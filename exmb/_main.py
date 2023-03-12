from __future__ import annotations
from argparse import ArgumentParser, Namespace
from collections import deque
from datetime import datetime, timedelta, timezone
from json import dump, load
from pathlib import Path
from queue import Queue
from time import sleep
from typing import NotRequired, TypedDict

from exdc.client import Gateway, REST
# from exdc.exception import GatewayReceiveTimeout
from exdc.type.gateway import Intent, PresenceActivity, PresenceActivityType, PresenceStatus, \
    PresenceUpdateData
from exrc import LinkThing, ListingSort, OAuth2Client, OAuth2RevokedTokenException, OAuth2Token
from exvhp import GfyCatClient, ImgurClient, StreamableClient, StreamffClient, StreamjaClient, \
    VHPClient
from exvhp.type import GfyCatCreatePost
from httpx import HTTPStatusError

__config_path__ = Path.home() / ".config" / "exmb"


class Credential(TypedDict):
    reddit: RedditCredential
    discord: NotRequired[DiscordCredential]


class DiscordCredential(TypedDict):
    bot_token: str
    owner_id: str


class Mirrors(TypedDict):
    streamable: NotRequired[str]
    streamff: NotRequired[str]
    streamja: NotRequired[str]


class RedditCredential(OAuth2Token):
    client_id: str
    client_secret: NotRequired[str]
    issued_at: str


def alias_saved():
    return [path.stem for path in __config_path__.glob("*.json")]


def auth_list():
    print("\n".join([
        "Available OAuth2 Authorizations",
        "-------------------------------",
        *alias_saved(),
    ]))


def auth_new(args: Namespace):
    assert args.alias not in alias_saved()

    reddit = OAuth2Client.code_flow_localserver(args.client_id, args.redirect_uri, args.duration,
                                                args.scopes.split(" "), state=args.state,
                                                client_secret=args.client_secret,
                                                user_agent=args.user_agent)
    reddit_credential = RedditCredential(**reddit.token, client_id=args.client_id,
                                         issued_at=reddit.token_issued_at.isoformat())

    if args.client_secret is not None:
        reddit_credential |= {"client_secret": args.client_secret}

    if args.discord_bot_token is not None and args.discord_owner_id:
        discord_credential = DiscordCredential(bot_token=args.discord_bot_token,
                                               owner_id=args.discord_owner_id)
        credential = Credential(reddit=reddit_credential, discord=discord_credential)

    else:
        credential = Credential(reddit=reddit_credential)

    with __config_path__.joinpath(f"{args.alias}.json").open(mode="w") as credential_stream:
        dump(credential, credential_stream, separators=(",", ":"))


def auth_revoke(args: Namespace):
    credential = load_credential(args)

    client_id = credential["reddit"]["client_id"]
    client_secret = None
    issued_at = datetime.fromisoformat(credential["reddit"]["issued_at"])

    if "client_secret" in credential["reddit"]:
        client_secret = credential["reddit"]["client_secret"]

    reddit = OAuth2Client(client_id, credential["reddit"], token_issued_at=issued_at,
                          client_secret=client_secret)

    try:
        reddit.revoke()

    except OAuth2RevokedTokenException:
        alias_credential_path = __config_path__.joinpath(f"{args.alias}.json")
        alias_credential_path.unlink()


def check_post_deleted(reddit: OAuth2Client, subreddit: str, post_id: str):
    res = reddit.info(ids=[post_id], subreddit=subreddit)

    if res.json()["data"]["dist"] == 0:
        raise ValueError(f"Post {post_id} doesn't exist!")

    latest_post: LinkThing = res.json()["data"]["children"][0]
    post_removal_status = latest_post["data"]["removed_by_category"]
    return post_removal_status is not None


def comment_mirrors(reddit: OAuth2Client, to_comment: Queue[tuple[LinkThing, Mirrors]]):
    while to_comment.qsize() > 0:
        post, mirrors = to_comment.get()
        post_name = post["data"]["name"]

        if len(mirrors) == 0:
            continue

        _mirrors: list[str] = []
        _references: dict[str, str] = {}

        if "streamable" in mirrors:
            _mirrors.append("* [Streamable][streamable]")
            _references["streamable"] = mirrors["streamable"]

        if "streamff" in mirrors:
            _mirrors.append("* [Streamff][streamff]")
            _references["streamff"] = mirrors["streamff"]

        if "streamja" in mirrors:
            _mirrors.append("* [Streamja][streamja]")
            _references["streamja"] = mirrors["streamja"]

        _references["pyexmb-link"] = "https://github.com/eXhumer/pyeXMB"
        _references["contact-link"] = "https://www.reddit.com/message/compose?to=" + \
            "%2Fu%2FContentPuff&subject=Issue%20with%20mirrors%20in%20post%20" + \
            f"{post_name}"

        md_text = "\n\n".join(["**Mirrors**", *_mirrors, "---",
                               "^Powered ^by ^[pyeXMB][pyexmb-link] ^| [^(Contact " +
                               "author incase of issue with mirrors)][contact-link]",
                               "\n".join([f"[{key}]: {val}"
                                          for key, val in _references.items()])])

        parent_id = post_name
        res = reddit.comments(post["data"]["id"], subreddit=post["data"]["subreddit"], limit=1)

        if (
            len(res.json()) == 2
            and len(res.json()[1]["data"]["children"]) > 0
        ):
            comment = res.json()[1]["data"]["children"][0]["data"]

            author = comment["author"] if "author" in comment else None
            locked = comment["locked"] if "locked" in comment else None
            stickied = comment["stickied"] if "stickied" in comment else None

            if (author is not None and author == "AutoModerator") and \
                    (locked is not None and locked is False) and \
                    (stickied is not None and stickied is True):
                parent_id = comment["name"]

        reddit.comment(parent_id, text=md_text)


def mirror_for_posts(reddit: OAuth2Client, vhp: VHPClient, args: Namespace):
    to_mirror: Queue[tuple[LinkThing, int, datetime | None]] = Queue()
    to_comment: Queue[tuple[LinkThing, Mirrors]] = Queue()

    mirror_post_names = [f"t3_{post_id}" for post_id in args.post_ids]

    res = reddit.info(ids=mirror_post_names)

    not_found_post_names = [post_name for post_name in mirror_post_names if post_name
                            not in (post["data"]["name"] for post
                                    in res.json()["data"]["children"])]

    found_posts: list[LinkThing] = res.json()["data"]["children"]

    for post in found_posts:
        to_mirror.put((post, 0, None))

    mirror_posts(vhp, to_mirror, to_comment, args)
    comment_mirrors(reddit, to_comment)

    return [post["data"]["name"] for post in found_posts], not_found_post_names


def get_subreddit_latest_post_name(reddit: OAuth2Client, args: Namespace):
    res = reddit.posts(subreddit=args.subreddit, sort=ListingSort.NEW, limit=1)

    if res.json()["data"]["dist"] == 0:
        raise ValueError(f"No posts in subreddit r/{args.subreddit}!")

    latest_post: LinkThing = res.json()["data"]["children"][0]
    return latest_post["data"]["name"]


def load_clients(args: Namespace):
    credential = load_credential(args)

    client_id = credential["reddit"]["client_id"]
    client_secret = None
    issued_at = datetime.fromisoformat(credential["reddit"]["issued_at"])

    if "client_secret" in credential["reddit"]:
        client_secret = credential["reddit"]["client_secret"]

    reddit = OAuth2Client(client_id, credential["reddit"], token_issued_at=issued_at,
                          client_secret=client_secret, user_agent=args.user_agent)
    discord_clients = None

    if "discord" in credential and args.action == "run-bot":
        discord_rest = REST.with_bot_token(credential["discord"]["bot_token"],
                                           user_agent=args.user_agent)
        presence_update = PresenceUpdateData(
            activities=[PresenceActivity(name=f"for media posts on 'r/{args.subreddit}'",
                                         type=PresenceActivityType.WATCHING)],
            status=PresenceStatus.DND,
            afk=True)
        discord_gateway = Gateway(credential["discord"]["bot_token"], Intent.DIRECT_MESSAGES,
                                  presence_update=presence_update, user_agent=args.user_agent)

        discord_clients = (discord_rest, discord_gateway)

    return reddit, VHPClient(user_agent=args.user_agent), discord_clients, \
        credential["discord"]["owner_id"] if "discord" in credential else None


def load_credential(args: Namespace):
    assert args.alias in alias_saved()

    alias_credential_path = __config_path__.joinpath(f"{args.alias}.json")

    with alias_credential_path.open(mode="rb") as credential_stream:
        credential: Credential = load(credential_stream)

    return credential


def mirror_posts(vhp: VHPClient, to_mirror: Queue[tuple[LinkThing, int, datetime | None]],
                 to_comment: Queue[tuple[LinkThing, Mirrors]], args: Namespace):
    while to_mirror.qsize() > 0:
        post, retries, try_after = to_mirror.get()

        if retries >= 5:
            continue

        if try_after is not None and try_after > datetime.now(tz=timezone.utc):
            to_mirror.put((post, retries, try_after))
            continue

        media_url = post["data"]["url"]

        if media_url.startswith("https://gfycat.com/"):
            gfyname = media_url[len("https://gfycat.com/"):]
            upload_status = vhp.gfycat.get_upload_status(gfyname)

            if upload_status["task"] != "complete":
                if "time" in upload_status:
                    try_after = datetime.now(tz=timezone.utc) + \
                        timedelta(seconds=upload_status["time"])
                    to_mirror.put((post, retries + 1, try_after))

                continue

            video_url = vhp.gfycat.get_post_info(gfyname)["gfyItem"]["mp4Url"]

        elif media_url.startswith("https://imgur.com/"):
            if media_url.startswith("https://imgur.com/a/"):
                continue

            media_id = media_url[len("https://imgur.com/"):]

            try:
                video_url = vhp.imgur.get_media(media_id)["media"][0]["url"]

            except HTTPStatusError as ex:
                if ex.response.status_code == 404:
                    continue

                raise ex

        elif media_url.startswith("https://streamable.com/"):
            video_id = media_url[len("https://streamable.com/"):]

            if not vhp.streamable.is_video_available(video_id):
                continue

            if vhp.streamable.is_video_processing(video_id):
                try_after = datetime.now(tz=timezone.utc) + timedelta(seconds=10)
                to_mirror.put((post, retries + 1, try_after))
                continue

            video_url = vhp.streamable.get_video_url(video_id)

        elif media_url.startswith("https://streamff.com/v/"):
            video_id = media_url[len("https://streamff.com/"):]
            video_link = vhp.streamff.get_video_data(video_id)["videoLink"]
            video_url = f"https://streamff.com{video_link}"

        elif media_url.startswith("https://streamja.com/"):
            media_url = media_url.replace("/embed/", "/")
            video_id = media_url[len("https://streamja.com/"):]

            if not vhp.streamja.is_video_available(video_id):
                continue

            if vhp.streamja.is_video_processing(video_id):
                try_after = datetime.now(tz=timezone.utc) + timedelta(seconds=10)
                to_mirror.put((post, retries + 1, try_after))
                continue

            video_url = vhp.streamja.get_video_url(video_id)

        else:
            continue

        video_stream = vhp.get_media_from_url(video_url)

        mirrors = Mirrors()

        if True:
            mirror_streamable = vhp.streamable.clip_video(video_url, title=post["data"]["title"])
            mirrors |= {"streamable": mirror_streamable["url"]}

        if args.streamff_mirror:
            mirror_streamff_video_id, mirror_streamff_url = \
                vhp.streamff.upload_video(video_stream)
            mirrors |= {"streamff": mirror_streamff_url}

        if True:
            mirror_streamja = vhp.streamja.upload_video(video_stream)
            mirror_shortid = mirror_streamja['shortId']
            mirrors |= {"streamja": f"https://streamja.com/{mirror_shortid}"}

        to_comment.put((post, mirrors))


def parse_program_args():
    parser = ArgumentParser()
    parser.add_argument("--user-agent")
    subparsers = parser.add_subparsers(dest="action")
    auth_parser = subparsers.add_parser("auth")
    auth_subparsers = auth_parser.add_subparsers(dest="auth_action")
    auth_new_parser = auth_subparsers.add_parser("new")
    auth_new_parser.add_argument("alias")
    auth_new_parser.add_argument("client_id")
    auth_new_parser.add_argument("scopes")
    auth_new_parser.add_argument("redirect_uri")
    auth_new_parser.add_argument("--client-secret")
    auth_new_parser.add_argument("--discord-bot-token")
    auth_new_parser.add_argument("--discord-owner-id")
    auth_new_parser.add_argument("--duration", choices=["temporary", "permanent"],
                                 default="permanent")
    auth_new_parser.add_argument("--state")
    auth_subparsers.add_parser("list")
    auth_revoke_parser = auth_subparsers.add_parser("revoke")
    auth_revoke_parser.add_argument("alias")
    mirror_posts_parser = subparsers.add_parser("mirror-posts")
    mirror_posts_parser.add_argument("alias")
    mirror_posts_parser.add_argument("post_ids", nargs="+")
    mirror_posts_parser.add_argument("--reddit-mirror", action="store_true")
    mirror_posts_parser.add_argument("--streamff-mirror", action="store_true")
    mirror_posts_parser.add_argument("--skip-missing-stickied-automod", action="store_true")
    post_parser = subparsers.add_parser("post")
    post_parser.add_argument("alias")
    post_parser.add_argument("title")
    post_parser.add_argument("media_path", type=Path)
    post_parser.add_argument("--nsfw", action="store_true")
    post_parser.add_argument("--send-replies", action="store_true")
    post_parser.add_argument("--spoiler", action="store_true")
    post_parser.add_argument("--subreddit")
    post_parser.add_argument("--flair-id")
    post_parser.add_argument("--flair-text")
    post_subparsers = post_parser.add_subparsers(dest="post_action")
    post_gfycat_parser = post_subparsers.add_parser("gfycat")
    post_gfycat_parser.add_argument("--description")
    post_gfycat_parser.add_argument("--no-md5", action="store_true")
    post_gfycat_parser.add_argument("--post-on-encoding", action="store_true")
    post_gfycat_parser.add_argument("--private", action="store_true")
    post_imgur_parser = post_subparsers.add_parser("imgur")
    post_imgur_parser.add_argument("--description")
    post_reddit_parser = post_subparsers.add_parser("reddit")
    post_reddit_parser.add_argument("--no-websocket")
    post_streamable_parser = post_subparsers.add_parser("streamable")
    post_streamable_parser.add_argument("--upload-region")
    post_subparsers.add_parser("streamff")
    post_subparsers.add_parser("streamja")
    run_bot_parser = subparsers.add_parser("run-bot")
    run_bot_parser.add_argument("alias")
    run_bot_parser.add_argument("subreddit")
    run_bot_parser.add_argument("--before")
    run_bot_parser.add_argument("--limit", type=int)
    run_bot_parser.add_argument("--reddit-mirror", action="store_true")
    run_bot_parser.add_argument("--sleep-interval", type=int, default=30)
    run_bot_parser.add_argument("--streamff-mirror", action="store_true")
    run_bot_parser.add_argument("--skip-missing-stickied-automod", action="store_true")

    return parser.parse_args()


def post_gfycat(reddit: OAuth2Client, gfycat: GfyCatClient, args: Namespace):
    post_data = GfyCatCreatePost(title=args.title, nsfw=args.nsfw, noMd5=args.no_md5,
                                 private=args.private)

    if "description" in args:
        post_data |= {"description": args.description}

    gfycat_post = gfycat.new_video_post(post_data=post_data)

    with args.media_path.open(mode="rb") as media_stream:
        assert gfycat.upload_video(gfycat_post["gfyname"], media_stream,
                                   filename=args.media_path.name,
                                   upload_type=gfycat_post["uploadType"])

    while True:
        status = gfycat.get_upload_status(gfycat_post["gfyname"])

        if status["task"] == "complete" or \
                (args.post_on_encoding and status["task"] == "encoding"):
            break

        if "time" in status:
            sleep(status["time"])

        else:
            raise ValueError(status)

    gfyname = status["gfyname"] if "gfyname" in status else gfycat_post["gfyname"]
    url = f"https://gfycat.com/{gfyname}"
    submission = reddit.submit_link(args.title, url, nsfw=args.nsfw,
                                    send_replies=args.send_replies, spoiler=args.spoiler,
                                    subreddit=args.subreddit, flair_id=args.flair_id,
                                    flair_text=args.flair_text)
    print(submission)


def post_imgur(reddit: OAuth2Client, imgur: ImgurClient, args: Namespace):
    with args.media_path.open(mode="rb") as media_stream:
        ticket = imgur.upload_media(media_stream, args.media_path.name)

    while True:
        ticket_poll = imgur.poll_video_tickets(ticket["data"]["ticket"])

        if ticket["data"]["ticket"] in ticket_poll["data"]["done"]:
            break

    media_id = ticket_poll["data"]["done"][ticket["data"]["ticket"]]
    media_data = ticket_poll["data"]["images"][media_id]

    imgur.update_media(media_data["deletehash"], title=args.title, description=args.description)

    url = f"https://imgur.com/{media_id}"

    submission = reddit.submit_link(args.title, url, nsfw=args.nsfw,
                                    send_replies=args.send_replies,
                                    spoiler=args.spoiler, subreddit=args.subreddit,
                                    flair_id=args.flair_id, flair_text=args.flair_text)
    print(submission)


def post_reddit(reddit: OAuth2Client, args: Namespace):
    with args.media_path.open(mode="rb") as media_stream:
        submission, update = reddit.submit_video(args.title, media_stream, args.media_path.name,
                                                 nsfw=args.nsfw, send_replies=args.send_replies,
                                                 spoiler=args.spoiler, subreddit=args.subreddit,
                                                 flair_id=args.flair_id,
                                                 flair_text=args.flair_text,
                                                 wait_for_ws_update=not args.no_websocket)
        print(submission, update)


def post_streamable(reddit: OAuth2Client, streamable: StreamableClient, args: Namespace):
    with args.media_path.open(mode="rb") as media_stream:
        upload_data = streamable.upload_video(media_stream, filename=args.media_path.name,
                                              title=args.title, upload_region=args.upload_region)

    if upload_data["status"] != 1:
        raise Exception  # TODO: Better exception raising

    submission = reddit.submit_link(args.title, upload_data["url"], nsfw=args.nsfw,
                                    send_replies=args.send_replies,
                                    spoiler=args.spoiler, subreddit=args.subreddit,
                                    flair_id=args.flair_id, flair_text=args.flair_text)
    print(submission)


def post_streamff(reddit: OAuth2Client, streamff: StreamffClient, args: Namespace):
    with args.media_path.open(mode="rb") as media_stream:
        video_id, video_url = streamff.upload_video(media_stream, filename=args.media_path.name)

    submission = reddit.submit_link(args.title, video_url, nsfw=args.nsfw,
                                    send_replies=args.send_replies,
                                    spoiler=args.spoiler, subreddit=args.subreddit,
                                    flair_id=args.flair_id, flair_text=args.flair_text)
    print(submission)


def post_streamja(reddit: OAuth2Client, streamja: StreamjaClient, args: Namespace):
    with args.media_path.open(mode="rb") as media_stream:
        upload_data = streamja.upload_video(media_stream, args.media_path.name)

    if upload_data["status"] != 1:
        raise Exception  # TODO: Better exception raising

    url = f"https://streamja.com/{upload_data['shortId']}"

    submission = reddit.submit_link(args.title, url, nsfw=args.nsfw,
                                    send_replies=args.send_replies,
                                    spoiler=args.spoiler, subreddit=args.subreddit,
                                    flair_id=args.flair_id, flair_text=args.flair_text)
    print(submission)


def run_bot(reddit: OAuth2Client, vhp: VHPClient, args: Namespace,
            discord: tuple[REST, Gateway] | None = None, discord_owner_id: str | None = None):
    if discord is not None:
        assert discord_owner_id is not None
        rest, gateway = discord
        owner_dm_channel = rest.create_dm_channel(discord_owner_id)

    else:
        rest, gateway, owner_dm_channel = None, None, None

    mirror_stack: deque[str] = deque()
    to_comment: Queue[tuple[LinkThing, Mirrors]] = Queue()
    to_mirror: Queue[tuple[LinkThing, int, datetime | None]] = Queue()

    try:
        while True:
            if search_posts(reddit, mirror_stack, to_mirror, args):
                new_posts_len = to_mirror.qsize()

                if discord is not None:
                    assert rest is not None and gateway is not None and \
                        owner_dm_channel is not None

                    rest.post_message(owner_dm_channel["id"],
                                      content=f"Found new posts {new_posts_len} to mirror!")

                mirror_posts(vhp, to_mirror, to_comment, args)
                comment_mirrors(reddit, to_comment)

            if discord is not None:
                rest.post_message(owner_dm_channel["id"],
                                  content=f"Sleeping bot for {args.sleep_interval} seconds!")

            sleep(args.sleep_interval)

    except KeyboardInterrupt:
        if discord is not None:
            rest.post_message(owner_dm_channel["id"], content="Shutting bot down!")

        comment_mirrors(reddit, to_comment)


def search_posts(reddit: OAuth2Client, mirror_stack: deque[str],
                 to_mirror: Queue[tuple[LinkThing, int, datetime | None]], args: Namespace):
    if not args.before:
        args.before = get_subreddit_latest_post_name(reddit, args)

    if check_post_deleted(reddit, args.subreddit, args.before) is True:
        args.before = mirror_stack.pop() if len(mirror_stack) else \
            get_subreddit_latest_post_name(reddit, args)
        return False

    posts_res = reddit.posts(subreddit=args.subreddit, sort=ListingSort.NEW, before=args.before,
                             limit=args.limit)
    posts_json = posts_res.json()

    if posts_json["data"]["dist"] != 0:
        posts: list[LinkThing] = posts_json["data"]["children"]

        for post in reversed(posts):
            if not post["data"]["url"].startswith(("https://gfycat.com/",
                                                   "https://imgur.com/",
                                                   "https://streamable.com/",
                                                   "https://streamff.com/",
                                                   "https://streamja.com/")):
                continue

            res = reddit.comments(post["data"]["id"], subreddit=post["data"]["subreddit"],
                                  limit=1)
            res_json = res.json()

            if len(res_json) == 2 and len(res_json[1]["data"]["children"]) == 1:
                comment = res.json()[1]["data"]["children"][0]["data"]

                author = comment["author"] if "author" in comment else None
                locked = comment["locked"] if "locked" in comment else None
                stickied = comment["stickied"] if "stickied" in comment else None

                assert author is not None, comment
                assert locked is not None, comment
                assert stickied is not None, comment

                if (author != "AutoModerator" or locked is True or stickied is False) \
                        and args.skip_missing_stickied_automod:
                    continue

            elif args.skip_missing_stickied_automod:
                continue

            to_mirror.put((post, 0, None))

        args.before = posts[0]["data"]["name"]
        return to_mirror.qsize() > 0

    return False


def update_credential(reddit: OAuth2Client, args: Namespace):
    credential = load_credential(args)
    credential["reddit"] |= RedditCredential(**(credential["reddit"] | reddit.token |
                                                {"issued_at": reddit.token_issued_at.
                                                    isoformat()}))

    alias_credential_path = __config_path__.joinpath(f"{args.alias}.json")

    with alias_credential_path.open(mode="w") as credential_stream:
        dump(credential, credential_stream, separators=(",", ":"))


def __program_main():
    args = parse_program_args()

    if args.action == "auth":
        if args.auth_action == "list":
            auth_list()

        elif args.auth_action == "new":
            auth_new(args)

        elif args.auth_action == "revoke":
            auth_revoke(args)

    elif args.action == "post":
        reddit, vhp, discord, discord_owner_id = load_clients(args)

        if args.post_action == "reddit":
            post_reddit(reddit, args)

        else:
            if args.post_action == "gfycat":
                post_gfycat(reddit, vhp.gfycat, args)

            elif args.post_action == "imgur":
                post_imgur(reddit, vhp.imgur, args)

            elif args.post_action == "streamable":
                post_streamable(reddit, vhp.streamable, args)

            elif args.post_action == "streamff":
                post_streamff(reddit, vhp.streamff, args)

            elif args.post_action == "streamja":
                post_streamja(reddit, vhp.streamja, args)

            update_credential(reddit, args)

    elif args.action == "mirror-posts":
        reddit, vhp, discord, discord_owner_id = load_clients(args)

        mirror, not_mirrored = mirror_for_posts(reddit, vhp, args)

        print(f"Mirrored: {mirror}")
        print(f"Not Mirrored: {not_mirrored}")

    elif args.action == "run-bot":
        reddit, vhp, discord, discord_owner_id = load_clients(args)

        run_bot(reddit, vhp, args, discord=discord, discord_owner_id=discord_owner_id)

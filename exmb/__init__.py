# eXMB - Bot to mirror r/formula1 highlight clips
# Copyright (C) 2021 - eXhumer

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, version 3 of the License.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

"""Bot module to mirror r/formula1 highlight clips"""
from __future__ import annotations
from argparse import ArgumentParser, Namespace
from io import BytesIO
from pathlib import Path
from pkg_resources import require
from time import sleep
from typing import Any, Dict, List

from exrc.client import OAuth2Client
from exvhp.client import (
    JustStreamLive, Streamable, Streamja, Streamwo, Streamff,
)
from requests import Session

__version__ = require(__package__)[0].version
__config_path__ = Path.home() / ".config" / __package__
__user_agent__ = f"{__package__}/{__version__}"
__clippers__ = (
    "ContentPuff",
    "magony",
    "sefn19",
    "DoeEensGek",
    "asd241",
    "TwoPlanksPrevail",
)
__flairs__ = (
    "Video",
    "Highlight",
    ":post-video: Video",
)
__highlight_search_query__ = " AND ".join((
    f"({query_part})"
    for query_part
    in (
        " OR ".join((
            f"author:{author}"
            for author
            in __clippers__
        )),
        " OR ".join((
            f"flair:{flair}"
            for flair
            in (
                "Video",
                "Highlight",
                '":post-video: Video"',
            )
        )),
    )
))


def __bot_clients_setup(auth_alias: str):
    session = Session()
    session.headers["User-Agent"] = __user_agent__

    return (
        OAuth2Client.load_from_file(
            __config_path__ / f"{auth_alias}.json",
            session=session,
        ),
        JustStreamLive(session=session),
        Streamable(session=session),
        Streamja(session=session),
        Streamff(session=session),
        Streamwo(session=session),
    )


def __run_bot(
    auth_alias: str,
    subreddit: str | None = None,
    **listing_kwargs: str | int,
):
    if subreddit is None:
        subreddit = "formula1"

    kwargs = {}

    for key, val in listing_kwargs.items():
        if key in ("before", "limit") and val is not None:
            kwargs[key] = val

    (
        reddit,
        juststreamlive,
        streamable,
        streamja,
        streamff,
        streamwo,
    ) = __bot_clients_setup(auth_alias)

    if "before" not in kwargs or kwargs["before"] is None:
        print("before not specified! attempting to retrieve latest post name")
        kwargs["before"] = None

        if kwargs["before"] is None:
            res = reddit.get(
                f"r/{subreddit}/new",
                params={"limit": 1},
            )

            if not res.ok:
                raise ValueError(
                    "Invalid response while trying to retrieve latest post " +
                    "name!",
                )

            if res.json()["data"]["dist"] == 0:
                raise Exception(f"Unable to any valid post in {subreddit}")

            kwargs.update({
                "before": res.json()["data"]["children"][0]["data"]["name"],
            })

        print(f"Latest post name: {kwargs['before']}")

    while True:
        print(f"Retrieving all posts before post name {kwargs['before']}")

        res = reddit.get(
            f"r/{subreddit}/new",
            params=kwargs,
        )

        if not res.ok:
            raise ValueError(
                "Invalid response while trying to retrieve posts listing!",
            )

        highlight_posts = []

        while res.json()["data"]["dist"] != 0:
            subreddit_listing_posts = res.json()["data"]["children"]

            for post in subreddit_listing_posts:
                if (
                    post["data"]["link_flair_text"] in __flairs__
                    and post["data"]["author"] in __clippers__
                ):
                    highlight_posts.append(post)

            kwargs.update({
                "before": subreddit_listing_posts[0]["data"]["name"],
            })

            res = reddit.get(
                f"r/{subreddit}/new",
                params=kwargs,
            )

            if not res.ok:
                raise ValueError(
                    "Invalid response while trying to retrieve posts listing!",
                )

        __mirror_for_posts(
            highlight_posts,
            reddit,
            streamable,
            streamja,
            juststreamlive,
            streamff,
            streamwo,
        )

        print("Sleeping for 10 seconds!")
        sleep(10)


def __mirror_for_posts_by_id(
    auth_alias: str,
    post_ids: List[str],
    subreddit: str | None = None,
):
    (
        reddit,
        juststreamlive,
        streamable,
        streamja,
        streamff,
        streamwo,
    ) = __bot_clients_setup(auth_alias)

    res = reddit.info(ids=post_ids, subreddit=subreddit)

    if not res.ok:
        raise ValueError(
            "Invalid response while trying to retrieve posts by ID!",
        )

    if len(post_ids) != res.json()["data"]["dist"]:
        not_found_posts = ", ".join((
            post_id
            for post_id
            in post_ids
            if post_id
            not in (
                post["data"]["name"]
                for post
                in res.json()["data"]["children"]
            )
        ))

        print(f"Posts {not_found_posts} were not found!")

    __mirror_for_posts(
        res.json()["data"]["children"],
        reddit,
        streamable,
        streamja,
        juststreamlive,
        streamff,
        streamwo,
    )


def __mirror_for_posts(
    highlight_posts: List[Dict[str, Any]],
    reddit: OAuth2Client,
    streamable: Streamable,
    streamja: Streamja,
    juststreamlive: JustStreamLive,
    streamff: Streamff,
    streamwo: Streamwo,
):
    for post in highlight_posts:
        vid_url: str = post["data"]["url"]

        sab_mirror_res = None
        sja_mirror_res = None
        jsl_mirror_res = None
        sff_mirror_res = None

        if not vid_url.startswith((
            "https://streamable.com/",
            "https://streamja.com/",
            "https://streamwo.com/",
            "https://streamff.com/v/",
        )):
            print(
                f"Post {post['data']['name']} with unsupported video host!"
            )
            continue

        if vid_url.startswith("https://streamable.com/"):
            streamable_id = vid_url.split("https://streamable.com/")[1]
            print(f"Processing {post['data']['name']} with Streamable " +
                  f"Video {streamable_id}")

            vid_res = streamable.get_video(streamable_id)

            if not vid_res.ok:
                print("Unable to get direct video link from Streamable " +
                      f"video ID {streamable_id}. Video not available / " +
                      "taken down!")
                continue

            media_data = BytesIO(vid_res.content)

            sab_mirror_res = streamable.clip_video(
                streamable_id,
                mirror_title=post["data"]["title"],
            )
            jsl_mirror_res = \
                juststreamlive.mirror_streamable_video(streamable_id)
            sja_mirror_res = \
                streamja.upload_video(media_data, "Mirror.mp4")
            sff_mirror_res = \
                streamff.upload_video(media_data, "Mirror.mp4")

        elif vid_url.startswith("https://streamja.com/"):
            streamja_id = vid_url.split("https://streamja.com/")[1]

            if streamja_id.startswith("embed/"):
                streamja_id = vid_url.split("embed/")[1]

            print(f"Processing {post['data']['name']} with Streamja " +
                  f"Video {streamja_id}")

            vid_res = streamja.get_video(streamja_id)

            if not vid_res.ok:
                print("Unable to get direct video link from Streamja " +
                      f"video ID {streamja_id}. Video not available / " +
                      "taken down!")
                continue

            media_data = BytesIO(vid_res.content)

            sab_mirror_res = streamable.clip_streamja_video(
                streamja_id,
                mirror_title=post["data"]["title"],
            )
            jsl_mirror_res = \
                juststreamlive.mirror_streamja_video(streamja_id)
            sja_mirror_res = \
                streamja.upload_video(media_data, "Mirror.mp4")
            sff_mirror_res = \
                streamff.upload_video(media_data, "Mirror.mp4")

        elif vid_url.startswith("https://streamwo.com/"):
            streamwo_id = vid_url.split("https://streamwo.com/")[1]
            print(f"Processing {post['data']['name']} with Streamwo " +
                  f"Video {streamwo_id}")

            vid_res = streamwo.get_video(streamwo_id)

            if not vid_res.ok:
                print("Unable to get direct video link from Streamwo " +
                      f"video ID {streamwo_id}. Video not available / " +
                      "taken down!")
                continue

            media_data = BytesIO(vid_res.content)

            sab_mirror_res = streamable.clip_streamwo_video(
                streamwo_id,
                mirror_title=post["data"]["title"],
            )
            jsl_mirror_res = \
                juststreamlive.mirror_streamwo_video(streamwo_id)
            sja_mirror_res = \
                streamja.upload_video(media_data, "Mirror.mp4")
            sff_mirror_res = \
                streamff.upload_video(media_data, "Mirror.mp4")

        elif vid_url.startswith("https://streamff.com/v/"):
            streamff_id = vid_url.split("https://streamff.com/v/")[1]
            print(f"Processing {post['data']['name']} with Streamff " +
                  f"Video {streamff_id}")

            vid_res = streamff.get_video(streamff_id)

            if not vid_res.ok:
                print("Unable to get direct video link from Streamff " +
                      f"video ID {streamff_id}. Video not available / " +
                      "taken down!")
                continue

            media_data = BytesIO(vid_res.content)

            sab_mirror_res = streamable.clip_streamff_video(
                streamff_id,
                mirror_title=post["data"]["title"],
            )
            jsl_mirror_res = \
                juststreamlive.upload_video(media_data, "Mirror.mp4")
            sja_mirror_res = \
                streamja.upload_video(media_data, "Mirror.mp4")
            sff_mirror_res = \
                streamff.upload_video(media_data, "Mirror.mp4")

        mirrors = []

        if (
            sab_mirror_res.ok
            and sab_mirror_res.json()["error"] is None
        ):
            print(f"Streamable mirror created for {post['data']['name']}!")
            mirrors.append(f"* [Streamable]({sab_mirror_res.json()['url']})")

        else:
            print(f"Streamable mirror failed for {post['data']['name']}!")
            print(f"|- Status Code: {sab_mirror_res.status_code}")
            print(f"|- Request URL: {sab_mirror_res.url}")
            print(f"|- Response Text: {sab_mirror_res.text}")

        if jsl_mirror_res.ok:
            jsl_mid = jsl_mirror_res.json()["id"]
            print("Juststreamlive mirror created for " +
                  f"{post['data']['name']}!")
            mirrors.append(
                f"* [JustStreamLive](https://juststream.live/{jsl_mid})",
            )

        else:
            print(f"Juststreamlive mirror failed for {post['data']['name']}!")
            print(f"|- Status Code: {jsl_mirror_res.status_code}")
            print(f"|- Request URL: {jsl_mirror_res.url}")
            print(f"|- Response Text: {jsl_mirror_res.text}")

        if (
            sja_mirror_res.ok
            and sja_mirror_res.json()["status"] == 1
        ):
            sja_mid = sja_mirror_res.json()["url"]
            print(f"Streamja mirror created for {post['data']['name']}!")
            mirrors.append(
                "* " + " | ".join((
                    f"[Streamja Embed](https://streamja.com/embed{sja_mid})",
                    f"[Streamja Non-Embed](https://streamja.com{sja_mid})",
                )),
            )

        else:
            print(f"Streamja mirror failed for {post['data']['name']}!")
            print(f"|- Status Code: {sja_mirror_res.status_code}")
            print(f"|- Request URL: {sja_mirror_res.url}")
            print(f"|- Response Text: {sja_mirror_res.text}")

        if sff_mirror_res.ok:
            print(f"Streamff mirror created for {post['data']['name']}!")
            mirror_url = "https://streamff.com/v/" + sff_mirror_res.url.split(
                "https://streamff.com/api/videos/upload/",
            )[1]
            mirrors.append(f"* [Streamff]({mirror_url})")

        else:
            print(f"Streamff mirror failed for {post['data']['name']}!")
            print(f"|- Status Code: {sff_mirror_res.status_code}")
            print(f"|- Request URL: {sff_mirror_res.url}")
            print(f"|- Response Text: {sff_mirror_res.text}")

        if len(mirrors) > 0:
            parent_id = post["data"]["name"]

            res = reddit.comments(
                post["data"]["id"],
                subreddit=post["data"]["subreddit"],
                limit=1,
            )

            if not res.ok:
                print("Invalid response while trying to retrieve comments " +
                      "listing!")

            elif (
                len(res.json()) == 2
                and len(res.json()[1]["data"]["children"]) > 0
            ):
                post_first_comment = res.json()[1]["data"]["children"][0]

                if post_first_comment["data"]["stickied"] is True:
                    parent_id = post_first_comment["data"]["name"]

                else:
                    print(f"No sticked comment under post {parent_id}")

            else:
                print(f"No comments under post {parent_id}")

            reddit.comment(
                "\n\n".join([
                    "**Mirrors**",
                    *mirrors,
                    "---",
                    "^(Powered by [eXMB](https://github.com/eXhumer/eXMB)" +
                    " | [Contact author incase of issue with mirror(s)]" +
                    "(https://www.reddit.com/message/compose?to=" +
                    "%2Fu%2FContentPuff&subject=Issue%20with%20" +
                    f"mirror(s)%20in%20post%20{post['data']['name']}))"
                ]),
                parent_id,
            )

        else:
            print(F"Failed to create any mirror for {post['data']['name']}")


def __post_juststreamlive(
    auth_alias: str,
    media_path: Path,
    title: str,
    subreddit: str | None = None,
    flair_id: str | None = None,
):
    session = Session()
    session.headers["User-Agent"] = __user_agent__
    reddit = OAuth2Client.load_from_file(
        __config_path__ / f"{auth_alias}.json",
        session=session,
    )
    juststreamlive = JustStreamLive(session=session)
    res = juststreamlive.upload_from_file(media_path)

    if not res.ok:
        raise Exception("Invalid response while uploading file to " +
                        "JustStreamLive!")

    reddit.submit_url(
        title,
        f"https://juststream.live/{res.json()['id']}",
        subreddit=subreddit,
        flair_id=flair_id,
    )


def __post_streamable(
    auth_alias: str,
    media_path: Path,
    title: str,
    subreddit: str | None = None,
    flair_id: str | None = None,
):
    session = Session()
    session.headers["User-Agent"] = __user_agent__
    reddit = OAuth2Client.load_from_file(
        __config_path__ / f"{auth_alias}.json",
        session=session,
    )
    streamable = Streamable(session=session)

    res = streamable.upload_from_file(media_path, video_title=title)

    if not res.ok or res.json()["error"] is not None:
        raise Exception("Invalid response while uploading file to " +
                        "Streamable!")

    reddit.submit_url(
        title,
        res.json()["url"],
        subreddit=subreddit,
        flair_id=flair_id,
    )


def __post_streamja(
    auth_alias: str,
    media_path: Path,
    title: str,
    subreddit: str | None = None,
    flair_id: str | None = None,
):
    session = Session()
    session.headers["User-Agent"] = __user_agent__
    reddit = OAuth2Client.load_from_file(
        __config_path__ / f"{auth_alias}.json",
        session=session,
    )
    streamja = Streamja(session=session)
    res = streamja.upload_from_file(media_path)

    if not res.ok or res.json()["status"] == 0:
        raise Exception("Invalid response while uploading file to " +
                        "Streamja!")

    reddit.submit_url(
        title,
        f"https://streamja.com{res.json()['url']}",
        subreddit=subreddit,
        flair_id=flair_id,
    )


def __post_streamwo(
    auth_alias: str,
    media_path: Path,
    title: str,
    subreddit: str | None = None,
    flair_id: str | None = None,
):
    session = Session()
    session.headers["User-Agent"] = __user_agent__
    reddit = OAuth2Client.load_from_file(
        __config_path__ / f"{auth_alias}.json",
        session=session,
    )
    streamwo = Streamwo(session=session)
    res = streamwo.upload_from_file(media_path)

    if not res.ok:
        raise Exception("Invalid response while uploading file to " +
                        "Streamwo!")

    reddit.submit_url(
        title,
        f"https://streamwo.com/{res.text}",
        subreddit=subreddit,
        flair_id=flair_id,
    )


def __post_streamff(
    auth_alias: str,
    media_path: Path,
    title: str,
    subreddit: str | None = None,
    flair_id: str | None = None,
):
    session = Session()
    session.headers["User-Agent"] = __user_agent__
    reddit = OAuth2Client.load_from_file(
        __config_path__ / f"{auth_alias}.json",
        session=session,
    )
    streamff = Streamff(session=session)
    res = streamff.upload_from_file(media_path)

    if not res.ok:
        raise Exception("Invalid response while uploading file to " +
                        "Streamff!")

    vid_id = res.url.split('https://streamff.com/api/videos/upload/')[1]
    reddit.submit_url(
        title,
        f"https://streamff.com/v/{vid_id}",
        subreddit=subreddit,
        flair_id=flair_id,
    )


def __parse_args(args: Namespace):
    if not __config_path__.is_dir():
        __config_path__.mkdir(parents=True)

    if args.action == "auth":
        if args.auth_action == "list":
            print("\n".join([
                "Available OAuth2 Authorizations",
                "-------------------------------",
                *[
                    path.stem
                    for path
                    in __config_path__.glob("*.json")
                ],
            ]))

        elif args.auth_action == "new":
            if not (__config_path__ / f"{args.alias}.json").is_file():
                OAuth2Client.localserver_code_flow(
                    args.client_id,
                    args.client_secret if args.client_secret else "",
                    args.callback_url,
                    args.duration,
                    args.scopes.split(" "),
                    state=args.state,
                    user_agent=__user_agent__,
                ).save_to_file(__config_path__ / f"{args.alias}.json")

            else:
                raise FileExistsError(
                    f"Authorization already exists with alias {args.alias}!",
                )

        elif args.auth_action == "revoke":
            if (__config_path__ / f"{args.alias}.json").is_file():
                OAuth2Client.load_from_file(
                    __config_path__ / f"{args.alias}.json",
                ).revoke()
                (__config_path__ / f"{args.alias}.json").unlink()

            else:
                raise KeyError(
                    f"No authorization alias with key {args.alias} found!",
                )

        else:
            raise ValueError(f'Invalid auth action "{args.auth_action}"!')

    elif args.action == "run-bot":
        if (__config_path__ / f"{args.alias}.json").is_file():
            __run_bot(
                args.alias,
                before=args.before,
                limit=args.limit,
                subreddit=args.subreddit,
            )

        else:
            raise KeyError(
                f"No authorization alias with key {args.alias} found!",
            )

    elif args.action == "mirror-for-post":
        if (__config_path__ / f"{args.alias}.json").is_file():
            __mirror_for_posts_by_id(
                args.alias,
                args.post_ids,
                subreddit=args.subreddit,
            )

        else:
            raise KeyError(
                f"No authorization alias with key {args.alias} found!",
            )

    elif args.action == "post-juststreamlive":
        if (__config_path__ / f"{args.alias}.json").is_file():
            __post_juststreamlive(
                args.alias,
                args.media_path,
                args.title,
                subreddit=args.subreddit,
                flair_id=args.flair_id,
            )

        else:
            raise KeyError(
                f"No authorization alias with key {args.alias} found!",
            )

    elif args.action == "post-streamable":
        if (__config_path__ / f"{args.alias}.json").is_file():
            __post_streamable(
                args.alias,
                args.media_path,
                args.title,
                subreddit=args.subreddit,
                flair_id=args.flair_id,
            )

        else:
            raise KeyError(
                f"No authorization alias with key {args.alias} found!",
            )

    elif args.action == "post-streamja":
        if (__config_path__ / f"{args.alias}.json").is_file():
            __post_streamja(
                args.alias,
                args.media_path,
                args.title,
                subreddit=args.subreddit,
                flair_id=args.flair_id,
            )

        else:
            raise KeyError(
                f"No authorization alias with key {args.alias} found!",
            )

    elif args.action == "post-streamwo":
        if (__config_path__ / f"{args.alias}.json").is_file():
            __post_streamwo(
                args.alias,
                args.media_path,
                args.title,
                subreddit=args.subreddit,
                flair_id=args.flair_id,
            )

        else:
            raise KeyError(
                f"No authorization alias with key {args.alias} found!",
            )

    elif args.action == "post-streamff":
        if (__config_path__ / f"{args.alias}.json").is_file():
            __post_streamff(
                args.alias,
                args.media_path,
                args.title,
                subreddit=args.subreddit,
                flair_id=args.flair_id,
            )

        else:
            raise KeyError(
                f"No authorization alias with key {args.alias} found!",
            )

    else:
        raise ValueError(f'Invalid action "{args.action}"!')


def console_main():
    parser = ArgumentParser()
    subparsers = parser.add_subparsers(dest="action")
    auth_parser = subparsers.add_parser("auth")
    auth_subparsers = auth_parser.add_subparsers(dest="auth_action")
    auth_new_parser = auth_subparsers.add_parser("new")
    auth_new_parser.add_argument("alias")
    auth_new_parser.add_argument("client_id")
    auth_new_parser.add_argument("scopes")
    auth_new_parser.add_argument("callback_url")
    auth_new_parser.add_argument("--client-secret")
    auth_new_parser.add_argument(
        "--duration", choices=["temporary", "permanent"],
    )
    auth_new_parser.add_argument("--state")
    auth_subparsers.add_parser("list")
    auth_revoke_parser = auth_subparsers.add_parser("revoke")
    auth_revoke_parser.add_argument("alias")
    run_parser = subparsers.add_parser("run-bot")
    run_parser.add_argument("alias")
    run_parser.add_argument("--before")
    run_parser.add_argument("--limit", type=int)
    run_parser.add_argument("--subreddit")
    mirror_for_post_parser = subparsers.add_parser("mirror-for-post")
    mirror_for_post_parser.add_argument("alias")
    mirror_for_post_parser.add_argument(
        "post_ids", metavar="post_id", nargs="+",
    )
    mirror_for_post_parser.add_argument("--subreddit")
    post_juststreamlive_parser = subparsers.add_parser("post-juststreamlive")
    post_juststreamlive_parser.add_argument("alias")
    post_juststreamlive_parser.add_argument("media_path", type=Path)
    post_juststreamlive_parser.add_argument("title")
    post_juststreamlive_parser.add_argument("--subreddit")
    post_juststreamlive_parser.add_argument("--flair-id")
    post_streamable_parser = subparsers.add_parser("post-streamable")
    post_streamable_parser.add_argument("alias")
    post_streamable_parser.add_argument("media_path", type=Path)
    post_streamable_parser.add_argument("title")
    post_streamable_parser.add_argument("--subreddit")
    post_streamable_parser.add_argument("--flair-id")
    post_streamja_parser = subparsers.add_parser("post-streamja")
    post_streamja_parser.add_argument("alias")
    post_streamja_parser.add_argument("media_path", type=Path)
    post_streamja_parser.add_argument("title")
    post_streamja_parser.add_argument("--subreddit")
    post_streamja_parser.add_argument("--flair-id")
    post_streamwo_parser = subparsers.add_parser("post-streamwo")
    post_streamwo_parser.add_argument("alias")
    post_streamwo_parser.add_argument("media_path", type=Path)
    post_streamwo_parser.add_argument("title")
    post_streamwo_parser.add_argument("--subreddit")
    post_streamwo_parser.add_argument("--flair-id")
    post_streamff_parser = subparsers.add_parser("post-streamff")
    post_streamff_parser.add_argument("alias")
    post_streamff_parser.add_argument("media_path", type=Path)
    post_streamff_parser.add_argument("title")
    post_streamff_parser.add_argument("--subreddit")
    post_streamff_parser.add_argument("--flair-id")

    __parse_args(parser.parse_args())

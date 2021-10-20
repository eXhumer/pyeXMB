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

from exrc.client import OAuth2Client
from exvhp.service import JustStreamLive, Streamable, Streamja, Streamwo
from exvhp.utils import (
    get_streamable_video_url,
    get_streamja_video_url,
    get_streamwo_video_url,
)
from requests import Session

__version__ = require(__package__)[0].version
__config_path__ = Path.home() / ".config" / __package__
__user_agent__ = f"{__package__}/{__version__}"
__highlight_search_query__ = " AND ".join((
    f"({query_part})"
    for query_part
    in (
        " OR ".join((
            f"author:{author}"
            for author
            in (
                "ContentPuff",
                "magony",
                "sefn19",
                "DoeEensGek",
                "asd241",
                "TwoPlanksPrevail",
            )
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


def __run_bot(auth_alias: str, **listing_kwargs: str | int):
    kwargs = {}

    for key, val in listing_kwargs.items():
        if key in ("before", "limit") and val is not None:
            kwargs[key] = val

    session = Session()
    session.headers["User-Agent"] = __user_agent__
    reddit = OAuth2Client.load_from_file(
        __config_path__ / f"{auth_alias}.json",
        session=session,
    )
    juststreamlive = JustStreamLive(session=session)
    streamable = Streamable(session=session)
    streamja = Streamja(session=session)
    streamwo = Streamwo(session=session)

    if "before" not in kwargs:
        print("before not specified! attempting to retrieve latest post name")

        res = reddit.search(
            __highlight_search_query__,
            subreddit="formula1",
            show="all",
            sort="new",
            type="link",
            **kwargs,
        )

        if res.status_code != 200:
            raise ValueError(
                "Invalid response while trying to retrieve latest post name!",
            )

        kwargs.update({
            "before": res.json()["data"]["children"][0]["data"]["name"],
        })

        print(f"Latest post name: {kwargs['before']}")

    while True:
        print(f"Searching all posts before post name {kwargs['before']}")

        res = reddit.search(
            __highlight_search_query__,
            subreddit="formula1",
            show="all",
            sort="new",
            type="link",
            **kwargs,
        )

        if res.status_code != 200:
            raise ValueError(
                "Invalid response while trying to retrieve posts listing!",
            )

        highlight_posts_listing = []

        while res.json()["data"]["dist"] != 0:
            new_listing = res.json()["data"]["children"]
            new_listing.extend(highlight_posts_listing)
            highlight_posts_listing = new_listing

            kwargs.update({
                "before": res.json()["data"]["children"][0]["data"]["name"],
            })

            res = reddit.search(
                __highlight_search_query__,
                subreddit="formula1",
                show="all",
                sort="new",
                type="link",
                **kwargs,
            )

            if res.status_code != 200:
                raise ValueError(
                    "Invalid response while trying to retrieve posts listing!",
                )

        for post in highlight_posts_listing:
            vid_url: str = post["data"]["url"]

            sab_mirror_res = None
            sja_mirror_res = None
            swo_mirror_res = None
            jsl_mirror_res = None

            if not vid_url.startswith((
                "https://streamable.com/",
                "https://streamja.com/",
                "https://streamwo.com/",
            )):
                print(
                    f"Post {post['data']['name']} with unsupported video host!"
                )
                continue

            if vid_url.startswith("https://streamable.com/"):
                streamable_id = vid_url.split("https://streamable.com/")[1]
                print(f"Processing {post['data']['name']} with Streamable " +
                      f"Video {streamable_id}")
                media_url = get_streamable_video_url(session, streamable_id)

                if media_url is None:
                    print("Unable to get direct video link from Streamable " +
                          f"video ID {streamable_id}. Video not available / " +
                          "taken down!")
                    continue

                media_res = session.get(media_url)

                if media_res != 200:
                    print("Invalid response while trying to retrieve media" +
                          f" content from {media_url} for Streamable Video " +
                          f"{streamable_id} for Reddit Post " +
                          f"{post['data']['name']}!")
                    continue

                media_data = BytesIO(media_res.content)

                sab_mirror_res = streamable.clip_video(
                    streamable_id,
                    mirror_title=post["data"]["title"],
                ),
                jsl_mirror_res = \
                    juststreamlive.mirror_streamable_video(streamable_id)
                sja_mirror_res = \
                    streamja.upload_video(media_data, "Mirror.mp4")
                swo_mirror_res = \
                    streamwo.upload_video(media_data, "Mirror.mp4")

            elif vid_url.startswith("https://streamja.com/"):
                streamja_id = vid_url.split("https://streamja.com/")[1]

                if streamja_id.startswith("embed/"):
                    streamja_id = vid_url.split("embed/")[1]

                print(f"Processing {post['data']['name']} with Streamja " +
                      f"Video {streamja_id}")

                media_url = get_streamja_video_url(
                    session,
                    streamja_id,
                )

                if media_url is None:
                    print("Unable to get direct video link from Streamja " +
                          f"video ID {streamja_id}. Video not available / " +
                          "taken down!")
                    continue

                media_res = session.get(media_url)

                if media_res.status_code != 200:
                    print("Invalid response while trying to retrieve media" +
                          f" content from {media_url} for Streamja Video " +
                          f"{streamja_id} for Reddit Post " +
                          f"{post['data']['name']}!")
                    continue

                media_data = BytesIO(media_res.content)

                sab_mirror_res = streamable.clip_streamja_video(
                    streamja_id,
                    mirror_title=post["data"]["title"],
                )
                jsl_mirror_res = \
                    juststreamlive.mirror_streamja_video(streamja_id)
                sja_mirror_res = \
                    streamja.upload_video(media_data, "Mirror.mp4")
                swo_mirror_res = \
                    streamwo.upload_video(media_data, "Mirror.mp4")

            elif vid_url.startswith("https://streamwo.com/"):
                streamwo_id = vid_url.split("https://streamwo.com/")[1]
                print(f"Processing {post['data']['name']} with Streamwo " +
                      f"Video {streamwo_id}")

                media_url = get_streamwo_video_url(
                    session,
                    streamwo_id,
                )

                if media_url is None:
                    print("Unable to get direct video link from Streamwo " +
                          f"video ID {streamwo_id}. Video not available / " +
                          "taken down!")
                    continue

                media_res = session.get(media_url)

                if media_res.status_code != 200:
                    print("Invalid response while trying to retrieve media" +
                          f" content from {media_url} for Streamwo Video " +
                          f"{streamwo_id} for Reddit Post " +
                          f"{post['data']['name']}!")
                    continue

                media_data = BytesIO(media_res.content)

                sab_mirror_res = streamable.clip_streamwo_video(
                    streamwo_id,
                    mirror_title=post["data"]["title"],
                )
                jsl_mirror_res = \
                    juststreamlive.mirror_streamwo_video(streamwo_id)
                sja_mirror_res = \
                    streamja.upload_video(media_data, "Mirror.mp4")
                swo_mirror_res = \
                    streamwo.upload_video(media_data, "Mirror.mp4")

            mirrors = []

            if (
                sab_mirror_res.status_code == 200
                and sab_mirror_res.json()["error"] is None
            ):
                print(f"Streamable mirror created for {post['data']['name']}!")
                mirrors.append(sab_mirror_res.json()["url"])

            else:
                print(f"Streamable mirror failed for {post['data']['name']}!")

            if jsl_mirror_res.status_code == 200:
                jsl_mid = jsl_mirror_res.json()["id"]
                print("Juststreamlive mirror created for " +
                      f"{post['data']['name']}!")
                mirrors.append(f"https://juststream.live/{jsl_mid}")

            else:
                print("Juststreamlive mirror failed for " +
                      f"{post['data']['name']}!")

            if (
                sja_mirror_res.status_code == 200
                and sja_mirror_res.json()["status"] == 1
            ):
                sja_mid = sja_mirror_res.json()["url"]
                print(f"Streamja mirror created for {post['data']['name']}!")
                mirrors.append(f"https://streamja.com/embed{sja_mid}")

            else:
                print(f"Streamja mirror created for {post['data']['name']}!")

            if swo_mirror_res.status_code == 200:
                print(f"Streamwo mirror created for {post['data']['name']}!")
                mirrors.append(
                    f"https://streamwo.com/{swo_mirror_res.text}",
                )

            else:
                print(f"Streamwo mirror created for {post['data']['name']}!")

            if len(mirrors) > 0:
                parent_id = post["data"]["name"]

                res = reddit.comments(
                    post["data"]["id"],
                    subreddit="formula1",
                    limit=1,
                )

                if res.status_code != 200:
                    print("Invalid response while trying to retrieve posts " +
                          "listing!")

                else:
                    post_first_comment = res.json()[1]["data"]["children"][0]

                    if post_first_comment["data"]["distinguished"] is not None:
                        parent_id = post_first_comment["data"]["name"]

                reddit.comment("\n\n".join(mirrors), parent_id)

            else:
                print("Failed to create any mirror for " +
                      post['data']['name'])

        print("Sleeping for 120 seconds!")
        sleep(120)


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
    __parse_args(parser.parse_args())

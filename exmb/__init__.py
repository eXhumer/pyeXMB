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
    "(" + " OR ".join((
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
    )) + ")",
    "(" + " OR ".join((
        f"flair:{flair}"
        for flair
        in (
            "Video",
            "Highlight",
            '":post-video: Video"',
            "DoeEensGek",
            "asd241",
            "sefn19",
        )
    )) + ")",
))


def __run_bot(auth_alias: str, **listing_kwargs: str | int):
    kwargs = {}

    for key, val in listing_kwargs.items():
        if key in ("after", "before", "limit", "count") and val is not None:
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

    while True:
        res = reddit.search(
            __highlight_search_query__,
            subreddit="formula1",
            show="all",
            type="link",
            **kwargs,
        )

        highlight_posts_listing = []

        # Search all highlight posts
        while True:
            highlight_posts_listing.extend(res.json()["data"]["children"])

            if res.json()["data"]["after"] is None:
                break

            kwargs.update({
                "after": res.json()["data"]["after"],
                "before": None,
            })

            res = reddit.search(
                __highlight_search_query__,
                subreddit="formula1",
                show="all",
                type="link",
                **kwargs,
            )

        if res.json()["data"]["dist"] != 0:
            kwargs.update({
                "after": None,
                "before": res.json()["data"]["children"][0]["data"]["name"],
            })

        print(len(highlight_posts_listing))

        for post in highlight_posts_listing:
            vid_url: str = post["data"]["url"]
            mirrors = []

            if vid_url.startswith("https://streamable.com/"):
                streamwo_id = vid_url.split("https://streamable.com/")[1]

                media_url = get_streamable_video_url(
                    session,
                    streamwo_id,
                )

                if media_url is not None:
                    media_data = BytesIO(session.get(media_url).content)

                    mirrors.extend([
                        streamable.clip_video(
                            streamwo_id,
                            mirror_title=post["data"]["title"],
                        ),
                        juststreamlive.mirror_streamable_video(streamwo_id),
                        streamja.upload_video(
                            media_data,
                            post["data"]["title"] + ".mp4",
                        ),
                        streamwo.upload_video(
                            media_data,
                            post["data"]["title"] + ".mp4",
                        ),
                    ])

                else:
                    continue

            elif vid_url.startswith("https://streamja.com/"):
                streamja_id = vid_url.split("https://streamwo.com/")[1]

                media_url = get_streamja_video_url(
                    session,
                    streamja_id,
                )

                if media_url is not None:
                    media_data = BytesIO(session.get(media_url).content)

                    mirrors.extend([
                        streamable.clip_streamwo_video(
                            streamwo_id,
                            mirror_title=post["data"]["title"],
                        ),
                        juststreamlive.mirror_streamwo_video(streamwo_id),
                        streamja.upload_video(
                            media_data,
                            post["data"]["title"] + ".mp4",
                        ),
                        streamwo.upload_video(
                            media_data,
                            post["data"]["title"] + ".mp4",
                        ),
                    ])

                else:
                    continue

            elif vid_url.startswith("https://streamwo.com/"):
                streamwo_id = vid_url.split("https://streamwo.com/")[1]

                if streamja_id.startswith("embed/"):
                    streamwo_id = vid_url.split("embed/")[1]

                media_url = get_streamwo_video_url(
                    session,
                    streamwo_id,
                )

                if media_url is not None:
                    media_data = BytesIO(session.get(media_url).content)

                    mirrors.extend([
                        streamable.clip_streamwo_video(
                            streamwo_id,
                            mirror_title=post["data"]["title"],
                        ),
                        juststreamlive.mirror_streamwo_video(streamwo_id),
                        streamja.upload_video(
                            media_data,
                            post["data"]["title"] + ".mp4",
                        ),
                        streamwo.upload_video(
                            media_data,
                            post["data"]["title"] + ".mp4",
                        ),
                    ])

                else:
                    continue

            else:
                continue

            if len(mirrors) > 0:
                res = reddit.comments(
                    post["data"]["id"],
                    limit=1,
                    subreddit="formula1",
                )

                comment = res.json()[1]["data"]["children"][0]

                [
                    streamable_mirror,
                    juststreamlive_mirror,
                    streamja_mirror,
                    streamwo_mirror,
                ] = mirrors

                mirrors = []

                if (
                    streamable_mirror.status_code == 200
                    and streamable_mirror.json()["error"] is None
                ):
                    mirrors.append(streamable_mirror.json()["url"])

                if juststreamlive_mirror.status_code == 200:
                    jsl_mid = juststreamlive_mirror.json()["id"]
                    mirrors.append(f"https://juststream.live/{jsl_mid}")

                if (
                    streamja_mirror.status_code == 200
                    and streamja_mirror.json()["status"] == 1
                ):
                    sja_mid = streamja_mirror.json()["url"]
                    mirrors.append(f"https://streamja.com/embed{sja_mid}")

                if streamwo_mirror.status_code == 200:
                    mirrors.append(
                        f"https://streamwo.com/{streamwo_mirror.text}",
                    )

                reddit.comment(
                    "\n\n".join(mirrors),
                    post["data"]["name"]
                    if comment["data"]["distinguished"] is None
                    else comment["data"]["name"],
                )

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
                after=args.after,
                count=args.count,
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
    run_parser.add_argument("--after")
    run_parser.add_argument("--count", type=int)
    run_parser.add_argument("--limit", type=int)
    __parse_args(parser.parse_args())

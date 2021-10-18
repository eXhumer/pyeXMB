# eXMB - Bot to mirror r/formula highlight clips
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

"""Bot module to mirror r/formula highlight clips"""
from argparse import ArgumentParser, Namespace
from pathlib import Path
from pkg_resources import require

from exrc.client import OAuth2Client
from exvhp.service import Imgur, JustStreamLive, Streamable, Streamja, Streamwo
from requests import Session

__version__ = require(__package__)[0].version
__config_path__ = Path.home() / ".config" / __package__
__user_agent__ = f"{__package__}/{__version__}"
__reddit_search_query__ = " AND ".join((
    " OR ".join((
        f"author:{author}"
        for author
        in (
            "ContentPuff",
            "magony",
            "sefn19",
            "DoeEensGek",
            "asd241",
            "sefn19",
        )
    )),
    " OR ".join((
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
    )),
))


def __run_bot(auth_alias: str):
    session = Session()
    session.headers["User-Agent"] = __user_agent__
    reddit = OAuth2Client.load_from_file(
        __config_path__ / f"{auth_alias}.json",
        session=session,
    )
    imgur = Imgur(session=session)
    juststreamlive = JustStreamLive(session=session)
    streamable = Streamable(session=session)
    streamja = Streamja(session=session)
    streamwo = Streamwo(session=session)

    # TODO: Scan for highlight posts from Reddit
    # TODO: Check searched posts for supported hosts and mirror
    # TODO: Submit mirrors to Reddit
    # Loop process until keyboard interrupt


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
            __run_bot(args.alias)

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
    __parse_args(parser.parse_args())

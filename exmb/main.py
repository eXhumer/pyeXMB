from argparse import ArgumentParser, Namespace
from pathlib import Path

from . import __config_path__
from .client import BotClient


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
                BotClient.reddit_auth_new_user_localserver_code_flow(
                    args.alias,
                    args.client_id,
                    args.duration,
                    args.scopes.split(" "),
                    callback_url=args.callback_url,
                    client_secret=args.client_secret,
                    state=args.state,
                ).reddit_save_to_file()

            else:
                raise FileExistsError(
                    f"Authorization already exists with alias {args.alias}!",
                )

        elif args.auth_action == "revoke":
            if (__config_path__ / f"{args.alias}.json").is_file():
                BotClient.reddit_load_existing_user(args.alias).reddit_revoke()
                (__config_path__ / f"{args.alias}.json").unlink()

            else:
                raise KeyError(
                    f"No authorization alias with key {args.alias} found!",
                )

        else:
            raise ValueError(f'Invalid auth action "{args.auth_action}"!')

    elif args.action == "run-bot":
        if (__config_path__ / f"{args.alias}.json").is_file():
            BotClient.reddit_load_existing_user(
                args.alias
            ).run_bot_for_subreddit(
                args.subreddit if args.subreddit else "formula1",
                mixture_mirror=args.mixture_mirror,
                streamwo_mirror=args.streamwo_mirror,
                before=args.before,
                limit=args.limit,
            )

        else:
            raise KeyError(
                f"No authorization alias with key {args.alias} found!",
            )

    elif args.action == "mirror-for-post":
        if (__config_path__ / f"{args.alias}.json").is_file():
            BotClient.reddit_load_existing_user(
                args.alias
            ).mirror_for_posts_by_id(
                args.post_ids,
                subreddit=args.subreddit,
                mixture_mirror=args.mixture_mirror,
                streamwo_mirror=args.streamwo_mirror,
            )

        else:
            raise KeyError(
                f"No authorization alias with key {args.alias} found!",
            )

    elif args.action == "post-juststreamlive":
        if (__config_path__ / f"{args.alias}.json").is_file():
            BotClient.reddit_load_existing_user(
                args.alias
            ).post_juststreamlive(
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
            BotClient.reddit_load_existing_user(
                args.alias
            ).post_streamable(
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
            BotClient.reddit_load_existing_user(
                args.alias
            ).post_streamja(
                args.media_path,
                args.title,
                subreddit=args.subreddit,
                flair_id=args.flair_id,
            )

        else:
            raise KeyError(
                f"No authorization alias with key {args.alias} found!",
            )

    elif args.action == "post-mixture":
        if (__config_path__ / f"{args.alias}.json").is_file():
            BotClient.reddit_load_existing_user(
                args.alias
            ).post_mixture(
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
            BotClient.reddit_load_existing_user(
                args.alias
            ).post_streamwo(
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
            BotClient.reddit_load_existing_user(
                args.alias
            ).post_streamff(
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
    run_parser.add_argument("--mixture-mirror", action="store_true")
    run_parser.add_argument("--streamwo-mirror", action="store_true")
    mirror_for_post_parser = subparsers.add_parser("mirror-for-post")
    mirror_for_post_parser.add_argument("alias")
    mirror_for_post_parser.add_argument(
        "post_ids", metavar="post_id", nargs="+",
    )
    mirror_for_post_parser.add_argument(
        "--mixture-mirror", action="store_true",
    )
    mirror_for_post_parser.add_argument(
        "--streamwo-mirror", action="store_true",
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
    post_mixture_parser = subparsers.add_parser("post-mixture")
    post_mixture_parser.add_argument("alias")
    post_mixture_parser.add_argument("media_path", type=Path)
    post_mixture_parser.add_argument("title")
    post_mixture_parser.add_argument("--subreddit")
    post_mixture_parser.add_argument("--flair-id")
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

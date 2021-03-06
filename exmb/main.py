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
                reddit_mirror=args.reddit_mirror,
                streamff_mirror=args.streamff_mirror,
                before=args.before,
                limit=args.limit,
                skip_missing_automod=args.skip_missing_automod,
                max_processing_attempts=10,
                minimum_retry_interval=5,
                interval=5,
            )

        else:
            raise KeyError(
                f"No authorization alias with key {args.alias} found!",
            )

    elif args.action == "mirror-for-post":
        if (__config_path__ / f"{args.alias}.json").is_file():
            BotClient.reddit_load_existing_user(
                args.alias
            ).mirror_for_posts_by_names(
                args.post_names,
                subreddit=args.subreddit,
                juststreamlive_mirror=args.juststreamlive_mirror,
                streamff_mirror=args.streamff_mirror,
                reddit_mirror=args.reddit_mirror,
                skip_missing_automod=args.skip_missing_automod,
                max_processing_attempts=10,
                minimum_retry_interval=5,
            )

        else:
            raise KeyError(
                f"No authorization alias with key {args.alias} found!",
            )

    elif args.action == "post-imgur":
        if (__config_path__ / f"{args.alias}.json").is_file():
            BotClient.reddit_load_existing_user(
                args.alias
            ).post_imgur(
                args.media_path,
                args.title,
                subreddit=args.subreddit,
                flair_id=args.flair_id,
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

    elif args.action == "post-reddit":
        if (__config_path__ / f"{args.alias}.json").is_file():
            BotClient.reddit_load_existing_user(
                args.alias
            ).post_reddit(
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
    auth_new_parser.add_argument("--duration",
                                 choices=["temporary", "permanent"])
    auth_new_parser.add_argument("--state")
    auth_subparsers.add_parser("list")
    auth_revoke_parser = auth_subparsers.add_parser("revoke")
    auth_revoke_parser.add_argument("alias")
    run_parser = subparsers.add_parser("run-bot")
    run_parser.add_argument("alias")
    run_parser.add_argument("--before")
    run_parser.add_argument("--limit", type=int)
    run_parser.add_argument("--subreddit")
    run_parser.add_argument("--reddit-mirror")
    run_parser.add_argument("--juststreamlive-mirror", action="store_true")
    run_parser.add_argument("--streamff-mirror", action="store_true")
    run_parser.add_argument("--skip-missing-automod", action="store_true")
    mirror_for_post_parser = subparsers.add_parser("mirror-for-post")
    mirror_for_post_parser.add_argument("alias")
    mirror_for_post_parser.add_argument("post_names", metavar="post_name",
                                        nargs="+")
    mirror_for_post_parser.add_argument("--reddit-mirror")
    mirror_for_post_parser.add_argument("--juststreamlive-mirror",
                                        action="store_true")
    mirror_for_post_parser.add_argument("--streamff-mirror",
                                        action="store_true")
    mirror_for_post_parser.add_argument("--subreddit")
    mirror_for_post_parser.add_argument("--skip-missing-automod",
                                        action="store_true")
    post_imgur_parser = subparsers.add_parser("post-imgur")
    post_imgur_parser.add_argument("alias")
    post_imgur_parser.add_argument("media_path", type=Path)
    post_imgur_parser.add_argument("title")
    post_imgur_parser.add_argument("--subreddit")
    post_imgur_parser.add_argument("--flair-id")
    post_juststreamlive_parser = subparsers.add_parser("post-juststreamlive")
    post_juststreamlive_parser.add_argument("alias")
    post_juststreamlive_parser.add_argument("media_path", type=Path)
    post_juststreamlive_parser.add_argument("title")
    post_juststreamlive_parser.add_argument("--subreddit")
    post_juststreamlive_parser.add_argument("--flair-id")
    post_reddit_parser = subparsers.add_parser("post-reddit")
    post_reddit_parser.add_argument("alias")
    post_reddit_parser.add_argument("media_path", type=Path)
    post_reddit_parser.add_argument("title")
    post_reddit_parser.add_argument("--subreddit")
    post_reddit_parser.add_argument("--flair-id")
    post_streamable_parser = subparsers.add_parser("post-streamable")
    post_streamable_parser.add_argument("alias")
    post_streamable_parser.add_argument("media_path", type=Path)
    post_streamable_parser.add_argument("title")
    post_streamable_parser.add_argument("--subreddit")
    post_streamable_parser.add_argument("--flair-id")
    post_streamff_parser = subparsers.add_parser("post-streamff")
    post_streamff_parser.add_argument("alias")
    post_streamff_parser.add_argument("media_path", type=Path)
    post_streamff_parser.add_argument("title")
    post_streamff_parser.add_argument("--subreddit")
    post_streamff_parser.add_argument("--flair-id")
    post_streamja_parser = subparsers.add_parser("post-streamja")
    post_streamja_parser.add_argument("alias")
    post_streamja_parser.add_argument("media_path", type=Path)
    post_streamja_parser.add_argument("title")
    post_streamja_parser.add_argument("--subreddit")
    post_streamja_parser.add_argument("--flair-id")

    __parse_args(parser.parse_args())

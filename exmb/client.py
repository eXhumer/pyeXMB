from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from queue import Queue
from time import sleep
from typing import Any, Dict, List

from exrc.client import OAuth2Client
from exvhp import (
    Client as VHPClient,
    MixtureVideo,
    StreamableVideo,
    StreamffVideo,
    StreamjaVideo,
    StreamwoVideo,
)
from requests import Session

from . import (
    __config_path__,
    __user_agent__,
    JUSTSTREAMLIVE_MAX_SIZE,
    MIXTURE_MAX_SIZE,
    STREAMABLE_MAX_SIZE,
    STREAMFF_MAX_SIZE,
    STREAMJA_MAX_SIZE,
    STREAMWO_MAX_SIZE,
)


class BotClient:
    def __init__(
        self,
        exrc: OAuth2Client,
        exvhp: VHPClient,

    ) -> None:
        self.__reddit_client = exrc
        self.__vhp_client = exvhp

    def __post_deleted(self, subreddit: str, post_id: str):
        res = self.__reddit_client.info(
            ids=[post_id],
            subreddit=subreddit,
        )
        res.raise_for_status()

        latest_post = res.json()["data"]["children"][0]
        post_removal_status = latest_post["data"]["removed_by_category"]
        return post_removal_status is not None

    def __get_latest_post_name(self, subreddit: str):
        res = self.__reddit_client.posts(
            subreddit=subreddit,
            sort="new",
            limit=1,
        )
        res.raise_for_status()

        if res.json()["data"]["dist"] == 0:
            raise ValueError(f"No posts in {subreddit}!")

        latest_post = res.json()["data"]["children"][0]
        latest_postname: str = latest_post["data"]["name"]

        return latest_postname

    @classmethod
    def reddit_auth_new_user_localserver_code_flow(
        cls,
        auth_alias: str,
        client_id: str,
        duration: str,
        scopes: List[str],
        callback_url: str = "http://localhost:65010/auth_callback",
        client_secret: str = "",
        state: str | None = None,
        user_agent: str | None = None,
    ):
        session = Session()
        session.headers["User-Agent"] = (
            __user_agent__ if user_agent is None else user_agent
        )

        return cls(
            OAuth2Client.localserver_code_flow(
                client_id,
                client_secret,
                callback_url,
                duration,
                scopes,
                state=state,
                token_path=__config_path__ / f"{auth_alias}.json",
                session=session,
            ),
            VHPClient(session=session),
        )

    @classmethod
    def reddit_load_existing_user(
        cls,
        auth_alias: str,
        user_agent: str | None = None,
    ):
        session = Session()
        session.headers["User-Agent"] = (
            __user_agent__ if user_agent is None else user_agent
        )

        return cls(
            OAuth2Client.load_from_file(
                __config_path__ / f"{auth_alias}.json",
            ),
            VHPClient(session=session),
        )

    def reddit_revoke(self):
        return self.__reddit_client.revoke()

    def reddit_save_to_file(self):
        self.__reddit_client.save_to_file()

    def run_bot_for_subreddit(
        self,
        subreddit: str,
        mixture_mirror: bool = False,
        streamwo_mirror: bool = False,
        before: str | None = None,
        limit: int | None = None,
        interval: int = 5,
        skip_missing_automod: bool = False,
    ):
        if not before:
            print("before not specified! Attempting to retrieve latest " +
                  "post name")
            before = self.__get_latest_post_name(subreddit)
            print(f"Latest post name: {before}")

        mirror_postname_stack = deque()

        while True:
            print(f"Checking if latest post {before} has been removed/deleted")

            if self.__post_deleted(subreddit, before):
                print(f"Post {before} was removed/deleted!")
                print("Attempting to use last non removed/deleted highlight " +
                      "post!")

                if len(mirror_postname_stack):
                    try:
                        while True:
                            last_mirror_postname = mirror_postname_stack.pop()

                            if self.__post_deleted(
                                subreddit,
                                last_mirror_postname,
                            ):
                                continue

                            mirror_postname_stack.append(last_mirror_postname)
                            print("Found non removed/deleted mirrored " +
                                  "highlight post!")
                            print("Setting latest post as " +
                                  last_mirror_postname)
                            before = last_mirror_postname
                            break

                    except IndexError:
                        print("All mirrored posts were deleted/removed!")
                        before = self.__get_latest_post_name(subreddit)
                        print(f"Setting latest post as {before}")

                else:
                    print("No previous mirrored highlight post found!")
                    before = self.__get_latest_post_name(subreddit)
                    print(f"Setting latest post as {before}")

            print(f"Retrieving all posts before post name {before}")

            params = {}
            params.update(before=before)

            if limit:
                params.update(limit=limit)

            highlight_posts = []

            while True:
                res = self.__reddit_client.posts(
                    subreddit=subreddit,
                    sort="new",
                    before=before,
                    limit=limit,
                )
                res.raise_for_status()

                if res.json()["data"]["dist"] == 0:
                    break

                subreddit_listing_posts = res.json()["data"]["children"]

                for post in reversed(subreddit_listing_posts):
                    if post["data"]["url"].startswith((
                        "https://mixture.gg/v/",
                        "https://streamable.com/",
                        "https://streamff.com/v/",
                        "https://streamja.com/",
                        "https://streamwo.com/file/",
                    )):
                        res = self.__reddit_client.comments(
                            post["data"]["id"],
                            subreddit=post["data"]["subreddit"],
                            limit=1,
                        )
                        res.raise_for_status()

                        if (
                            len(res.json()) == 2
                            and len(res.json()[1]["data"]["children"]) > 0
                        ):
                            post_first_comment = \
                                res.json()[1]["data"]["children"][0]

                            if (("stickied" not in post_first_comment["data"]
                                    or post_first_comment["data"]["stickied"]
                                    is False) and skip_missing_automod):
                                continue

                        elif skip_missing_automod:
                            continue

                        mirror_postname_stack.append(post["data"]["name"])
                        highlight_posts.append(post)

                before = subreddit_listing_posts[0]["data"]["name"]
                params.update(before=before)

            self.__mirror_for_posts(
                highlight_posts,
                mixture_mirror=mixture_mirror,
                streamwo_mirror=streamwo_mirror,
            )

            print(f"Sleeping for {interval} seconds!")
            sleep(interval)

    def __mirror_for_posts(
        self,
        highlight_posts: List[Dict[str, Any]],
        max_processing_attempts: int = 10,
        minimum_retry_interval: int = 5,
        mixture_mirror: bool = False,
        streamwo_mirror: bool = False,
    ):
        post_queue = Queue()

        for post in highlight_posts:
            post_queue.put({"post": post, "attempts": 0, "last_attempt": None})

        while not post_queue.empty():
            post_data = post_queue.get()
            post = post_data["post"]
            vid_url: str = post["data"]["url"]

            if not vid_url.startswith((
                "https://mixture.gg/v/",
                "https://streamable.com/",
                "https://streamff.com/v/",
                "https://streamja.com/",
                "https://streamwo.com/file/",
            )):
                print(
                    f"Post {post['data']['name']} with unsupported video host!"
                )
                continue

            if vid_url.startswith("https://mixture.gg/v/"):
                link_id = vid_url.split("https://mixture.gg/v/")[1]
                print(f"Processing {post['data']['name']} with Mixture " +
                      f"Video {link_id}")

                if not self.__vhp_client.mixture.is_video_available(link_id):
                    print("Unable to get direct video link from Mixture " +
                          f"video ID {link_id}. Video not available / " +
                          "taken down!")
                    continue

                if post_data["attempts"] < max_processing_attempts:
                    last_attempt: datetime

                    if (
                        last_attempt := post_data["last_attempt"]
                    ) is not None and (
                        datetime.now(tz=timezone.utc) - last_attempt
                    ).seconds < minimum_retry_interval:
                        print(f"Attempting Mixture Video {link_id} " +
                              "mirror too quickly since last try! Must wait " +
                              f"{minimum_retry_interval} seconds between " +
                              "each attempt!")
                        post_queue.put(post_data)
                        continue

                    if self.__vhp_client.mixture.is_video_processing(link_id):
                        post_data["last_attempt"] = \
                            datetime.now(tz=timezone.utc)
                        print(f"Mixture Video {link_id} still " +
                              "being processed, trying later!")
                        post_data["attempts"] += 1
                        post_queue.put(post_data)
                        continue

                else:
                    print(f"Mixture Video {link_id} still " +
                          "being processed! Max attempts reached, " +
                          "ignoring video!")
                    continue

                media_data = \
                    self.__vhp_client.mixture.get_video_content(link_id)

                if media_data.getbuffer().nbytes <= JUSTSTREAMLIVE_MAX_SIZE:
                    jsl_mirror = self.__vhp_client.juststreamlive.mirror_video(
                        MixtureVideo(link_id=link_id),
                    )

                if (
                    mixture_mirror
                    and media_data.getbuffer().nbytes <= MIXTURE_MAX_SIZE
                ):
                    mix_mirror = self.__vhp_client.mixture.upload_video(
                        media_data, "Mirror.mp4",
                    )

                if media_data.getbuffer().nbytes <= STREAMABLE_MAX_SIZE:
                    sab_mirror = self.__vhp_client.streamable.mirror_video(
                        MixtureVideo(link_id=link_id),
                        title=post["data"]["title"],
                    )

                if media_data.getbuffer().nbytes <= STREAMFF_MAX_SIZE:
                    sff_mirror = self.__vhp_client.streamff.upload_video(
                        media_data, "Mirror.mp4",
                    )

                if media_data.getbuffer().nbytes <= STREAMJA_MAX_SIZE:
                    sja_mirror = self.__vhp_client.streamja.upload_video(
                        media_data, "Mirror.mp4",
                    )

                if (
                    streamwo_mirror
                    and media_data.getbuffer().nbytes <= STREAMWO_MAX_SIZE
                ):
                    swo_mirror = self.__vhp_client.streamwo.upload_video(
                        media_data, "Mirror.mp4",
                    )

            elif vid_url.startswith("https://streamable.com/"):
                shortcode = vid_url.split("https://streamable.com/")[1]
                print(f"Processing {post['data']['name']} with Streamable " +
                      f"Video {shortcode}")

                if not self.__vhp_client.streamable.is_video_available(
                    shortcode
                ):
                    print("Unable to get direct video link from Streamable " +
                          f"video ID {shortcode}. Video not available / " +
                          "taken down!")
                    continue

                if post_data["attempts"] < max_processing_attempts:
                    last_attempt: datetime

                    if (
                        last_attempt := post_data["last_attempt"]
                    ) is not None and (
                        datetime.now(tz=timezone.utc) - last_attempt
                    ).seconds < minimum_retry_interval:
                        print(f"Attempting Streamable Video {shortcode} " +
                              "mirror too quickly since last try! Must wait " +
                              f"{minimum_retry_interval} seconds between " +
                              "each attempt!")
                        post_queue.put(post_data)
                        continue

                    if self.__vhp_client.streamable.is_video_processing(
                        shortcode,
                    ):
                        post_data["last_attempt"] = \
                            datetime.now(tz=timezone.utc)
                        print(f"Streamable Video {shortcode} still " +
                              "being processed, trying later!")
                        post_data["attempts"] += 1
                        post_queue.put(post_data)
                        continue

                else:
                    print(f"Streamable Video {shortcode} still " +
                          "being processed! Max attempts reached, " +
                          "ignoring video!")
                    continue

                media_data = \
                    self.__vhp_client.streamable.get_video_content(shortcode)

                if media_data.getbuffer().nbytes <= JUSTSTREAMLIVE_MAX_SIZE:
                    jsl_mirror = self.__vhp_client.juststreamlive.mirror_video(
                        StreamableVideo(shortcode=shortcode),
                    )

                if (
                    mixture_mirror
                    and media_data.getbuffer().nbytes <= MIXTURE_MAX_SIZE
                ):
                    mix_mirror = self.__vhp_client.mixture.upload_video(
                        media_data, "Mirror.mp4",
                    )

                if media_data.getbuffer().nbytes <= STREAMABLE_MAX_SIZE:
                    sab_mirror = self.__vhp_client.streamable.mirror_video(
                        StreamableVideo(shortcode=shortcode),
                        title=post["data"]["title"],
                    )

                if media_data.getbuffer().nbytes <= STREAMJA_MAX_SIZE:
                    sja_mirror = self.__vhp_client.streamja.upload_video(
                        media_data, "Mirror.mp4",
                    )

                if media_data.getbuffer().nbytes <= STREAMFF_MAX_SIZE:
                    sff_mirror = self.__vhp_client.streamff.upload_video(
                        media_data, "Mirror.mp4",
                    )

                if (
                    streamwo_mirror
                    and media_data.getbuffer().nbytes <= STREAMWO_MAX_SIZE
                ):
                    swo_mirror = self.__vhp_client.streamwo.upload_video(
                        media_data, "Mirror.mp4",
                    )

            elif vid_url.startswith("https://streamja.com/"):
                short_id = vid_url.split("https://streamja.com/")[1]

                if short_id.startswith("embed/"):
                    short_id = vid_url.split("embed/")[1]

                print(f"Processing {post['data']['name']} with Streamja " +
                      f"Video {short_id}")

                if not self.__vhp_client.streamja.is_video_available(
                    short_id
                ):
                    print("Unable to get direct video link from Streamja " +
                          f"video ID {short_id}. Video not available / " +
                          "taken down!")
                    continue

                if post_data["attempts"] < max_processing_attempts:
                    last_attempt: datetime

                    if (
                        last_attempt := post_data["last_attempt"]
                    ) is not None and (
                        datetime.now(tz=timezone.utc) - last_attempt
                    ).seconds < minimum_retry_interval:
                        print(f"Attempting Streamja Video {short_id} " +
                              "mirror too quickly since last try! Must wait " +
                              f"{minimum_retry_interval} seconds between " +
                              "each attempt!")
                        post_queue.put(post_data)
                        continue

                    if self.__vhp_client.streamja.is_video_processing(
                        short_id
                    ):
                        post_data["last_attempt"] = \
                            datetime.now(tz=timezone.utc)
                        print(f"Streamja Video {short_id} still being " +
                              "processed, trying later!")
                        post_data["attempts"] += 1
                        post_queue.put(post_data)
                        continue

                else:
                    print(f"Streamja Video {short_id} still being processed!" +
                          " Max attempts reached, ignoring video!")
                    continue

                media_data = self.__vhp_client.streamja.get_video_content(
                    short_id
                )

                if media_data.getbuffer().nbytes <= JUSTSTREAMLIVE_MAX_SIZE:
                    jsl_mirror = self.__vhp_client.juststreamlive.mirror_video(
                        StreamjaVideo(short_id=short_id),
                    )

                if (
                    mixture_mirror
                    and media_data.getbuffer().nbytes <= MIXTURE_MAX_SIZE
                ):
                    mix_mirror = self.__vhp_client.mixture.upload_video(
                        media_data, "Mirror.mp4",
                    )

                if media_data.getbuffer().nbytes <= STREAMABLE_MAX_SIZE:
                    sab_mirror = self.__vhp_client.streamable.mirror_video(
                        StreamjaVideo(short_id=short_id),
                        title=post["data"]["title"],
                    )

                if media_data.getbuffer().nbytes <= STREAMFF_MAX_SIZE:
                    sff_mirror = self.__vhp_client.streamff.upload_video(
                        media_data, "Mirror.mp4",
                    )

                if media_data.getbuffer().nbytes <= STREAMJA_MAX_SIZE:
                    sja_mirror = self.__vhp_client.streamja.upload_video(
                        media_data, "Mirror.mp4",
                    )

                if (
                    streamwo_mirror
                    and media_data.getbuffer().nbytes <= STREAMWO_MAX_SIZE
                ):
                    swo_mirror = self.__vhp_client.streamwo.upload_video(
                        media_data, "Mirror.mp4",
                    )

            elif vid_url.startswith("https://streamff.com/v/"):
                streamff_id = vid_url.split("https://streamff.com/v/")[1]
                print(f"Processing {post['data']['name']} with Streamff " +
                      f"Video {streamff_id}")

                media_data = \
                    self.__vhp_client.streamff.get_video_content(streamff_id)

                if media_data.getbuffer().nbytes <= JUSTSTREAMLIVE_MAX_SIZE:
                    jsl_mirror = self.__vhp_client.juststreamlive.upload_video(
                        media_data,
                        "Mirror.mp4",
                    )

                if (
                    mixture_mirror
                    and media_data.getbuffer().nbytes <= MIXTURE_MAX_SIZE
                ):
                    mix_mirror = self.__vhp_client.mixture.upload_video(
                        media_data,
                        "Mirror.mp4",
                    )

                if media_data.getbuffer().nbytes <= STREAMABLE_MAX_SIZE:
                    sab_mirror = self.__vhp_client.streamable.mirror_video(
                        StreamffVideo(id=streamff_id),
                        title=post["data"]["title"],
                    )

                if media_data.getbuffer().nbytes <= STREAMFF_MAX_SIZE:
                    sff_mirror = self.__vhp_client.streamja.upload_video(
                        media_data,
                        "Mirror.mp4",
                    )

                if media_data.getbuffer().nbytes <= STREAMJA_MAX_SIZE:
                    sja_mirror = self.__vhp_client.streamja.upload_video(
                        media_data,
                        "Mirror.mp4",
                    )

                if (
                    streamwo_mirror
                    and media_data.getbuffer().nbytes <= STREAMWO_MAX_SIZE
                ):
                    mix_mirror = self.__vhp_client.streamwo.upload_video(
                        media_data,
                        "Mirror.mp4",
                    )

            elif vid_url.startswith("https://streamwo.com/file/"):
                link_id = vid_url.split("https://streamwo.com/file/")[1]
                print(f"Processing {post['data']['name']} with Streamwo " +
                      f"Video {link_id}")

                if not self.__vhp_client.streamwo.is_video_available(link_id):
                    print("Unable to get direct video link from Streamwo " +
                          f"video ID {link_id}. Video not available / " +
                          "taken down!")
                    continue

                if post_data["attempts"] < max_processing_attempts:
                    last_attempt: datetime

                    if (
                        last_attempt := post_data["last_attempt"]
                    ) is not None and (
                        datetime.now(tz=timezone.utc) - last_attempt
                    ).seconds < minimum_retry_interval:
                        print(f"Attempting Streamwo Video {link_id} " +
                              "mirror too quickly since last try! Must wait " +
                              f"{minimum_retry_interval} seconds between " +
                              "each attempt!")
                        post_queue.put(post_data)
                        continue

                    if self.__vhp_client.streamwo.is_video_processing(link_id):
                        post_data["last_attempt"] = \
                            datetime.now(tz=timezone.utc)
                        print(f"Streamwo Video {link_id} still " +
                              "being processed, trying later!")
                        post_data["attempts"] += 1
                        post_queue.put(post_data)
                        continue

                else:
                    print(f"Streamwo Video {link_id} still " +
                          "being processed! Max attempts reached, " +
                          "ignoring video!")
                    continue

                media_data = \
                    self.__vhp_client.streamwo.get_video_content(link_id)

                if media_data.getbuffer().nbytes <= JUSTSTREAMLIVE_MAX_SIZE:
                    jsl_mirror = self.__vhp_client.juststreamlive.mirror_video(
                        StreamwoVideo(link_id=link_id),
                    )

                if (
                    mixture_mirror
                    and media_data.getbuffer().nbytes <= MIXTURE_MAX_SIZE
                ):
                    mix_mirror = self.__vhp_client.mixture.upload_video(
                        media_data, "Mirror.mp4",
                    )

                if media_data.getbuffer().nbytes <= STREAMABLE_MAX_SIZE:
                    sab_mirror = self.__vhp_client.streamable.mirror_video(
                        MixtureVideo(link_id=link_id),
                        title=post["data"]["title"],
                    )

                if media_data.getbuffer().nbytes <= STREAMFF_MAX_SIZE:
                    sff_mirror = self.__vhp_client.streamff.upload_video(
                        media_data, "Mirror.mp4",
                    )

                if media_data.getbuffer().nbytes <= STREAMJA_MAX_SIZE:
                    sja_mirror = self.__vhp_client.streamja.upload_video(
                        media_data, "Mirror.mp4",
                    )

                if (
                    streamwo_mirror
                    and media_data.getbuffer().nbytes <= STREAMWO_MAX_SIZE
                ):
                    swo_mirror = self.__vhp_client.streamwo.upload_video(
                        media_data, "Mirror.mp4",
                    )

            else:
                assert False, "Should be unreachable!"

            mirrors = []

            if media_data.getbuffer().nbytes <= STREAMABLE_MAX_SIZE:
                print("Streamable mirror created for " +
                      f"{post['data']['name']}!")
                mirrors.append(f"* [Streamable]({str(sab_mirror.url)})")

            else:
                print("Streamable mirror failed for " +
                      f"{post['data']['name']} as it is too large!")
                mirrors.append("* Streamable: Failed as video file too " +
                               "large for host")

            if media_data.getbuffer().nbytes <= JUSTSTREAMLIVE_MAX_SIZE:
                print("JustStreamLive mirror created for " +
                      f"{post['data']['name']}!")
                mirrors.append(f"* [JustStreamLive]({str(jsl_mirror.url)})")

            else:
                print("JustStreamLive mirror failed for " +
                      f"{post['data']['name']} as it is too large!")
                mirrors.append("* JustStreamLive: Failed as video file too " +
                               "large for host")

            if media_data.getbuffer().nbytes <= STREAMJA_MAX_SIZE:
                print(f"Streamja mirror created for {post['data']['name']}!")
                mirrors.append(
                    "* " + " | ".join((
                        f"[Streamja Embed]({str(sja_mirror.embed_url)})",
                        f"[Streamja Non-Embed]({str(sja_mirror.url)})",
                    )),
                )

            else:
                print(f"Streamja mirror failed for {post['data']['name']} " +
                      "as it is too large!")
                mirrors.append("* Streamja: Failed as video file too large " +
                               "for host")

            if media_data.getbuffer().nbytes <= STREAMFF_MAX_SIZE:
                print(f"Streamff mirror created for  {post['data']['name']}!")
                mirrors.append(f"* [Streamff]({str(sff_mirror.url)})")

            else:
                print(f"Streamff mirror failed for {post['data']['name']} " +
                      "as it is too large!")
                mirrors.append("* Streamff: Failed as video file too large " +
                               "for host")

            if mixture_mirror:
                if media_data.getbuffer().nbytes <= MIXTURE_MAX_SIZE:
                    print("Mixture mirror created for " +
                          f"{post['data']['name']}!")
                    mirrors.append(f"* [Mixture]({str(mix_mirror.url)})")

                else:
                    print("Mixture mirror failed for " +
                          f"{post['data']['name']} as it is too large!")
                    mirrors.append("* Mixture: Failed as video file too " +
                                   "large for host")

            if streamwo_mirror:
                if media_data.getbuffer().nbytes <= STREAMWO_MAX_SIZE:
                    print("Streamwo mirror created for " +
                          f"{post['data']['name']}!")
                    mirrors.append(f"* [Streamwo]({str(swo_mirror.url)})")

                else:
                    print("Streamwo mirror failed for " +
                          f"{post['data']['name']} as it is too large!")
                    mirrors.append("* Streamwo: Failed as video file too " +
                                   "large for host")

            if len(mirrors) > 0:
                parent_id = post["data"]["name"]

                res = self.__reddit_client.comments(
                    post["data"]["id"],
                    subreddit=post["data"]["subreddit"],
                    limit=1,
                )
                res.raise_for_status()

                if (
                    len(res.json()) == 2
                    and len(res.json()[1]["data"]["children"]) > 0
                ):
                    post_first_comment = res.json()[1]["data"]["children"][0]

                    if "stickied" not in post_first_comment["data"]:
                        print("Stickied property not found for comment " +
                              f"{post_first_comment['data']['name']} under " +
                              f"post {parent_id}")

                    elif post_first_comment["data"]["stickied"] is True:
                        parent_id = post_first_comment["data"]["name"]

                    else:
                        print(f"No stickied comment under post {parent_id}")

                else:
                    print(f"No comments under post {parent_id}")

                self.__reddit_client.comment(
                    "\n\n".join([
                        "**Mirrors**",
                        *mirrors,
                        "---",
                        "^Powered ^by ^[pyeXMB](https://github.com/eXhumer/" +
                        "pyeXMB) ^| [^(Contact author incase of issue with " +
                        "mirrors)](https://www.reddit.com/message/compose?" +
                        "to=%2Fu%2FContentPuff&subject=Issue%20with%20" +
                        f"mirrors%20in%20post%20{post['data']['name']})"
                    ]),
                    parent_id,
                )

            else:
                print("Failed to create any mirror for " +
                      f"{post['data']['name']}")

    def mirror_for_posts_by_id(
        self,
        post_ids: List[str],
        subreddit: str | None = None,
        mixture_mirror: bool = False,
        streamwo_mirror: bool = False,
    ):
        res = self.__reddit_client.info(ids=post_ids, subreddit=subreddit)
        res.raise_for_status()

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

        self.__mirror_for_posts(
            res.json()["data"]["children"],
            mixture_mirror=mixture_mirror,
            streamwo_mirror=streamwo_mirror,
        )

    def post_juststreamlive(
        self,
        media_path: Path,
        post_title: str,
        subreddit: str | None = None,
        flair_id: str | None = None,
    ):
        video = self.__vhp_client.juststreamlive.upload_video(
            media_path.open(mode="rb"),
            media_path.name,
        )

        return self.__reddit_client.submit_url(
            post_title,
            str(video.url),
            subreddit=subreddit,
            flair_id=flair_id,
        )

    def post_streamable(
        self,
        media_path: Path,
        post_title: str,
        subreddit: str | None = None,
        flair_id: str | None = None,
        upload_region: str = "us-east-1",
    ):
        video = self.__vhp_client.streamable.upload_video(
            media_path.open(mode="rb"),
            media_path.name,
            title=post_title,
            upload_region=upload_region,
        )

        return self.__reddit_client.submit_url(
            post_title,
            str(video.url),
            subreddit=subreddit,
            flair_id=flair_id,
        )

    def post_streamja(
        self,
        media_path: Path,
        post_title: str,
        subreddit: str | None = None,
        flair_id: str | None = None,
    ):
        video = self.__vhp_client.streamja.upload_video(
            media_path.open(mode="rb"),
            media_path.name,
        )

        return self.__reddit_client.submit_url(
            post_title,
            str(video.url),
            subreddit=subreddit,
            flair_id=flair_id,
        )

    def post_mixture(
        self,
        media_path: Path,
        post_title: str,
        subreddit: str | None = None,
        flair_id: str | None = None,
    ):
        video = self.__vhp_client.mixture.upload_video(
            media_path.open(mode="rb"),
            media_path.name,
        )

        return self.__reddit_client.submit_url(
            post_title,
            str(video.url),
            subreddit=subreddit,
            flair_id=flair_id,
        )

    def post_streamwo(
        self,
        media_path: Path,
        post_title: str,
        subreddit: str | None = None,
        flair_id: str | None = None,
    ):
        video = self.__vhp_client.streamwo.upload_video(
            media_path.open(mode="rb"),
            media_path.name,
        )

        return self.__reddit_client.submit_url(
            post_title,
            str(video.url),
            subreddit=subreddit,
            flair_id=flair_id,
        )

    def post_streamff(
        self,
        media_path: Path,
        post_title: str,
        subreddit: str | None = None,
        flair_id: str | None = None,
    ):
        video = self.__vhp_client.streamff.upload_video(
            media_path.open(mode="rb"),
            media_path.name,
        )

        return self.__reddit_client.submit_url(
            post_title,
            str(video.url),
            subreddit=subreddit,
            flair_id=flair_id,
        )

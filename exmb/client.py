from collections import deque
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from queue import Queue
from time import sleep
from typing import Any, Dict, List

from exrc.client import OAuth2Client
from exvhp.client import (
    JustStreamLive, Mixture, Streamable, Streamja, Streamff,
)
from requests import Session

from . import (
    __config_path__,
    __user_agent__,
    JUSTSTREAMLIVE_MAX_SIZE,
    STREAMABLE_MAX_SIZE,
    STREAMFF_MAX_SIZE,
    STREAMJA_MAX_SIZE,
    MIXTURE_MAX_SIZE,
)


class BotClient:
    def __init__(
        self,
        reddit: OAuth2Client,
        juststreamlive: JustStreamLive,
        streamable: Streamable,
        streamja: Streamja,
        streamff: Streamff,
        mixture: Mixture,
    ) -> None:
        self.__reddit = reddit
        self.__juststreamlive = juststreamlive
        self.__streamable = streamable
        self.__streamja = streamja
        self.__streamff = streamff
        self.__mixture = mixture

    @classmethod
    def reddit_auth_new_user_localserver_code_flow(
        cls,
        auth_alias: str,
        client_id: str,
        duration: str,
        scopes: List[str],
        callback_url: str = "http://localhost:65010/auth_callback",
        client_secret: str | None = None,
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
                client_secret if client_secret else "",
                callback_url,
                duration,
                scopes,
                state=state,
                user_agent=__user_agent__,
                token_path=__config_path__ / f"{auth_alias}.json",
                session=session,
            ),
            JustStreamLive(session=session),
            Streamable(session=session),
            Streamja(session=session),
            Streamff(session=session),
            Mixture(session=session),
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
                __config_path__ / f"{auth_alias}.json"
            ),
            JustStreamLive(session=session),
            Streamable(session=session),
            Streamja(session=session),
            Streamff(session=session),
            Mixture(session=session),
        )

    def reddit_revoke(self):
        return self.__reddit.revoke()

    def reddit_save_to_file(self):
        self.__reddit.save_to_file()

    def run_bot_for_subreddit(
        self,
        subreddit: str,
        mixture_mirror: bool = False,
        **listing_kwargs: str | int,
    ):
        if "before" not in listing_kwargs or listing_kwargs["before"] is None:
            print("before not specified! attempting to retrieve latest " +
                  "post name")
            listing_kwargs["before"] = None

            if listing_kwargs["before"] is None:
                res = self.__reddit.get(
                    f"r/{subreddit}/new",
                    params={"limit": 1},
                )

                if not res.ok:
                    raise ValueError(
                        "Invalid response while trying to retrieve latest " +
                        "post name!",
                    )

                if res.json()["data"]["dist"] == 0:
                    raise Exception(f"Unable to any valid post in {subreddit}")

                listing_kwargs.update({
                    "before":
                        res.json()["data"]["children"][0]["data"]["name"],
                })

            print(f"Latest post name: {listing_kwargs['before']}")

        highlight_posts_stack = deque()

        while True:
            print(f"Checking if latest post {listing_kwargs['before']} " +
                  "has been removed/deleted")
            res = self.__reddit.info(
                ids=[listing_kwargs["before"]],
                subreddit=subreddit,
            )

            if not res.ok:
                raise ValueError(
                    "Invalid response while trying to check if latest post " +
                    "was deleted/removed!",
                )

            latest_post = res.json()["data"]["children"][0]
            post_removal_status = latest_post["data"]["removed_by_category"]

            if post_removal_status is not None:
                print(f"Post {listing_kwargs['before']} was removed/deleted!")
                print("Attempting to use last non removed/deleted highlight " +
                      "post!")

                while True:
                    if len(highlight_posts_stack) != 0:
                        last_highlights_post_name = highlight_posts_stack.pop()
                        res = self.__reddit.info(
                            ids=[last_highlights_post_name],
                            subreddit=subreddit,
                        )
                        if not res.ok:
                            raise ValueError(
                                "Invalid response while trying to check if " +
                                "latest highlight post was deleted/removed!",
                            )

                        latest_post = res.json()["data"]["children"][0]
                        post_removal_status = \
                            latest_post["data"]["removed_by_category"]

                        if post_removal_status is not None:
                            continue

                        highlight_posts_stack.append(last_highlights_post_name)
                        print("Found non removed/deleted mirrored highlight " +
                              "post!")
                        print("Setting latest post as " +
                              last_highlights_post_name)
                        listing_kwargs['before'] = last_highlights_post_name
                        break

                    else:
                        print("No previous mirrored highlight post found!")
                        res = self.__reddit.get(
                            f"r/{subreddit}/new",
                            params={"limit": 1},
                        )

                        if not res.ok:
                            raise ValueError(
                                "Invalid response while trying to retrieve " +
                                "latest post name!",
                            )

                        if res.json()["data"]["dist"] == 0:
                            raise Exception("Unable to any valid post in " +
                                            f"{subreddit}")

                        latest_post_name = \
                            res.json()["data"]["children"][0]["data"]["name"]
                        listing_kwargs["before"] = latest_post_name

                        print(f"Setting latest post as {latest_post_name}")
                        break

            print("Retrieving all posts before post name " +
                  listing_kwargs["before"])

            res = self.__reddit.get(
                f"r/{subreddit}/new",
                params=listing_kwargs,
            )

            if not res.ok:
                raise ValueError(
                    "Invalid response while trying to retrieve posts listing!",
                )

            highlight_posts = []

            while res.json()["data"]["dist"] != 0:
                subreddit_listing_posts = res.json()["data"]["children"]

                for post in reversed(subreddit_listing_posts):
                    if post["data"]["url"].startswith((
                        "https://streamable.com/",
                        "https://streamja.com/",
                        "https://mixture.gg/v/",
                        "https://streamff.com/v/",
                    )):
                        highlight_posts_stack.append(post["data"]["name"])
                        highlight_posts.append(post)

                listing_kwargs.update({
                    "before": subreddit_listing_posts[0]["data"]["name"],
                })

                res = self.__reddit.get(
                    f"r/{subreddit}/new",
                    params=listing_kwargs,
                )

                if not res.ok:
                    raise ValueError(
                        "Invalid response while trying to retrieve posts " +
                        "listing!",
                    )

            self.__mirror_for_posts(
                highlight_posts,
                mixture_mirror=mixture_mirror,
            )

            print("Sleeping for 30 seconds!")
            sleep(30)

    def __mirror_for_posts(
        self,
        highlight_posts: List[Dict[str, Any]],
        max_processing_attempts: int = 10,
        mixture_mirror: bool = False,
    ):
        post_queue = Queue()

        for post in highlight_posts:
            post_queue.put({"post": post, "attempts": 0, "last_attempt": None})

        while not post_queue.empty():
            post_data = post_queue.get()
            post = post_data["post"]
            vid_url: str = post["data"]["url"]

            sab_mirror_res = None
            sja_mirror_res = None
            jsl_mirror_res = None
            sff_mirror_res = None

            if not vid_url.startswith((
                "https://streamable.com/",
                "https://streamja.com/",
                "https://mixture.gg/v/",
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

                if not self.__streamable.is_video_available(streamable_id):
                    print("Unable to get direct video link from Streamable " +
                          f"video ID {streamable_id}. Video not available / " +
                          "taken down!")
                    continue

                if post_data["attempts"] < max_processing_attempts:
                    last_attempt: datetime
                    if (
                        last_attempt := post_data["last_attempt"]
                    ) is not None and (
                        datetime.now(tz=timezone.utc) - last_attempt
                    ).seconds < 5:
                        print(f"Attempting Streamable Video {streamable_id} " +
                              "mirror too quickly since last try! Must wait " +
                              "5 seconds between each attempt!")
                        post_queue.put(post_data)
                        continue

                    if self.__streamable.is_video_processing(streamable_id):
                        post_data["last_attempt"] = \
                            datetime.now(tz=timezone.utc)
                        print(f"Streamable Video {streamable_id} still " +
                              "being processed, trying later!")
                        post_data["attempts"] += 1
                        post_queue.put(post_data)
                        continue

                else:
                    print(f"Streamable Video {streamable_id} still " +
                          "being processed! Max attempts reached, " +
                          "ignoring video!")
                    continue

                vid_res = self.__streamable.get_video(streamable_id)
                media_data = BytesIO(vid_res.content)

                if media_data.getbuffer().nbytes <= STREAMABLE_MAX_SIZE:
                    sab_mirror_res, sab_vid_url = self.__streamable.clip_video(
                        streamable_id,
                        mirror_title=post["data"]["title"],
                    )

                if media_data.getbuffer().nbytes <= STREAMABLE_MAX_SIZE:
                    jsl_mirror_res, jsl_vid_url = \
                        self.__juststreamlive.mirror_streamable_video(
                            streamable_id,
                        )

                if media_data.getbuffer().nbytes <= STREAMJA_MAX_SIZE:
                    sja_mirror_res, sja_embed_url, sja_vid_url = \
                        self.__streamja.upload_video(media_data, "Mirror.mp4")

                if media_data.getbuffer().nbytes <= STREAMFF_MAX_SIZE:
                    sff_mirror_res, sff_vid_url = \
                        self.__streamff.upload_video(media_data, "Mirror.mp4")

                if (
                    mixture_mirror
                    and media_data.getbuffer().nbytes <= MIXTURE_MAX_SIZE
                ):
                    mix_mirror_res, mix_vid_url = \
                        self.__mixture.upload_video(media_data, "Mirror.mp4")

            elif vid_url.startswith("https://streamja.com/"):
                streamja_id = vid_url.split("https://streamja.com/")[1]

                if streamja_id.startswith("embed/"):
                    streamja_id = vid_url.split("embed/")[1]

                print(f"Processing {post['data']['name']} with Streamja " +
                      f"Video {streamja_id}")

                if not self.__streamja.is_video_available(streamja_id):
                    print("Unable to get direct video link from Streamja " +
                          f"video ID {streamja_id}. Video not available / " +
                          "taken down!")
                    continue

                if post_data["attempts"] < max_processing_attempts:
                    last_attempt: datetime
                    if (
                        last_attempt := post_data["last_attempt"]
                    ) is not None and (
                        datetime.now(tz=timezone.utc) - last_attempt
                    ).seconds < 5:
                        print(f"Attempting Streamja Video {streamja_id} " +
                              "mirror too quickly since last try! Must wait " +
                              "5 seconds between each attempt!")
                        post_queue.put(post_data)
                        continue

                    if self.__streamja.is_video_processing(streamja_id):
                        post_data["last_attempt"] = \
                            datetime.now(tz=timezone.utc)
                        print(f"Streamja Video {streamja_id} still " +
                              "being processed, trying later!")
                        post_data["attempts"] += 1
                        post_queue.put(post_data)
                        continue

                else:
                    print(f"Streamja Video {streamja_id} still " +
                          "being processed! Max attempts reached, " +
                          "ignoring video!")
                    continue

                vid_res = self.__streamja.get_video(streamja_id)
                media_data = BytesIO(vid_res.content)

                if media_data.getbuffer().nbytes <= STREAMABLE_MAX_SIZE:
                    sab_mirror_res, sab_vid_url = \
                        self.__streamable.clip_streamja_video(
                            streamja_id,
                            mirror_title=post["data"]["title"],
                        )
                if media_data.getbuffer().nbytes <= JUSTSTREAMLIVE_MAX_SIZE:
                    jsl_mirror_res, jsl_vid_url = \
                        self.__juststreamlive.mirror_streamja_video(
                            streamja_id
                        )

                if media_data.getbuffer().nbytes <= STREAMJA_MAX_SIZE:
                    sja_mirror_res, sja_embed_url, sja_vid_url = \
                        self.__streamja.upload_video(media_data, "Mirror.mp4")

                if media_data.getbuffer().nbytes <= STREAMFF_MAX_SIZE:
                    sff_mirror_res, sff_vid_url = \
                        self.__streamff.upload_video(media_data, "Mirror.mp4")

                if (
                    mixture_mirror
                    and media_data.getbuffer().nbytes <= MIXTURE_MAX_SIZE
                ):
                    mix_mirror_res, mix_vid_url = \
                        self.__mixture.upload_video(media_data, "Mirror.mp4")

            elif vid_url.startswith("https://mixture.gg/v/"):
                mixture_id = vid_url.split("https://mixture.gg/v/")[1]
                print(f"Processing {post['data']['name']} with Mixture " +
                      f"Video {mixture_id}")

                if not self.__mixture.is_video_available(mixture_id):
                    print("Unable to get direct video link from Mixture " +
                          f"video ID {mixture_id}. Video not available / " +
                          "taken down!")
                    continue

                if post_data["attempts"] < max_processing_attempts:
                    last_attempt: datetime
                    if (
                        last_attempt := post_data["last_attempt"]
                    ) is not None and (
                        datetime.now(tz=timezone.utc) - last_attempt
                    ).seconds < 5:
                        print(f"Attempting Mixture Video {mixture_id} " +
                              "mirror too quickly since last try! Must wait " +
                              "5 seconds between each attempt!")
                        post_queue.put(post_data)
                        continue

                    if self.__mixture.is_video_processing(mixture_id):
                        post_data["last_attempt"] = \
                            datetime.now(tz=timezone.utc)
                        print(f"Mixture Video {mixture_id} still " +
                              "being processed, trying later!")
                        post_data["attempts"] += 1
                        post_queue.put(post_data)
                        continue

                else:
                    print(f"Mixture Video {mixture_id} still " +
                          "being processed! Max attempts reached, " +
                          "ignoring video!")
                    continue

                vid_res = self.__mixture.get_video(mixture_id)
                media_data = BytesIO(vid_res.content)

                if media_data.getbuffer().nbytes <= STREAMABLE_MAX_SIZE:
                    sab_mirror_res, sab_vid_url = \
                        self.__streamable.clip_mixture_video(
                            mixture_id,
                            mirror_title=post["data"]["title"],
                        )

                if media_data.getbuffer().nbytes <= JUSTSTREAMLIVE_MAX_SIZE:
                    jsl_mirror_res, jsl_vid_url = \
                        self.__juststreamlive.mirror_mixture_video(
                            mixture_id
                        )

                if media_data.getbuffer().nbytes <= STREAMJA_MAX_SIZE:
                    sja_mirror_res, sja_embed_url, sja_vid_url = \
                        self.__streamja.upload_video(media_data, "Mirror.mp4")

                if media_data.getbuffer().nbytes <= STREAMFF_MAX_SIZE:
                    sff_mirror_res, sff_vid_url = \
                        self.__streamff.upload_video(media_data, "Mirror.mp4")

                if (
                    mixture_mirror
                    and media_data.getbuffer().nbytes <= MIXTURE_MAX_SIZE
                ):
                    mix_mirror_res, mix_vid_url = \
                        self.__mixture.upload_video(media_data, "Mirror.mp4")

            elif vid_url.startswith("https://streamff.com/v/"):
                streamff_id = vid_url.split("https://streamff.com/v/")[1]
                print(f"Processing {post['data']['name']} with Streamff " +
                      f"Video {streamff_id}")

                vid_res = self.__streamff.get_video(streamff_id)

                if not vid_res.ok:
                    print("Unable to get direct video link from Streamff " +
                          f"video ID {streamff_id}. Video not available / " +
                          "taken down!")
                    continue

                media_data = BytesIO(vid_res.content)

                if media_data.getbuffer().nbytes <= STREAMABLE_MAX_SIZE:
                    sab_mirror_res, sab_vid_url = \
                        self.__streamable.clip_streamff_video(
                            streamff_id,
                            mirror_title=post["data"]["title"],
                        )

                if media_data.getbuffer().nbytes <= JUSTSTREAMLIVE_MAX_SIZE:
                    jsl_mirror_res, jsl_vid_url = \
                        self.__juststreamlive.upload_video(
                            media_data, "Mirror.mp4",
                        )

                if media_data.getbuffer().nbytes <= STREAMJA_MAX_SIZE:
                    sja_mirror_res, sja_embed_url, sja_vid_url = \
                        self.__streamja.upload_video(media_data, "Mirror.mp4")

                if media_data.getbuffer().nbytes <= STREAMFF_MAX_SIZE:
                    sff_mirror_res, sff_vid_url = \
                        self.__streamff.upload_video(media_data, "Mirror.mp4")

                if (
                    mixture_mirror
                    and media_data.getbuffer().nbytes <= MIXTURE_MAX_SIZE
                ):
                    mix_mirror_res, mix_vid_url = \
                        self.__mixture.upload_video(media_data, "Mirror.mp4")

            mirrors = []

            if media_data.getbuffer().nbytes <= STREAMABLE_MAX_SIZE:
                if sab_vid_url is not None:
                    print("Streamable mirror created for " +
                          f"{post['data']['name']}!")
                    mirrors.append(f"* [Streamable]({sab_vid_url})")

                else:
                    print("Streamable mirror failed for " +
                          f"{post['data']['name']}!")
                    print(f"|- Status Code: {sab_mirror_res.status_code}")
                    print(f"|- Request URL: {sab_mirror_res.url}")
                    print(f"|- Response Text: {sab_mirror_res.text}")

            else:
                print("Streamable mirror failed for " +
                      f"{post['data']['name']} as it is too large!")
                mirrors.append("* Streamable: Failed as video file too " +
                               "large for host")

            if media_data.getbuffer().nbytes <= JUSTSTREAMLIVE_MAX_SIZE:
                if jsl_vid_url is not None:
                    print("JustStreamLive mirror created for " +
                          f"{post['data']['name']}!")
                    mirrors.append(f"* [JustStreamLive]({jsl_vid_url})")

                elif (
                    jsl_mirror_res.status_code == 400
                    and jsl_mirror_res.json()["detail"] == "File too big"
                ):
                    print("JustStreamLive mirror failed for " +
                          f"{post['data']['name']} as it is too large!")
                    mirrors.append("* JustStreamLive: Failed as video file " +
                                   "too large for host")

                else:
                    print("JustStreamLive mirror failed for " +
                          f"{post['data']['name']}!")
                    print(f"|- Status Code: {jsl_mirror_res.status_code}")
                    print(f"|- Request URL: {jsl_mirror_res.url}")
                    print(f"|- Response Text: {jsl_mirror_res.text}")

            else:
                print("JustStreamLive mirror failed for " +
                      f"{post['data']['name']} as it is too large!")
                mirrors.append("* JustStreamLive: Failed as video file too " +
                               "large for host")

            if media_data.getbuffer().nbytes <= STREAMJA_MAX_SIZE:
                if sja_embed_url is not None and sja_vid_url is not None:
                    print("Streamja mirror created for " +
                          f"{post['data']['name']}!")
                    mirrors.append(
                        "* " + " | ".join((
                            f"[Streamja Embed]({sja_embed_url})",
                            f"[Streamja Non-Embed]({sja_vid_url})",
                        )),
                    )

                elif sja_mirror_res.status_code == 413:
                    print("Streamja mirror failed for " +
                          f"{post['data']['name']} as it is too large!")
                    mirrors.append("* Streamja: Failed as video file too " +
                                   "large for host")

                else:
                    print("Streamja mirror failed for " +
                          f"{post['data']['name']}!")
                    print(f"|- Status Code: {sja_mirror_res.status_code}")
                    print(f"|- Request URL: {sja_mirror_res.url}")
                    print(f"|- Response Text: {sja_mirror_res.text}")

            else:
                print(f"Streamja mirror failed for {post['data']['name']} " +
                      "as it is too large!")
                mirrors.append("* Streamja: Failed as video file too large " +
                               "for host")

            if media_data.getbuffer().nbytes <= STREAMFF_MAX_SIZE:
                if sff_vid_url is not None:
                    print("Streamff mirror created for " +
                          f"{post['data']['name']}!")
                    mirrors.append(f"* [Streamff]({sff_vid_url})")

                elif sff_mirror_res.status_code == 413:
                    print("Streamff mirror failed for " +
                          f"{post['data']['name']} as it is too large!")
                    mirrors.append("* Streamff: Failed as video file too " +
                                   "large for host")

                else:
                    print("Streamff mirror failed for " +
                          f"{post['data']['name']}!")
                    print(f"|- Status Code: {sff_mirror_res.status_code}")
                    print(f"|- Request URL: {sff_mirror_res.url}")
                    print(f"|- Response Text: {sff_mirror_res.text}")

            else:
                print(f"Streamff mirror failed for {post['data']['name']} " +
                      "as it is too large!")
                mirrors.append("* Streamff: Failed as video file too large " +
                               "for host")

            if mixture_mirror:
                if media_data.getbuffer().nbytes <= MIXTURE_MAX_SIZE:
                    if mix_mirror_res.ok:
                        print("Mixture mirror created for " +
                              f"{post['data']['name']}!")
                        mirrors.append(f"* [Mixture]({mix_vid_url})")

                    else:
                        print("Mixture mirror failed for " +
                              f"{post['data']['name']}!")
                        print(f"|- Status Code: {mix_mirror_res.status_code}")
                        print(f"|- Request URL: {mix_mirror_res.url}")
                        print(f"|- Response Text: {mix_mirror_res.text}")

                else:
                    print("Mixture mirror failed for " +
                          f"{post['data']['name']} as it is too large!")
                    mirrors.append("* Mixture: Failed as video file too " +
                                   "large for host")

            if len(mirrors) > 0:
                parent_id = post["data"]["name"]

                res = self.__reddit.comments(
                    post["data"]["id"],
                    subreddit=post["data"]["subreddit"],
                    limit=1,
                )

                if not res.ok:
                    print("Invalid response while trying to retrieve " +
                          "comments listing!")

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

                self.__reddit.comment(
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
    ):
        res = self.__reddit.info(ids=post_ids, subreddit=subreddit)

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

        self.__mirror_for_posts(
            res.json()["data"]["children"],
            mixture_mirror=mixture_mirror,
        )

    def post_juststreamlive(
        self,
        media_path: Path,
        title: str,
        subreddit: str | None = None,
        flair_id: str | None = None,
    ):
        _, vid_url = self.__juststreamlive.upload_from_file(media_path)

        if vid_url is None:
            raise Exception("Invalid response while uploading file to " +
                            "JustStreamLive!")

        return self.__reddit.submit_url(
            title,
            vid_url,
            subreddit=subreddit,
            flair_id=flair_id,
        )

    def post_streamable(
        self,
        media_path: Path,
        title: str,
        subreddit: str | None = None,
        flair_id: str | None = None,
    ):
        _, vid_url = self.__streamable.upload_from_file(
            media_path, video_title=title,
        )

        if vid_url is None:
            raise Exception("Invalid response while uploading file to " +
                            "Streamable!")

        return self.__reddit.submit_url(
            title,
            vid_url,
            subreddit=subreddit,
            flair_id=flair_id,
        )

    def post_streamja(
        self,
        media_path: Path,
        title: str,
        subreddit: str | None = None,
        flair_id: str | None = None,
    ):
        _, _, vid_url = self.__streamja.upload_from_file(media_path)

        if vid_url is None:
            raise Exception("Invalid response while uploading file to " +
                            "Streamja!")

        return self.__reddit.submit_url(
            title,
            vid_url,
            subreddit=subreddit,
            flair_id=flair_id,
        )

    def post_mixture(
        self,
        media_path: Path,
        title: str,
        subreddit: str | None = None,
        flair_id: str | None = None,
    ):
        res, vid_url = self.__mixture.upload_from_file(media_path)

        if not res.ok:
            raise Exception("Invalid response while uploading file to " +
                            "Mixture!")

        return self.__reddit.submit_url(
            title, vid_url, subreddit=subreddit, flair_id=flair_id,
        )

    def post_streamff(
        self,
        media_path: Path,
        title: str,
        subreddit: str | None = None,
        flair_id: str | None = None,
    ):
        _, vid_url = self.__streamff.upload_from_file(media_path)

        if vid_url is None:
            raise Exception("Invalid response while uploading file to " +
                            "Streamff!")

        return self.__reddit.submit_url(
            title,
            vid_url,
            subreddit=subreddit,
            flair_id=flair_id,
        )

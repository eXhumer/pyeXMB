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
from collections import deque
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from pkg_resources import require
from queue import Queue
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
__MB = 1 * 1024 * 1024
JUSTSTREAMLIVE_MAX_SIZE = 200 * __MB
STREAMABLE_MAX_SIZE = 250 * __MB
STREAMFF_MAX_SIZE = 200 * __MB
STREAMJA_MAX_SIZE = 30 * __MB
STREAMWO_MAX_SIZE = 512 * __MB


class BotClient:
    def __init__(self, auth_alias: str) -> None:
        session = Session()
        session.headers["User-Agent"] = __user_agent__
        self.__reddit = OAuth2Client.load_from_file(
            __config_path__ / f"{auth_alias}.json",
            session=session,
        )
        self.__juststreamlive = JustStreamLive(session=session)
        self.__streamable = Streamable(session=session)
        self.__streamja = Streamja(session=session)
        self.__streamff = Streamff(session=session)
        self.__streamwo = Streamwo(session=session)

    def run_bot_for_subreddit(
        self,
        subreddit: str,
        streamwo_mirror: bool = False,
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
                        "https://streamwo.com/file/",
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
                streamwo_mirror=streamwo_mirror,
            )

            print("Sleeping for 30 seconds!")
            sleep(30)

    def __mirror_for_posts(
        self,
        highlight_posts: List[Dict[str, Any]],
        max_processing_attempts: int = 10,
        streamwo_mirror: bool = False,
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
                "https://streamwo.com/file/",
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

                if len(media_data) <= STREAMABLE_MAX_SIZE:
                    sab_mirror_res, sab_vid_url = self.__streamable.clip_video(
                        streamable_id,
                        mirror_title=post["data"]["title"],
                    )

                if len(media_data) <= STREAMABLE_MAX_SIZE:
                    jsl_mirror_res, jsl_vid_url = \
                        self.__juststreamlive.mirror_streamable_video(
                            streamable_id,
                        )

                if len(media_data) <= STREAMJA_MAX_SIZE:
                    sja_mirror_res, sja_embed_url, sja_vid_url = \
                        self.__streamja.upload_video(media_data, "Mirror.mp4")

                if len(media_data) <= STREAMFF_MAX_SIZE:
                    sff_mirror_res, sff_vid_url = \
                        self.__streamff.upload_video(media_data, "Mirror.mp4")

                if streamwo_mirror and len(media_data) <= STREAMWO_MAX_SIZE:
                    swo_mirror_res, swo_vid_url = \
                        self.__streamwo.upload_video(media_data, "Mirror.mp4")

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

                if len(media_data) <= STREAMABLE_MAX_SIZE:
                    sab_mirror_res, sab_vid_url = \
                        self.__streamable.clip_streamja_video(
                            streamja_id,
                            mirror_title=post["data"]["title"],
                        )
                if len(media_data) <= JUSTSTREAMLIVE_MAX_SIZE:
                    jsl_mirror_res, jsl_vid_url = \
                        self.__juststreamlive.mirror_streamja_video(
                            streamja_id
                        )

                if len(media_data) <= STREAMJA_MAX_SIZE:
                    sja_mirror_res, sja_embed_url, sja_vid_url = \
                        self.__streamja.upload_video(media_data, "Mirror.mp4")

                if len(media_data) <= STREAMFF_MAX_SIZE:
                    sff_mirror_res, sff_vid_url = \
                        self.__streamff.upload_video(media_data, "Mirror.mp4")

                if streamwo_mirror and len(media_data) <= STREAMWO_MAX_SIZE:
                    swo_mirror_res, swo_vid_url = \
                        self.__streamwo.upload_video(media_data, "Mirror.mp4")

            elif vid_url.startswith("https://streamwo.com/file/"):
                streamwo_id = vid_url.split("https://streamwo.com/file/")[1]
                print(f"Processing {post['data']['name']} with Streamwo " +
                      f"Video {streamwo_id}")

                if not self.__streamwo.is_video_available(streamwo_id):
                    print("Unable to get direct video link from Streamwo " +
                          f"video ID {streamwo_id}. Video not available / " +
                          "taken down!")
                    continue

                if post_data["attempts"] < max_processing_attempts:
                    last_attempt: datetime
                    if (
                        last_attempt := post_data["last_attempt"]
                    ) is not None and (
                        datetime.now(tz=timezone.utc) - last_attempt
                    ).seconds < 5:
                        print(f"Attempting Streamwo Video {streamwo_id} " +
                              "mirror too quickly since last try! Must wait " +
                              "5 seconds between each attempt!")
                        post_queue.put(post_data)
                        continue

                    if self.__streamwo.is_video_processing(streamwo_id):
                        post_data["last_attempt"] = \
                            datetime.now(tz=timezone.utc)
                        print(f"Streamwo Video {streamwo_id} still " +
                              "being processed, trying later!")
                        post_data["attempts"] += 1
                        post_queue.put(post_data)
                        continue

                else:
                    print(f"Streamwo Video {streamwo_id} still " +
                          "being processed! Max attempts reached, " +
                          "ignoring video!")
                    continue

                vid_res = self.__streamwo.get_video(streamwo_id)
                media_data = BytesIO(vid_res.content)

                if len(media_data) <= STREAMABLE_MAX_SIZE:
                    sab_mirror_res, sab_vid_url = \
                        self.__streamable.clip_streamwo_video(
                            streamwo_id,
                            mirror_title=post["data"]["title"],
                        )

                if len(media_data) <= JUSTSTREAMLIVE_MAX_SIZE:
                    jsl_mirror_res, jsl_vid_url = \
                        self.__juststreamlive.mirror_streamwo_video(
                            streamwo_id
                        )

                if len(media_data) <= STREAMJA_MAX_SIZE:
                    sja_mirror_res, sja_embed_url, sja_vid_url = \
                        self.__streamja.upload_video(media_data, "Mirror.mp4")

                if len(media_data) <= STREAMFF_MAX_SIZE:
                    sff_mirror_res, sff_vid_url = \
                        self.__streamff.upload_video(media_data, "Mirror.mp4")

                if streamwo_mirror and len(media_data) <= STREAMWO_MAX_SIZE:
                    swo_mirror_res, swo_vid_url = \
                        self.__streamwo.upload_video(media_data, "Mirror.mp4")

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

                if len(media_data) <= STREAMABLE_MAX_SIZE:
                    sab_mirror_res, sab_vid_url = \
                        self.__streamable.clip_streamff_video(
                            streamff_id,
                            mirror_title=post["data"]["title"],
                        )

                if len(media_data) <= JUSTSTREAMLIVE_MAX_SIZE:
                    jsl_mirror_res, jsl_vid_url = \
                        self.__juststreamlive.upload_video(
                            media_data, "Mirror.mp4",
                        )

                if len(media_data) <= STREAMJA_MAX_SIZE:
                    sja_mirror_res, sja_embed_url, sja_vid_url = \
                        self.__streamja.upload_video(media_data, "Mirror.mp4")

                if len(media_data) <= STREAMFF_MAX_SIZE:
                    sff_mirror_res, sff_vid_url = \
                        self.__streamff.upload_video(media_data, "Mirror.mp4")

                if streamwo_mirror and len(media_data) <= STREAMWO_MAX_SIZE:
                    swo_mirror_res, swo_vid_url = \
                        self.__streamwo.upload_video(media_data, "Mirror.mp4")

            mirrors = []

            if len(media_data) <= STREAMABLE_MAX_SIZE:
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

            if len(media_data) <= JUSTSTREAMLIVE_MAX_SIZE:
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

            if len(media_data) <= STREAMJA_MAX_SIZE:
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

            if len(media_data) <= STREAMFF_MAX_SIZE:
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

            if streamwo_mirror and len(media_data) <= STREAMWO_MAX_SIZE:
                if swo_mirror_res.ok:
                    print("Streamwo mirror created for " +
                          f"{post['data']['name']}!")
                    mirrors.append(f"* [Streamwo]({swo_vid_url})")

                else:
                    print("Streamwo mirror failed for " +
                          f"{post['data']['name']}!")
                    print(f"|- Status Code: {swo_mirror_res.status_code}")
                    print(f"|- Request URL: {swo_mirror_res.url}")
                    print(f"|- Response Text: {swo_mirror_res.text}")

            else:
                print(f"Streamwo mirror failed for {post['data']['name']} " +
                      "as it is too large!")
                mirrors.append("* Streamwo: Failed as video file too large " +
                               "for host")

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
        streamwo_mirror: bool = False,
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
            streamwo_mirror=streamwo_mirror,
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

    def post_streamwo(
        self,
        media_path: Path,
        title: str,
        subreddit: str | None = None,
        flair_id: str | None = None,
    ):
        res, vid_url = self.__streamwo.upload_from_file(media_path)

        if not res.ok:
            raise Exception("Invalid response while uploading file to " +
                            "Streamwo!")

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
                client = OAuth2Client.localserver_code_flow(
                    args.client_id,
                    args.client_secret if args.client_secret else "",
                    args.callback_url,
                    args.duration,
                    args.scopes.split(" "),
                    state=args.state,
                    user_agent=__user_agent__,
                    token_path=__config_path__ / f"{args.alias}.json",
                )
                client.save_to_file()

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
            BotClient(args.alias).run_bot_for_subreddit(
                args.subreddit if args.subreddit else "formula1",
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
            BotClient(args.alias).mirror_for_posts_by_id(
                args.post_ids,
                subreddit=args.subreddit,
                streamwo_mirror=args.streamwo_mirror,
            )

        else:
            raise KeyError(
                f"No authorization alias with key {args.alias} found!",
            )

    elif args.action == "post-juststreamlive":
        if (__config_path__ / f"{args.alias}.json").is_file():
            BotClient(args.alias).post_juststreamlive(
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
            BotClient(args.alias).post_streamable(
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
            BotClient(args.alias).post_streamja(
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
            BotClient(args.alias).post_streamwo(
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
            BotClient(args.alias).post_streamff(
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
    run_parser.add_argument("--streamwo-mirror", action="store_true")
    mirror_for_post_parser = subparsers.add_parser("mirror-for-post")
    mirror_for_post_parser.add_argument("alias")
    mirror_for_post_parser.add_argument(
        "post_ids", metavar="post_id", nargs="+",
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

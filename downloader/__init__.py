import re
import json
import subprocess
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.pardir, os.getcwd())))
from logging_setup.logging_setup import get_logger
from youtube_dl import YoutubeDL

logger = get_logger(__name__)

VIDEO_HEIGHT = 360


class InvalidUrlException(Exception):
    """Called if valid download url cannot be found"""


def youtube_url_validation(url):
    """Check if the link is a valid youtube URL. Source: https://stackoverflow.com/a/19161373/11692859"""
    youtube_regex = (
        r'(https?://)?(www\.)?'
        '(youtube|youtu|youtube-nocookie)\.(com|be)/'
        '(watch\?v=|embed/|v/|.+\?v=)?([^&=%\?]{11})')

    youtube_regex_match = re.match(youtube_regex, url)
    if youtube_regex_match:
        return youtube_regex_match

    return youtube_regex_match


def filter_urls(video_formats):
    """Filter the URLs acquired from youtube-dl based on a number of different criteria"""
    real_url = None
    smallest_file_size = None
    find_audio = True
    selected_format = None

    while real_url is None:
        # Iterate through each dictionary
        for video_format in video_formats:
            # Check that the keys we're about to access exist in the dictionary
            if not {"acodec", "height", "ext"}.issubset(video_format):
                continue

            # Ensure that the video has an integer height value, is an mp4, and does not contain a manifest url that
            # can break ffmpeg
            if not isinstance(video_format["height"], int) or video_format["ext"] != "mp4" or "manifest_url" in \
                    video_format:
                continue

            # Filter videos by the required height and attempt to get the smallest file size to speed up downloads
            if video_format["height"] == VIDEO_HEIGHT:
                if find_audio and video_format["acodec"] == "none":
                    continue
                if smallest_file_size is None:
                    real_url = video_format['url'].strip()
                    smallest_file_size = video_format['filesize']
                    selected_format = video_format
                elif smallest_file_size is not None and video_format['filesize'] < smallest_file_size:
                    real_url = video_format['url'].strip()
                    smallest_file_size = video_format['filesize']
                    selected_format = video_format

        # If having audio is too much of a requirement, disable the audio requirement
        if real_url is None:
            find_audio = False

    if real_url is None:
        logger.error("A valid URL could not be found!")
        raise InvalidUrlException("A valid URL could not be found!")

    logger.info("Selected the following video format for downloading: ")
    logger.info(json.dumps(selected_format, indent=4))

    return real_url


def download_video(url, path, start_seconds, end_seconds):
    """Downloads a video from youtube"""
    logger.info(f"Attempting to downloading: {url}")

    if not youtube_url_validation(url):
        raise InvalidUrlException("Must be a youtube URL!")

    # Prevents weird certificate error on MacOS
    options_youtube_dl = {'nocheckcertificate': True}

    # Create yt-dl object for downloading stuff
    yt_downloader = YoutubeDL(options_youtube_dl)

    # Youtube-dl returns a dictionary of info
    try:
        info_dictionary = yt_downloader.extract_info(url, download=False)
    except Exception as e:
        logger.info(f"Something went wrong while running youtube-dl: {e}", exc_info=True)
        raise InvalidUrlException("URL rejected by youtube-dl!")

    # Filter the urls to get the most optimal download link
    real_url = filter_urls(info_dictionary['formats'])

    # format start and end seconds into timestamps
    start_time_formatted = f"{int(start_seconds / 3600)}:{int((start_seconds % 3600) / 60)}:{start_seconds % 60}.00"
    duration = end_seconds - start_seconds
    duration_formatted = f"{int(duration / 3600)}:{int((duration % 3600) / 60)}:{duration % 60}.00"

    # setup and run the ffmpeg command to download the desired portion of the video
    ffmpeg_command = ['ffmpeg',
                      '-y',
                      '-ss', start_time_formatted,
                      '-t', duration_formatted,
                      '-i', real_url,
                      "-c", "copy",
                      path]

    logger.info(f"Attempting to run the following FFmpeg command:  {' '.join(ffmpeg_command)}")

    running_process = subprocess.Popen(ffmpeg_command,
                                       stdout=subprocess.PIPE,
                                       stderr=subprocess.STDOUT,
                                       universal_newlines=True)

    # Wait until the process finishes before returning
    while running_process.poll() is None:
        output, error = running_process.communicate()
        if running_process.returncode != 0:
            logger.error(f"Something went wrong while running FFmpeg: {output}", exc_info=True)
            logger.error(f"Received error: {error}", exc_info=True)

    logger.info(f"Successfully downloaded file to: {path}")


if __name__ == '__main__':
    download_video('https://www.youtube.com/watch?v=G1IbRujko-A&t', "gandalf_saxophone.mp4", 0, 30)

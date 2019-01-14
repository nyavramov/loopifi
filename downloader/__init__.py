from youtube_dl import YoutubeDL

import subprocess


def download_video(url, path, start_seconds, end_seconds):
    # Prevents weird certificate error on MacOS
    optionsYoutubeDl = {'nocheckcertificate': True}

    # Create yt-dl object for downloading stuff
    ytDownloader = YoutubeDL(optionsYoutubeDl)

    # youtube-dl returns a dictionary of info
    infoDictionary = ytDownloader.extract_info(url, download=False)

    # Get last media url
    realUrl = infoDictionary['formats'][-1]['url'].strip()

    # format start and end seconds into timestamps
    startTime = '{}:{}:{}.00'.format(
        int(start_seconds / 3600),
        int((start_seconds % 3600) / 60),
        start_seconds % 60
    )

    duration = end_seconds - start_seconds

    durationFormatted = '{}:{}:{}.00'.format(
        int(duration / 3600),
        int((duration % 3600) / 60),
        duration % 60
    )

    # setup and run the ffmpeg command to download the desired
    # portion of the video
    ffmpegCommand = ['ffmpeg',
                     '-y',
                     '-ss', startTime,
                     '-t', durationFormatted,
                     '-i', realUrl,
                     '-c:v', 'libx264',
                     '-vf', 'scale=720:-2',
                     path]

    runningProcess = subprocess.Popen(ffmpegCommand,
                                      stdout=subprocess.PIPE,
                                      stderr=subprocess.STDOUT,
                                      universal_newlines=True)

    # Wait until the process finishes before returning
    while runningProcess.poll() is None:
        pass


if __name__ == '__main__':
    download_video('https://youtu.be/G9KDqfpCgws')

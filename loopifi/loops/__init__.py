import os
import sys
import shutil
import subprocess
from collections import namedtuple

# noinspection PyUnresolvedReferences, PyPackageRequirements
import context
import cv2
import imagehash
from PIL import Image
from ntpath import basename
from loopifi.logging_setup import get_logger


logger = get_logger(__name__)


##############################################################################################################
# Constants
##############################################################################################################

# Max amount of time between start and end timestamps
MAX_VIDEO_SEARCH_LENGTH = 600

# Search related hash constants
HASH_SIZE = 64
MAX_HASH_DIFFERENCE = (HASH_SIZE ** 2) * 4
MIN_MID_FRAME_SIMILARITY = 4
SIMILARITY_THRESHOLD = MAX_HASH_DIFFERENCE * 0.75
SEARCH_STEP_SIZE = 5  # Granularity/specificity of the loop search

# Webm output related constants
LOOP_WIDTH = 500  # The width in pixels of an encoded webm
NUMBER_WEBMS_TO_MAKE = 5  # How many webms we would like to make in total
MINIMUM_LOOP_FRAMES = 15  # The minimum number of frames in a webm
MAXIMUM_LOOP_FRAMES = 300  # The maximum number of frames in a webm

# Enable to prevent temporary files from being deleted
# Use from env-var like `DEBUG_MODE=1 python loops.py ...` or `DEBUG_MODE=1 flask rq worker`
DEBUG_MODE = os.environ.get("DEBUG_MODE", False)

##############################################################################################################
# Class Definitions
##############################################################################################################

LoopRecord = namedtuple(
    "webm",
    [
        "webm_name",
        "gif_name",
        "score",
        "frame_length",
        "start_frame_number",
        "end_frame_number",
        "webm_location",
        "gif_location",
        "mp4_location",
    ],
)


class FrameHashDatabase(object):
    def __init__(self, existing_hashes, path_of_source_video):
        self.db = existing_hashes
        self.path_of_source_video = path_of_source_video

    def get(self, frame_number):

        while frame_number not in self.db:
            # check if the next frame over exists
            frame_number += 1

        return self.db[frame_number]


class CandidateLoop(object):
    def __init__(self, score, start_frame_number, end_frame_number, frame_rate):

        self.score = score
        self.start_frame_number = start_frame_number
        self.end_frame_number = end_frame_number
        self.frame_rate = frame_rate

        self.start_time = self.start_frame_number / frame_rate
        self.duration = (self.end_frame_number - self.start_frame_number) / frame_rate

        self.gif_palette_command = None
        self.gif_encode_command = None
        self.webm_encode_command = None
        self.mp4_encode_command = None

        self.gif_name = None
        self.webm_name = None
        self.mp4_name = None


class InvalidIntervalException(Exception):
    """Thrown when module called with invalid start and end timestamps"""


#######################################################################################################################
# Function Definitions
#######################################################################################################################


# Clean up the various files & folders we generated at the start of the loop creation process
# TODO should put all temporary files into a single directory that can be either deleted or not based on a `DEBUG_MODE`
#  flag
def clean_up_folders(temp_frames_folder, frame_directory_path, path_of_source_video):

    if DEBUG_MODE:
        return

    folders_to_remove = [temp_frames_folder, frame_directory_path]

    vector_file = os.path.join(
        os.path.dirname(path_of_source_video), "transform_vectors.trf"
    )

    files_to_remove = [vector_file, path_of_source_video]

    for folder in folders_to_remove:
        try:
            shutil.rmtree(folder)
        except FileNotFoundError:
            pass

    for file in files_to_remove:
        try:
            os.remove(file)
        except FileNotFoundError:
            pass


#######################################################################################################################

# Get how long the video is
def get_duration(video_path):

    command = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        video_path,
    ]

    duration_string = subprocess.check_output(command, encoding="UTF-8")

    duration = float(duration_string)

    return duration


#######################################################################################################################


# Due to complications with start/end time, we need this fps function for number of frames calculation
def get_frame_rate(video_path):

    command = [
        "ffprobe",
        "-v",
        "0",
        "-of",
        "csv=p=0",
        "-select_streams",
        "V:0",
        "-show_entries",
        "stream=r_frame_rate",
        video_path,
    ]

    frame_rate_string = subprocess.check_output(command, encoding="UTF-8")

    # ffmpeg will report like 30000/1000
    num, div = frame_rate_string.split("/")
    frame_rate = int(num) / int(div)

    return frame_rate


#######################################################################################################################


# Creates directories called Loops & ALL_FRAMES_{videoName} & temp if they don't already exist
def create_directories(*paths):
    for path in paths:
        if not os.path.exists(path):
            os.makedirs(path)


#######################################################################################################################


# Calculate stabilization vectors --> Stabilize video
def resize_video(path_of_source_video, resized_video_path, callback):

    # Now we can use libvidstab to stabilize video using the .trf vector file we just created
    resize_command = [
        "ffmpeg",
        "-y",
        "-i",
        path_of_source_video,
        "-vf",
        f"scale={LOOP_WIDTH}:-2",
        "-crf",
        "20",
        resized_video_path,
    ]

    stabilize_progress = 0

    callback("Resizing video...", stabilize_progress)

    # run the command
    subprocess.run(resize_command)
    stabilize_progress += 10
    callback("Resizing video...", stabilize_progress)

    return resized_video_path


# Calculate stabilization vectors --> Stabilize video
def stabilize_video(
    path_of_source_video, stable_video_path, start_time, end_time, callback
):

    folder_of_source_video = os.path.dirname(path_of_source_video)
    duration = end_time - start_time

    # Prior to stabilizing the video, we'll need to calculate the stabilization vectors we need
    calculate_vector_command = [
        "ffmpeg",
        "-y",
        "-threads",
        "8",
        "-i",
        "{}".format(path_of_source_video),
        "-vf",
        "vidstabdetect=stepsize=6:shakiness=4:accuracy=5:"
        "result={}/transform_vectors.trf".format(os.path.dirname(path_of_source_video)),
        "-f",
        "null",
        "-",
    ]

    # Now we can use libvidstab to stabilize video using the .trf vector file we just created
    stabilize_command = [
        "ffmpeg",
        "-threads",
        "8",
        "-y",
        "-i",
        path_of_source_video,
        "-ss",
        str(start_time),
        "-t",
        str(duration),
        "-vf",
        "vidstabtransform=input={}/transform_vectors.trf:"
        "zoom=1:smoothing=30,unsharp=5:5:0.8:3:3:0.4".format(
            folder_of_source_video, LOOP_WIDTH
        ),
        "-vcodec",
        "libx264",
        "-acodec",
        "copy",
        "-preset",
        "fast",
        "-tune",
        "film",
        "-crf",
        "17",
        "-acodec",
        "copy",
        stable_video_path,
    ]

    stabilize_progress = 0

    callback("Stabilizing video...", stabilize_progress)

    for command in (calculate_vector_command, stabilize_command):

        callback("Stabilizing video...", stabilize_progress)

        # run the command
        subprocess.run(command)

        stabilize_progress += 10


#######################################################################################################################


# We'll use this to tell FFMPEG what kind of GIF/WEBM we want, i.e., give it correctly formatted parameters
def prepare_webm_info(
    candidate, webm_destination_folder, stable_video_path, sound_enabled, counter
):

    webm_name = "{}.webm".format(counter)
    webm_destination = os.path.join(webm_destination_folder, webm_name)
    webm_encode_command = [
        "ffmpeg",
        "-y",
        "-ss",
        str(candidate.start_time),
        "-t",
        str(candidate.duration),
        "-i",
        stable_video_path,
    ]

    if not sound_enabled:
        webm_encode_command.append("-an")

    # This part of command will then process all frames in temp directory to output to GIF/WEBM
    webm_encode_command.extend(
        [
            "-minrate",
            "1700k",
            "-b:v",
            "1800K",
            "-maxrate",
            "2000K",
            "-c:v",
            "libvpx",
            "-vf",
            "scale=500:-2",
            webm_destination,
        ]
    )

    candidate.webm_encode_command = webm_encode_command
    candidate.webm_name = webm_name

    return candidate


#######################################################################################################################


def prepare_gif_info(
    candidate, webm_destination_folder, stable_video_path, frame_directory_path, counter
):

    gif_name = "{}.gif".format(counter)
    gif_destination = os.path.join(webm_destination_folder, gif_name)
    palette_destination = os.path.join(frame_directory_path, "palette.png")

    gif_palette_command = [
        "ffmpeg",
        "-y",
        "-ss",
        str(candidate.start_time),
        "-t",
        str(candidate.duration),
        "-i",
        stable_video_path,
        "-vf",
        "scale=500:-2:flags=lanczos,palettegen",
        palette_destination,
    ]

    gif_encode_command = [
        "ffmpeg",
        "-y",
        "-ss",
        str(candidate.start_time),
        "-t",
        str(candidate.duration),
        "-i",
        stable_video_path,
        "-i",
        palette_destination,
        "-filter_complex",
        "fps=25,scale=500:-2:flags=lanczos[x];[x][1:v]paletteuse",
        gif_destination,
    ]

    candidate.gif_palette_command = gif_palette_command
    candidate.gif_encode_command = gif_encode_command
    candidate.gif_name = gif_name

    return candidate


#######################################################################################################################


def prepare_mp4_info(
    candidate, webm_destination_folder, stable_video_path, sound_enabled, counter
):

    mp4_name = "{}.mp4".format(counter)
    mp4_destination = os.path.join(webm_destination_folder, mp4_name)

    mp4_encode_command = [
        "ffmpeg",
        "-y",
        "-ss",
        str(candidate.start_time),
        "-t",
        str(candidate.duration),
        "-i",
        stable_video_path,
        "-an",
        "-b:v",
        "1800K",
        "-c:v",
        "libx264",
        "-vf",
        "scale=500:-2",
        mp4_destination,
    ]

    if sound_enabled:
        mp4_encode_command.remove("-an")

    candidate.mp4_encode_command = mp4_encode_command
    candidate.mp4_name = mp4_name

    return candidate


#######################################################################################################################


# We'll clean/populate the temp directory and then create the loops from list of sorted candidates
def create_candidate_loops(best_webm_candidates, callback):

    percent_per_webm = 20 / NUMBER_WEBMS_TO_MAKE
    encode_progress = 80

    callback("Encoding webms...", encode_progress)

    for i in range(0, min(len(best_webm_candidates), NUMBER_WEBMS_TO_MAKE)):

        gif_palette_command = best_webm_candidates[i].gif_palette_command
        gif_encode_command = best_webm_candidates[i].gif_encode_command
        webm_encode_command = best_webm_candidates[i].webm_encode_command
        mp4_encode_command = best_webm_candidates[i].mp4_encode_command

        for command in (
            gif_palette_command,
            gif_encode_command,
            webm_encode_command,
            mp4_encode_command,
        ):
            subprocess.run(command)

        encode_progress = encode_progress + percent_per_webm

        callback("Encoding webms...", encode_progress)


#######################################################################################################################


def compare_candidates(
    start_frame, candidate_frame, hash_db, best_score_this_iteration
):

    start_hash = hash_db.get(start_frame)
    candidate_hash = hash_db.get(candidate_frame)

    current_candidate_similarity = start_hash - candidate_hash
    current_candidate_similarity = float(current_candidate_similarity)

    # Keep track of which of the candidates get the best score when compared to start frame
    if (
        current_candidate_similarity < SIMILARITY_THRESHOLD
        and current_candidate_similarity < best_score_this_iteration
    ):

        middle_frame = (start_frame + candidate_frame) // 2
        middle_frame_hash = hash_db.get(middle_frame)

        start_middle_percent_diff = (
            (start_hash - middle_frame_hash) / MAX_HASH_DIFFERENCE
        ) * 100
        if start_middle_percent_diff < MIN_MID_FRAME_SIMILARITY:
            return None

        best_score_this_iteration = current_candidate_similarity

        return best_score_this_iteration, start_frame, candidate_frame

    return None


#######################################################################################################################


def add_info_to_candidates(
    best_webm_candidates,
    webm_destination_folder,
    stable_video_path,
    frame_directory_path,
    sound_enabled,
):

    for counter, candidate in enumerate(best_webm_candidates, 1):

        prepare_webm_info(
            candidate,
            webm_destination_folder,
            stable_video_path,
            sound_enabled,
            counter,
        )
        prepare_gif_info(
            candidate,
            webm_destination_folder,
            stable_video_path,
            frame_directory_path,
            counter,
        )
        prepare_mp4_info(
            candidate,
            webm_destination_folder,
            stable_video_path,
            sound_enabled,
            counter,
        )

    return best_webm_candidates


#######################################################################################################################


# Main program loop. As the name suggests, we use this to go through each frame and evaluate
# start frames vs candidates
def search_for_loops(hashed_frames_list, hash_db, frame_rate, callback):

    iteration = 0  # What iteration of the search process we're on
    best_webm_candidates = (
        []
    )  # Store commands & information corresponding to top loop candidates

    callback("Searching for loops...", 60)

    # Loop through every hash, comparing start hashes to candidates hashes
    for start_frame in hashed_frames_list:
        best_candidate = None
        iteration = iteration + 1
        candidate_counter = (
            0
        )  # Limits min & max number of candidates to compare to 1st frame in window

        # Move candidate search window & initialize highest similarity score to 0
        # Highest similarity refers to best candidate frame in current window
        candidate_frames = hashed_frames_list[iteration:]
        best_score_this_iteration = MAX_HASH_DIFFERENCE

        # Loop though every candidate frame and compare to start frame
        for candidate_frame in candidate_frames:
            candidate_counter = candidate_counter + SEARCH_STEP_SIZE

            if candidate_counter < MINIMUM_LOOP_FRAMES:
                continue
            elif candidate_counter > MAXIMUM_LOOP_FRAMES:
                break
            else:
                candidate = compare_candidates(
                    start_frame, candidate_frame, hash_db, best_score_this_iteration
                )
                if candidate is not None:
                    best_candidate = candidate
                    best_score_this_iteration, _, _ = candidate

        # If we've found a loop after comparing all the candidates, we can create it
        if best_candidate is not None:
            best_score_this_iteration, start_frame_number, end_frame_number = (
                best_candidate
            )
            new_candidate = CandidateLoop(
                best_score_this_iteration,
                start_frame_number,
                end_frame_number,
                frame_rate,
            )
            # Append the candidate loop along with its score, start, end, & framerate
            best_webm_candidates.append(new_candidate)

    callback("Searching for loops...", 80)

    # Since best_webm_candidates is a list of lists... aka... [ [0.89, commandString], [0.91, commandString] ]
    # Sort the outer list based on first item (score) of each inner list, highest to lowest score
    best_webm_candidates.sort(key=lambda x: x.score)

    return best_webm_candidates


#######################################################################################################################


def hash_frames(stable_video_path, callback):
    """Hashes video frames using perceptual hashing

    :param stable_video_path: where the stabilized video is located
    :param callback: a callback function

    :return: hash_dictionary, hashed_frames_list
    """
    callback("Preparing to search...", 40)

    hashed_frames_list = []
    hash_dictionary = {}

    current_frame = 0

    video_capture = cv2.VideoCapture(stable_video_path)
    number_of_frames = video_capture.get(cv2.CAP_PROP_FRAME_COUNT)

    while video_capture.isOpened:

        # Extract the frame
        ret, frame = video_capture.read()

        if not ret:
            video_capture.release()
            break

        if current_frame % 150 == 0:
            logger.info(f"Hash Progress: {(current_frame * 100) / number_of_frames}%")

        if current_frame % SEARCH_STEP_SIZE == 0:
            cv2_image = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            pillow_image = Image.fromarray(cv2_image)
            perceptual_hash = imagehash.phash(pillow_image, hash_size=HASH_SIZE)
            hashed_frames_list.append(current_frame)
            hash_dictionary[current_frame] = perceptual_hash

        current_frame += 1

    callback("Preparing to search...", 60)

    return hash_dictionary, hashed_frames_list


#######################################################################################################################


def get_video_info_tuple(best_webm_candidates, webm_destination_folder):

    tuples_list = []  # We'll store our namedtuples here

    for i in range(min(NUMBER_WEBMS_TO_MAKE, len(best_webm_candidates))):

        score = best_webm_candidates[i].score
        start_frame_number = best_webm_candidates[i].start_frame_number
        end_frame_number = best_webm_candidates[i].end_frame_number
        webm_name = best_webm_candidates[i].webm_name
        gif_name = best_webm_candidates[i].gif_name
        mp4_name = best_webm_candidates[i].mp4_name

        relative_path_webm = os.path.join(webm_destination_folder, webm_name)
        webm_location = os.path.abspath(relative_path_webm)

        relative_path_gif = os.path.join(webm_destination_folder, gif_name)
        gif_location = os.path.abspath(relative_path_gif)

        relative_path_mp4 = os.path.join(webm_destination_folder, mp4_name)
        mp4_location = os.path.abspath(relative_path_mp4)

        frame_length = end_frame_number - start_frame_number

        normalized_score = round(-1 * (score / MAX_HASH_DIFFERENCE - 1), 3)

        webm_tuple = LoopRecord(
            webm_name,
            gif_name,
            normalized_score,
            frame_length,
            start_frame_number,
            end_frame_number,
            webm_location,
            gif_location,
            mp4_location,
        )

        tuples_list.append(webm_tuple)

    return tuples_list


#######################################################################################################################


# Check if the params we've been given for start & end are valid
def check_valid_interval(start_time, end_time, duration):
    if start_time < 0 or end_time < 0:
        return False
    elif end_time - start_time < 0:
        return False
    elif end_time - start_time > MAX_VIDEO_SEARCH_LENGTH:
        return False
    elif start_time > duration:
        return False

    return True


#######################################################################################################################


def make_loops(
    path_of_source_video, start_time=0, end_time=20, callback=None, sound_enabled=True
):
    # avoid repetitive callback checks and simply use this function
    def safe_callback(status, progress):
        if callback:
            callback(status, progress)

    source_video_folder = os.path.dirname(path_of_source_video)

    # Loops destination folder
    webm_destination_folder = os.path.join(source_video_folder, "Loops")

    # Remove file ext --> generate folder name --> generate complete path
    video_file_name = basename(path_of_source_video)
    video_file_name_no_ext = os.path.splitext(video_file_name)[0]
    frame_directory_name = "ALL_FRAMES_" + video_file_name_no_ext
    frame_directory_path = os.path.join(source_video_folder, frame_directory_name)

    # We'll use this folder to hold frames needed by ffmpeg for loop creation
    temp_frames_folder = os.path.join(frame_directory_path, "temp")

    start_time = float(start_time)
    end_time = float(end_time)
    duration = get_duration(path_of_source_video)

    if not check_valid_interval(start_time, end_time, duration):
        raise InvalidIntervalException()

    # Create all the directories we'll need to store loops, frames, stabilization, etc
    create_directories(
        webm_destination_folder, frame_directory_path, temp_frames_folder
    )

    # Get the frame rate so that we can then use it to calculate the number of frames
    frame_rate = get_frame_rate(path_of_source_video)

    # Calculate the hashes we're going to iterate through
    hash_dictionary, hashed_frames_list = hash_frames(
        path_of_source_video, safe_callback
    )

    hash_db = FrameHashDatabase(hash_dictionary, path_of_source_video)

    # Start searching the entire list of frames for loops, then add ffmpeg commands for each candidate
    best_webm_candidates = search_for_loops(
        hashed_frames_list, hash_db, frame_rate, safe_callback
    )
    best_webm_candidates = add_info_to_candidates(
        best_webm_candidates,
        webm_destination_folder,
        path_of_source_video,
        frame_directory_path,
        sound_enabled,
    )

    # Create some number of loops after search has finished
    create_candidate_loops(best_webm_candidates, safe_callback)

    # Delete video, and all frames folders
    clean_up_folders(temp_frames_folder, frame_directory_path, path_of_source_video)

    results = get_video_info_tuple(best_webm_candidates, webm_destination_folder)

    return results


#######################################################################################################################


if __name__ == "__main__":
    # To profile, try `python -m cProfile -s cumtime loops.py Samples/sample.mp4`
    # Also see `profiling.md` for more info
    DEBUG_MODE = True
    make_loops(*sys.argv[1:])

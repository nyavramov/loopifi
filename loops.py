from ntpath import basename
from PIL import Image
from collections import namedtuple

import glob
import imagehash
import os
import re
import shutil
import subprocess
import sys

##############################################################################################################
# Constants
##############################################################################################################

# max amount of time between start and end timestamps
MAX_VIDEO_SEARCH_LENGTH = 30

# phash related hash constants
HASH_SIZE = 128
MAX_HASH_DIFFERENCE = 65536
SIMILARITY_THRESHOLD = MAX_HASH_DIFFERENCE * 0.75

# Enable to prevent temporary files from being deleted
# Use from env-var like `DEBUG_MODE=1 python loops.py ...` or `DEBUG_MODE=1 flask rq worker`
DEBUG_MODE = os.environ.get('DEBUG_MODE', False)

##############################################################################################################
# Class Definitions
##############################################################################################################

LoopRecord = namedtuple("webm", ["webmName", "gifName", "score", "frameLength", "startFrameNumber", "endFrameNumber",
                           "webmLocation", "gifLocation", "mp4Location"])


class FrameHashDatabase(object):

    def __init__(self, existing_hashes):
        self.db = existing_hashes

    def get(self, filename):
        if filename not in self.db:
            self.db[filename] = imagehash.phash(Image.open(filename), hash_size=HASH_SIZE)

        return self.db[filename]


class CandidateLoop(object):
    def __init__(self, score, startFrameNumber, endFrameNumber, frameRate):

        self.score            = score
        self.startFrameNumber = startFrameNumber
        self.endFrameNumber   = endFrameNumber
        self.frameRate        = frameRate

        self.startTime = self.startFrameNumber / frameRate
        self.duration  = (self.endFrameNumber - self.startFrameNumber) / frameRate
        
        self.gifPaletteCommand = None
        self.gifEncodeCommand  = None
        self.webmEncodeCommand = None 
        self.mp4EncodeCommand  = None

        self.gifName  = None
        self.webmName = None
        self.mp4Name  = None


class InvalidIntervalException(Exception):
    """Thrown when module called with invalid start and end timestamps"""

#######################################################################################################################
# Function Definitions
#######################################################################################################################


# Clean up the various files & folders we generated at the start of the loop creation process
# TODO should put all temporary files into a single directory that can be either deleted
#  or not based on a `DEBUG_MODE` flag
def cleanUpFolders(tempFramesFolder, frameDirectoryPath, pathOfSourceVideo, stableVideoPath):

    if DEBUG_MODE:
        return

    foldersToRemove = [tempFramesFolder, frameDirectoryPath] 

    vectorFile = os.path.join(os.path.dirname(pathOfSourceVideo), "transform_vectors.trf")
    
    filesToRemove = [vectorFile, pathOfSourceVideo]

    # If we choose not to stabilize video, stable video path *becomes* the path of source video
    # So for testing purposes, let's not delete the stable video since we'd be deleting the source video
    if stableVideoPath != pathOfSourceVideo:
        filesToRemove.append(stableVideoPath)

    for folder in foldersToRemove:
        try:
            shutil.rmtree(folder)
        except:
            pass

    for file in filesToRemove:
        try:
            os.remove(file)
        except:
            pass


#######################################################################################################################

# Get how long the video is
def getDuration(video_path):
    
    command = ["ffprobe",
                "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                video_path]

    duration_string = subprocess.check_output(command, encoding='UTF-8')

    duration = float(duration_string)

    return duration

#######################################################################################################################

# Due to complications with start/end time, we need this fps function for number of frames calculation
def getFrameRate(video_path):

    command = ["ffprobe",
                "-v", "0",
                "-of", "csv=p=0",
                "-select_streams", "V:0",
                "-show_entries", "stream=r_frame_rate",
                video_path]

    frame_rate_string = subprocess.check_output(command, encoding='UTF-8')

    # ffmpeg will report like 30000/1000
    num, div = frame_rate_string.split('/')
    frame_rate = int(num) / int(div)

    return frame_rate

#######################################################################################################################

# Split a video into its constituent frames
def splitVideoIntoFrames(frameDirectoryPath, stableVideoPath, callback):

    ffmpegSplitVideoSyntax = "{}/%d.png".format(frameDirectoryPath)

    # ffmpeg split command
    command = ['ffmpeg',
               "-i", stableVideoPath,
            ffmpegSplitVideoSyntax]

    callback("Splitting video into frames...", 20)

    subprocess.run(command)

    callback("Finished splitting video...", 40)
    
#######################################################################################################################

# Creates directories called Loops & ALL_FRAMES_{videoName} & temp if they don't already exist 
def createDirectories(*paths):
    for path in paths:
        if not os.path.exists(path):
            os.makedirs(path)

#######################################################################################################################

# Calculate stabilization vectors --> Stabilize video
def stabilizeVideo(pathOfSourceVideo, loopWidth, stableVideoPath, startTime, endTime, callback):
    
    folderOfSourceVideo = os.path.dirname(pathOfSourceVideo)
    duration            = endTime - startTime

    # Prior to stabilizing the video, we'll need to calculate the stabilization vectors we need
    calculateVectorCommand = ['ffmpeg',
                              "-y",
                              "-threads", "8",
                              "-i", "{}".format(pathOfSourceVideo),
                              "-vf",  "vidstabdetect=stepsize=6:shakiness=4:accuracy=5:"
                              "result={}/transform_vectors.trf".format(os.path.dirname(pathOfSourceVideo)),
                              "-f", "null",
                              "-"]

    # Now we can use libvidstab to stabilize video using the .trf vector file we just created
    stabilizeCommand = ['ffmpeg',
                        "-threads", "8",
                        "-y",   
                        "-i", pathOfSourceVideo,
                        "-ss", str(startTime),
                        "-t", str(duration),
                        "-vf", "vidstabtransform=input={}/transform_vectors.trf:"
                        "zoom=1:smoothing=30,unsharp=5:5:0.8:3:3:0.4".format(folderOfSourceVideo,
                        loopWidth),
                        "-vcodec", "libx264",
                        "-acodec", "copy",
                        "-preset", "fast",
                        "-tune", "film",
                        "-crf", "17",
                        "-acodec", "copy",
                        stableVideoPath]
    
    stabilizeProgress = 0

    callback("Stabilizing video...", stabilizeProgress)

    for command in (calculateVectorCommand, stabilizeCommand):
        
        callback("Stabilizing video...", stabilizeProgress)

        # run the command
        subprocess.run(command)

        stabilizeProgress += 10

#######################################################################################################################

# We'll use this to tell FFMPEG what kind of GIF/WEBM we want, i.e., give it correctly formatted parameters
def prepareWebmInfo(candidate, webmDestinationFolder, stableVideoPath, soundEnabled, counter):
    
    webmName = "{}.webm".format(counter)
    webmDestination = os.path.join(webmDestinationFolder, webmName)

    webmEncodeCommand = ["ffmpeg",
                         "-y",
                         "-ss", str(candidate.startTime),
                         "-t", str(candidate.duration),
                         "-i", stableVideoPath]

    if not soundEnabled:
        webmEncodeCommand.append("-an")

    # This part of command will then process all frames in temp directory to output to GIF/WEBM
    webmEncodeCommand.extend(["-minrate", "1700k",
                              "-b:v", "1800K",
                              "-maxrate", "2000K",
                              "-c:v", "libvpx",
                              "-vf", "scale=500:-2",
                              webmDestination])

    candidate.webmEncodeCommand = webmEncodeCommand
    candidate.webmName          = webmName

    return candidate
    
#######################################################################################################################

def prepareGifInfo(candidate, webmDestinationFolder, stableVideoPath, frameDirectoryPath, counter):

    gifName = "{}.gif".format(counter)
    gifDestination = os.path.join(webmDestinationFolder, gifName)
    paletteDestination = os.path.join(frameDirectoryPath, "palette.png")

    gifPaletteCommand = ["ffmpeg", 
                         "-y", 
                         "-ss", str(candidate.startTime),
                         "-t", str(candidate.duration),
                         "-i", stableVideoPath,
                         "-vf", "scale=500:-2:flags=lanczos,palettegen",
                         paletteDestination]

    gifEncodeCommand = ["ffmpeg", 
                        "-y", 
                        "-ss", str(candidate.startTime),
                        "-t", str(candidate.duration),
                        "-i", stableVideoPath,
                        "-i", paletteDestination,
                        "-filter_complex", "fps=25,scale=500:-2:flags=lanczos[x];[x][1:v]paletteuse",
                        gifDestination]
    
    candidate.gifPaletteCommand = gifPaletteCommand
    candidate.gifEncodeCommand  = gifEncodeCommand
    candidate.gifName           = gifName

    return candidate

#######################################################################################################################

def prepareMp4Info(candidate, webmDestinationFolder, stableVideoPath, soundEnabled, counter):

    mp4Name = "{}.mp4".format(counter)
    mp4Destination = os.path.join(webmDestinationFolder, mp4Name)

    mp4EncodeCommand = ["ffmpeg",
                        "-y",
                        "-ss", str(candidate.startTime),
                        "-t", str(candidate.duration),
                        "-i", stableVideoPath,
                        "-an",
                        "-b:v", "1800K",
                        "-c:v", "libx264",
                        "-vf", "scale=500:-2",
                        mp4Destination]

    if soundEnabled:
        mp4EncodeCommand.remove("-an")

    candidate.mp4EncodeCommand = mp4EncodeCommand
    candidate.mp4Name          = mp4Name

    return candidate

#######################################################################################################################

# We'll clean/populate the temp directory and then create the loops from list of sorted candidates
def createCandidateLoops(bestWebmCandidates, numberWebmsToMake, tempFramesFolder, frameDirectoryPath, callback):

    percentPerWebm = 20 / numberWebmsToMake
    encodeProgress = 80

    callback("Encoding webms...", encodeProgress)
    
    for i in range(0, min(len(bestWebmCandidates), numberWebmsToMake)):

        gifPaletteCommand = bestWebmCandidates[i].gifPaletteCommand
        gifEncodeCommand  = bestWebmCandidates[i].gifEncodeCommand
        webmEncodeCommand = bestWebmCandidates[i].webmEncodeCommand
        mp4EncodeCommand  = bestWebmCandidates[i].mp4EncodeCommand

        for command in (gifPaletteCommand, gifEncodeCommand, webmEncodeCommand, mp4EncodeCommand):
            subprocess.run(command)

        encodeProgress = encodeProgress + percentPerWebm

        callback("Encoding webms...", encodeProgress)

#######################################################################################################################

# TODO remove magic numbers in favor of constants at top of module
def compareCandidates(startFrame, candidateFrame, hashDb, bestScoreThisIteration, similarityThreshold):

    startHash     = hashDb.get(startFrame)
    candidateHash = hashDb.get(candidateFrame)

    currentCandidateSimilarity = startHash - candidateHash
    currentCandidateSimilarity = float(currentCandidateSimilarity)

    startFrameName = basename(startFrame)
    endFrameName   = basename(candidateFrame)
    
    # Keep track of which of the candidates get the best score when compared to start frame
    if currentCandidateSimilarity < similarityThreshold and \
       currentCandidateSimilarity < bestScoreThisIteration:

        # Get the number of the start frame 
        startFrameNumber = startFrameName.replace(".png", "")
        startFrameNumber = int(startFrameNumber)

        # Get the number of the end frame
        endFrameNumber = endFrameName.replace(".png", "")
        endFrameNumber = int(endFrameNumber)
        
        middleFrame     = str(( endFrameNumber + startFrameNumber ) // 2) + ".png"
        middleFramePath = os.path.join(os.path.dirname(startFrame), middleFrame)
        middleFrameHash = hashDb.get(middleFramePath)

        startMiddlePercentDiff = ( (startHash - middleFrameHash) / MAX_HASH_DIFFERENCE) * 100
        if startMiddlePercentDiff < 4:
            return None
        
        bestScoreThisIteration = currentCandidateSimilarity

        return bestScoreThisIteration, startFrameNumber, endFrameNumber

    return None

#######################################################################################################################

def addInfoToCandidates(bestWebmCandidates, webmDestinationFolder, stableVideoPath, frameDirectoryPath, soundEnabled):

    for counter, candidate in enumerate(bestWebmCandidates, 1):

        prepareWebmInfo(candidate, webmDestinationFolder, stableVideoPath, soundEnabled, counter)
        prepareGifInfo(candidate, webmDestinationFolder, stableVideoPath, frameDirectoryPath, counter)
        prepareMp4Info(candidate, webmDestinationFolder, stableVideoPath, soundEnabled, counter)

    return bestWebmCandidates

#######################################################################################################################

# Main program loop. As the name suggests, we use this to go through each frame and evaluate 
# start frames vs candidates
def searchForLoops(hashedFramesList, hashDb, searchOptions, callback):

    minimumLoopFrames, maximumLoopFrames, searchStepSize, similarityThreshold, frameRate = searchOptions

    iteration              = 0  # What iteration of the search process we're on
    bestWebmCandidates     = [] # Store commands & information corresponding to top loop candidates
    
    callback("Searching for loops...", 60)

    # Loop through every hash, comparing start hashes to candidates hashes
    for startFrame in hashedFramesList:
        bestCandidate    = None
        iteration        = iteration + 1
        candidateCounter = 0 # Limits min & max number of candidates to compare to 1st frame in window
        
        # Move candidate search window & initialize highest similarity score to 0
        # Highest similarity refers to best candidate frame in current window
        candidateFrames        = hashedFramesList[iteration:]
        bestScoreThisIteration = MAX_HASH_DIFFERENCE
        
        # Loop though every candidate frame and compare to start frame
        for candidateFrame in candidateFrames:
            candidateCounter = candidateCounter + searchStepSize 
            
            if candidateCounter < minimumLoopFrames:
                continue 
            elif candidateCounter > maximumLoopFrames:
                break
            else:
                aCandidate = compareCandidates(startFrame, candidateFrame, hashDb,
                                               bestScoreThisIteration, similarityThreshold)
                if aCandidate is not None:
                    bestCandidate = aCandidate
                    bestScoreThisIteration, _, _ = aCandidate
 
        # If we've found a loop after comparing all the candidates, we can create it
        if bestCandidate is not None:
            bestScoreThisIteration, startFrameNumber, endFrameNumber = bestCandidate      
            newCandidate = CandidateLoop(bestScoreThisIteration, startFrameNumber, endFrameNumber, frameRate)
            # Append the candidate loop along with its score, start, end, & framerate
            bestWebmCandidates.append(newCandidate)

    callback("Searching for loops...", 80)
        
    # Since bestWebmCandidates is a list of lists... aka... [ [0.89, commandString], [0.91, commandString] ]
    # Sort the outer list based on first item (score) of each inner list, highest to lowest score
    bestWebmCandidates.sort(key = lambda x: x.score) 
    return bestWebmCandidates

#######################################################################################################################

def hashFrames(searchStepSize, frames, callback):

    hashDictionary   = {}
    hashedFramesList = []
    hashIteration    = 0

    callback("Preparing to search...", 40)

    for frame in frames:
        hashIteration = hashIteration + 1

        # Don't hash all frames, only the ones we want to look at
        if hashIteration % searchStepSize != 0:
            continue

        # Append each hash to a hashes list, and add hash as kay to corresponding frame name
        aHash = imagehash.phash(Image.open(frame), hash_size=HASH_SIZE)

        hashDictionary[frame] = aHash
        hashedFramesList.append(frame)
    
    callback("Preparing to search...", 60)

    return hashDictionary, hashedFramesList

#######################################################################################################################

# Let's compose a list of all the frames in the video
def getFrameList(path):
    # find all png files in the frame directory path
    search = os.path.join(path, '*.png')

    # sort the results based on a special numerical sort
    frames = sorted(glob.glob(search), key=numericalSort)

    return frames

#######################################################################################################################

def getVideoInfoTuple(bestWebmCandidates, numberWebmsToMake, webmDestinationFolder):
    
    listOfTuples = [] # We'll store our namedtuples here

    for i in range(min(numberWebmsToMake, len(bestWebmCandidates))):

        score            = bestWebmCandidates[i].score
        startFrameNumber = bestWebmCandidates[i].startFrameNumber
        endFrameNumber   = bestWebmCandidates[i].endFrameNumber
        webmName         = bestWebmCandidates[i].webmName
        gifName          = bestWebmCandidates[i].gifName
        mp4Name          = bestWebmCandidates[i].mp4Name

        relativePathWebm = os.path.join(webmDestinationFolder, webmName)
        webmLocation     = os.path.abspath(relativePathWebm)

        relativePathGif = os.path.join(webmDestinationFolder, gifName)
        gifLocation     = os.path.abspath(relativePathGif)

        relativePathMp4 = os.path.join(webmDestinationFolder, mp4Name)
        mp4Location     = os.path.abspath(relativePathMp4)

        frameLength = endFrameNumber - startFrameNumber

        normalizedScore = round(-1 * (score / MAX_HASH_DIFFERENCE - 1), 3)
        
        webmTuple = LoopRecord(webmName, gifName, normalizedScore, frameLength, startFrameNumber,
                               endFrameNumber, webmLocation, gifLocation, mp4Location)
        
        listOfTuples.append(webmTuple)
    
    return listOfTuples

#######################################################################################################################

# So that we can override whatever black magic on the OS sorts the frames incorrectly
# This sorts the frames in our folder in correct numerical order: 1.png, 2.png, 3.png.
def numericalSort(value):

    numbers     = re.compile(r'(\d+)')
    parts       = numbers.split(value)
    parts[1::2] = map(int, parts[1::2])
    
    return parts

#######################################################################################################################

# Check if the params we've been given for start & end are valid
def checkValidInterval(startTime, endTime, duration):
    if startTime < 0 or endTime < 0:
        return False
    elif endTime - startTime < 0:
        return False
    elif endTime - startTime > MAX_VIDEO_SEARCH_LENGTH:
        return False
    elif startTime > duration:
        return False

    return True
    
#######################################################################################################################

def makeLoops(pathOfSourceVideo, startTime = 0, endTime = 20, callback = None, soundEnabled = True, stabilizeEnabled = True):
    # avoid repetitive callback checks and simply use this function
    def safe_callback(status, progress):
        if callback:
            callback(status, progress)

    sourceVideoFolder = os.path.dirname(pathOfSourceVideo)

    # Get path of stabilized video
    if stabilizeEnabled:
        stableVideoFileName = "STBL_" + basename(pathOfSourceVideo)
        stableVideoPath     = os.path.join(sourceVideoFolder, stableVideoFileName)
    else:
        stableVideoPath = pathOfSourceVideo

    # Loops destination folder
    webmDestinationFolder = os.path.join(sourceVideoFolder, "Loops")

    # Remove file ext --> generate folder name --> generate complete path
    videoFileName      = basename(pathOfSourceVideo)
    videoFileNameNoExt = os.path.splitext(videoFileName)[0]
    frameDirectoryName = "ALL_FRAMES_" + videoFileNameNoExt
    frameDirectoryPath = os.path.join(sourceVideoFolder, frameDirectoryName)

    # We'll use this folder to hold frames needed by ffmpeg for loop creation
    tempFramesFolder = os.path.join(frameDirectoryPath, "temp")

    startTime         = float(startTime)       
    endTime           = float(endTime)         
    loopWidth         = 500              # The width in pixels of an encoded webm
    searchStepSize    = 5                # Granularity/specificity of the loop search
    numberWebmsToMake = 5                # How many webms we would like to make in total
    minimumLoopFrames = 35               # The minimum number of frames in a webm
    maximumLoopFrames = 165              # The maximum number of frames in a webm

    duration = getDuration(pathOfSourceVideo)

    if not checkValidInterval(startTime, endTime, duration):
        raise InvalidIntervalException()

    # Create all the directories we'll need to store loops, frames, stabilization, etc
    createDirectories(webmDestinationFolder, frameDirectoryPath, tempFramesFolder)

    # Get the frame rate so that we can then use it to calculate the number of frames
    frameRate = getFrameRate(pathOfSourceVideo)

    if stabilizeEnabled:
        # Stabilize the video using libvidstabdetect
        stabilizeVideo(pathOfSourceVideo, loopWidth, stableVideoPath, startTime, endTime, safe_callback)

    # Split the video into constituent frames so we can compare individual frames
    splitVideoIntoFrames(frameDirectoryPath, stableVideoPath, safe_callback)

    # Get a list of all frame names that we just created, then insert them into dictionary
    frames = getFrameList(frameDirectoryPath)

    # Calculate the hashes we're going to iterate through 
    hashDictionary, hashedFramesList = hashFrames(searchStepSize, frames, safe_callback)
    hashDb                           = FrameHashDatabase(hashDictionary)

    # Start searching the entire list of frames for loops, then add ffmpeg commands for each candidate
    searchOptions      = (minimumLoopFrames, maximumLoopFrames, searchStepSize, SIMILARITY_THRESHOLD, frameRate)
    bestWebmCandidates = searchForLoops(hashedFramesList, hashDb, searchOptions, safe_callback)
    bestWebmCandidates = addInfoToCandidates(bestWebmCandidates, webmDestinationFolder, stableVideoPath, 
                         frameDirectoryPath, soundEnabled)

    # Create some number of loops after search has finished
    createCandidateLoops(bestWebmCandidates, numberWebmsToMake, tempFramesFolder, frameDirectoryPath, safe_callback)
    
    # Delete stable video, and all frames folders
    cleanUpFolders(tempFramesFolder, frameDirectoryPath, pathOfSourceVideo, stableVideoPath)  

    results = getVideoInfoTuple(bestWebmCandidates, numberWebmsToMake, webmDestinationFolder)

    return results

#######################################################################################################################


if __name__ == '__main__':
    # To profile, try `python -m cProfile -s cumtime loops.py Samples/sample.mp4`
    # Also see `profiling.md` for more info
    DEBUG_MODE = True
    makeLoops(*sys.argv[1:])

import os
import subprocess
from ntpath import basename

def getListOfWebms(rootFolder):

    listOfWebms = []

    for subdir, dirs, files in os.walk(rootFolder):
        for file in files:
            if file.endswith(".webm"):
                listOfWebms.append(os.path.join(subdir, file))

    return listOfWebms

def convertToGif(basePath, fullWebmPath, webmNameNoExtension):

    gifName = webmNameNoExtension + ".gif"

    paletteDestination = os.path.join(basePath, "palette.png")
    gifDestination     = os.path.join(basePath, gifName)

    gifPaletteCommand = ["ffmpeg", 
                         "-y", 
                         "-i", fullWebmPath,
                         "-vf", "fps=25,scale=500:-2:flags=lanczos,palettegen",
                         "{}".format(paletteDestination)]

    gifEncodeCommand = ["ffmpeg",
                        "-y",
                        "-i", fullWebmPath,
                        "-i", paletteDestination,
                        "-filter_complex", "fps=25,scale=500:-2:flags=lanczos[x];[x][1:v]paletteuse",
                        "{}".format(gifDestination)]

    for command in [gifPaletteCommand, gifEncodeCommand]:

        runningProcess = subprocess.Popen(command, stdout=subprocess.PIPE, 
                         stderr=subprocess.STDOUT, universal_newlines=True)

        while runningProcess.poll() is None:
            print(runningProcess.stdout.readline())
            continue

    os.remove(paletteDestination)

def convertToMp4(basePath, fullWebmPath, webmNameNoExtension):

    mp4Name = webmNameNoExtension + ".mp4"

    mp4Destination = os.path.join(basePath, mp4Name)

    mp4EncodeCommand = ["ffmpeg",
                        "-y",
                        "-i", fullWebmPath, 
                        "-c:v", "libx265", 
                        "-b:v", "1800K", 
                        "-vf", "fps=25",
                        "{}".format(mp4Destination)]

    runningProcess = subprocess.Popen(mp4EncodeCommand, stdout=subprocess.PIPE, 
                     stderr=subprocess.STDOUT, universal_newlines=True)

    while runningProcess.poll() is None:
        print(runningProcess.stdout.readline())
        continue

if __name__ == '__main__':
    
    rootFolder = '/PATH/TO/WEBMS/'
    
    listOfWebmPaths = getListOfWebms(rootFolder)

    for fullWebmPath in listOfWebmPaths:

        basePath = os.path.dirname(fullWebmPath)
        baseName = basename(fullWebmPath).split(".webm")[0]

        convertToGif(basePath, fullWebmPath, baseName)
        convertToMp4(basePath, fullWebmPath, baseName)

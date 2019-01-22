# [Loopifi.com](https://loopifi.com) - Find smooth loops in videos
![](https://imgur.com/54DuAUR.gif) ![](https://imgur.com/XrNK4Zd.gif)

## What is this?
This is the source code for [loopifi.com](https://loopifi.com) created by me and [Tristan Kernan](https://github.com/tristanmkernan).

Loopifi.com is a website created to help people find and make smooth loops from videos. It allows users to create and download smoothly looping gifs and webms from youtube and other video streaming sites, or upload their own videos.

## How does the algorithm work?
The basic idea is that a smooth loop is one where the first and last frames of a series of frames are similar. If we can find 2 similar frames separated by some number of frames in between them, then that's potentially a smooth loop. 

An input video is uploaded by the user or downloaded via youtube-dl. The video may then be stabilized according to the user's specifications. Then the video is split into frames.  Frames are then iteratively hashed using pHash. The Hamming distance between two candidate frames is calculated in order to determine if the frames are similar. The middle frame between 2 potential candidate frames is compared to the start of the loop to ensure that there is stuff actually happening (that we're not simply making a loop from a series of black frames, for instance). If the two candidate frames are sufficiently similar, above a set similarity threshold, then those candidates are added to a list.

Finally, the top N candidate loops with the highest similarity scores are selected and encoded to GIF, WEBM, and MP4 format. 

## What did you use to build this?
Docker (Apache License 2.0), Docker-compose (Apache License 2.0), Flask	(BSD), Flask Migrate	(MIT), Flask RQ2 (MIT), Flask SQLAlchemy (BSD), ImageHash (BSD), Pillow	PIL (SL), youtube-dl	(Unlicensed), Cult of the Party Parrot (CC BY-SA 4.0), Bulma (MIT), Bulma Extensions (MIT), FFmpeg (LGPL-2).

## How do I run this?
Assuming you have docker and docker-compose already installed, clone the repo and simply run `docker-compose up --build` to build and run the docker image. Then go to `localhost:8084` to use loopifi. You can also check out the live version of the site at [loopifi.com](https://loopifi.com).


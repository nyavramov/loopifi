# [loopifi.com](https://loopifi.com) - Find smooth loops in videos
![](https://imgur.com/54DuAUR.gif) ![](https://imgur.com/XrNK4Zd.gif)

## What is this?

This is the source code for [loopifi.com](https://loopifi.com), created by me and [Tristan](https://github.com/tristanmkernan).

We created loopifi to help people find and make smooth loops from videos. 
It allows users to create and download smoothly looping gifs and webms from youtube and other video streaming sites, or upload their own videos.

## How does the algorithm work?

We define a smooth loop as a sequence of video frames, such that the first and last frames have a high similarity.

The input video is either uploaded by the user or downloaded via youtube-dl.
Then the video is split into individual frames, which are hashed using [perceptual hashing](https://www.phash.org/).
Next, each frame is compared to its neighbor frames using the hamming distance of the hashes. 
Care is given to prevent edge cases, such as an all-black set of frames. 
The middle frame between 2 potential candidate frames is compared to the start of the loop to ensure that there is sufficient change in the video. 
Finally, if the two candidates are similar and pass the edge tests, they are marked as a potential output.

The top 5 candidate loops, sorted by best match, are selected and encoded to .gif, .webm, and .mp4 format. 

## What did you use to build this?

We are super thankful to the free and open source software community, without which this project would not have been possible!

We note here some specific libraries and tools:

- Docker (Apache License 2.0)
- Docker-compose (Apache License 2.0) 
- Flask	(BSD)
- Flask Migrate	(MIT)
- Flask RQ2 (MIT)
- Flask SQLAlchemy (BSD)
- ImageHash (BSD)
- Pillow	PIL (SL)
- youtube-dl	(Unlicensed)
- Cult of the Party Parrot (CC BY-SA 4.0)
- Bulma (MIT)
- Bulma Extensions (MIT)
- FFmpeg (LGPL-2).

## How do I run this locally?

First, install [docker](https://docs.docker.com/install/) and [docker-compose](https://docs.docker.com/compose/install/).

Next, clone the repo:

```sh
$ git clone git@github.com:nyavramov/loopifi.git
```

Build the docker images:

```sh
$ # in loopifi/ directory
$ docker-compose build
```

Start the database first, and give it about 60 seconds to download and warm up:

```sh
$ # in loopifi/ directory
$ docker-compose up -d db # this runs the database in 'detached' mode
```

Now, boot redis:

```sh
$ # in loopifi/ directory
$ docker-compose up -d redis
```

Lastly, start up the web server and the workers:

```sh
$ # in loopifi/ directory
$ docker-compose up -d # this starts the remaining services
```

Note: in case you want to host this application yourself, be sure to change the secret key in `env/docker.env`!

Visit [localhost:8084](http://localhost:8084/) to use your local loopifi installation! 


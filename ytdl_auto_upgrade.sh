#!/usr/bin/env bash

# We list youtube-dl in requirements.txt with
# `youtube-dl>=2019.4.17`
# and build with
# `RUN pip install -U -r /app/requirements.txt`
# meaning that the package should be upgraded to the latest possible

docker-compose build
docker-compose up -d worker  # only restart the worker containers

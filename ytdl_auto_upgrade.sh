#!/usr/bin/env bash

# We list youtube-dl in requirements.txt with
# `youtube-dl>=2019.4.17`
# and build with
# `RUN pip install -U -r /app/requirements.txt`
# meaning that the package should be upgraded to the latest possible

# cd /wherever/your/directory/is/located/
docker-compose build --build-arg CACHE_DATE=$(date +%Y-%m-%d)
docker-compose up -d worker  # only restart the worker containers

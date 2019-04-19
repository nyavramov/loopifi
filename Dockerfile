FROM tiangolo/uwsgi-nginx-flask:python3.7

COPY requirements.txt /app/requirements.txt
WORKDIR /app
RUN pip install --upgrade pip

# thanks to https://github.com/moby/moby/issues/22832
ARG CACHE_DATE=2016-01-01

RUN pip install -U -r /app/requirements.txt
COPY . /app

ENV PATH="/app/ffmpeg:${PATH}"

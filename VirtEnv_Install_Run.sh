#!/bin/bash
python3 -m venv "VirtualEnv"
source VirtualEnv/bin/activate
pip3 install -r requirements.txt
python3 application.py
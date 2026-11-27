#!/bin/bash
# One-time Pi setup. Run from the repo folder:  bash football-model/pi/setup.sh
set -e
cd "$(dirname "$0")/.."                       # football-model/
sudo apt-get update && sudo apt-get install -y python3-venv python3-pip git
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install pandas numpy pyarrow flask
.venv/bin/python pi/bootstrap.py
echo
echo "Next: put your keys in /etc/environment (see pi/README.md), install the service and the schedule."

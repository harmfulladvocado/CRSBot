#!/bin/bash
cd /home/user/CRSBot

git fetch origin main
LOCAL=$(git rev-parse HEAD)
REMOTE=$(git rev-parse origin/main)

if [ "$LOCAL" != "$REMOTE" ]; then
    echo "$(date): New commit detected, pulling and restarting..."
    git pull origin main
    venv/bin/pip install -r requirements.txt
    sudo systemctl restart crsbot
fi
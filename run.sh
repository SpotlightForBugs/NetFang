#!/bin/bash

if [ "$1" == "-h" ]; then
    echo "Usage: ./run.sh [OPTION]"
    echo "Options:"
    echo "  -h    Display this help message"
    echo "  -u    Update the Netfang repository"
    echo "  --hidden    Run Netfang in the background"
    exit 0
fi

if [ "$1" == "-u" ]; then
    git pull
fi

# Make ARP helper executable if it's not already
chmod +x netfang/setup/arp_helper.py

sudo python netfang/setup/setup_manager.py && \

if [ "$1" == "--hidden" ]; then
    nohup sudo python -m netfang.main &
else
    sudo python -m netfang.main
fi

sudo python netfang/setup/setup_manager.py stop
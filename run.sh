#!/bin/bash

if [ "$1" == "-u" ]; then
    git pull
fi
if [ "$1" == "-h" ]; then
    echo "Usage: ./run.sh [-u]"
    echo "  -u: Update the repository before running"
    exit 0
fi

#turn off HDMI
/usr/bin/tvservice -o # Turn off HDMI to save power

# Make ARP helper executable if it's not already
chmod +x netfang/setup/arp_helper.py

# Run the setup manager, start the main service, then stop the setup manager
sudo python netfang/setup/setup_manager.py && \
python -m netfang.main && \
sudo python netfang/setup/setup_manager.py stop

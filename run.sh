#!/bin/bash
# Make ARP helper executable if it's not already
chmod +x netfang/setup/arp_helper.py

sudo python netfang/setup/setup_manager.py && \
python -m netfang.main && \
sudo python netfang/setup/setup_manager.py stop
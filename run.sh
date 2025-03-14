#!/bin/bash

# Check for any local changes (tracked or untracked)
if [ -n "$(git status --porcelain)" ]; then
  echo "Local changes detected. Stashing changes before pulling."
  git stash -u    # -u to include untracked files
  git pull
  echo "Reapplying stashed changes."
  git stash pop
else
  echo "No local changes. Pulling latest changes."
  git pull
fi

# Make ARP helper executable if it's not already
chmod +x netfang/setup/arp_helper.py

# Run the setup manager, start the main service, then stop the setup manager
sudo python netfang/setup/setup_manager.py && \
python -m netfang.main && \
sudo python netfang/setup/setup_manager.py stop

#!/bin/bash
# Setup passwordless sudo for the ARP helper script (and optionally for waveshare_rgb_led_hat.py)

# Get the absolute path of the current directory
CURRENT_DIR=$(pwd)

ARP_HELPER_PATH="$CURRENT_DIR/netfang/scripts/arp_helper.py"
LED_SCRIPT_PATH="$CURRENT_DIR/scripts/waveshare_rgb_led_hat.py"

# Make both scripts executable
chmod +x "$ARP_HELPER_PATH"
chmod +x "$LED_SCRIPT_PATH"

# Create a sudoers file entry that allows the current user to run these scripts without a password
# If you only need arp_helper.py to have passwordless sudo, remove $LED_SCRIPT_PATH
echo "$USER ALL=(ALL) NOPASSWD: $ARP_HELPER_PATH | sudo tee /etc/sudoers.d/netfang-arp-helper"
echo "$USER ALL=(ALL) NOPASSWD: $LED_SCRIPT_PATH | sudo tee /etc/sudoers.d/netfang-rgb-helper"

# Set proper permissions on the sudoers file
sudo chmod 440 /etc/sudoers.d/netfang-arp-helper
sudo chmod 440 /etc/sudoers.d/netfang-rgb-helper

echo "Sudoers configuration completed."

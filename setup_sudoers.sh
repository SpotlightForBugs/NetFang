#!/bin/bash
# Setup passwordless sudo for the ARP helper script

# Get the absolute path of the current directory
CURRENT_DIR=$(pwd)
ARP_HELPER_PATH="$CURRENT_DIR/netfang/scripts/arp_helper.py"


# Make the ARP helper script executable
chmod +x "$ARP_HELPER_PATH"

# Create sudoers file entry
echo "$USER ALL=(ALL) NOPASSWD: $ARP_HELPER_PATH" | sudo tee /etc/sudoers.d/netfang-arp-helper

# Set proper permissions on the sudoers file
sudo chmod 440 /etc/sudoers.d/netfang-arp-helper

echo "Sudoers configuration for NetFang ARP helper completed."
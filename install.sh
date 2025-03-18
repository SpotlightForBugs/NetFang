#!/bin/bash

SERVICE_NAME="netfang.service"
SERVICE_PATH="/etc/systemd/system/$SERVICE_NAME"
SUDOERS_FILE="/etc/sudoers.d/netfang-setup-manager"

# This is where your run.sh is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
RUN_SCRIPT="$SCRIPT_DIR/run.sh"

# The user who will run the service
RUN_USER="NetFang"

usage() {
  cat <<EOF
Usage: sudo ./install.sh [OPTIONS]
  --uninstall   Remove netfang systemd service and sudoers file
  -h | --help   Show this help text
EOF
  exit 0
}

if [[ $EUID -ne 0 ]]; then
   echo "Please run this script as root: sudo ./install.sh"
   exit 1
fi

if [[ "$1" == "-h" || "$1" == "--help" ]]; then
    usage
fi

if [[ "$1" == "--uninstall" ]]; then
    echo "Uninstalling netfang service..."

    # Stop the service if running
    systemctl stop "$SERVICE_NAME" 2>/dev/null || true
    systemctl disable "$SERVICE_NAME" 2>/dev/null || true

    # Remove the service file
    if [ -f "$SERVICE_PATH" ]; then
      rm -f "$SERVICE_PATH"
    fi

    # Remove the sudoers file
    if [ -f "$SUDOERS_FILE" ]; then
      rm -f "$SUDOERS_FILE"
    fi

    # Reload systemd
    systemctl daemon-reload

    echo "netfang service uninstalled successfully."
    exit 0
fi

echo "Installing netfang service..."

# 1. Create a systemd service file
# Adjust ExecStart if you need to pass arguments to run.sh (like --hidden)
cat <<EOF > "$SERVICE_PATH"
[Unit]
Description=NetFang Service
After=network.target

[Service]
Type=simple
User=$RUN_USER
WorkingDirectory=$SCRIPT_DIR
ExecStart=/bin/bash $RUN_SCRIPT -u --hidden
Restart=on-failure
RestartSec = 5s
[Install]
WantedBy=multi-user.target
EOF



sudo usermod -aG kali-trusted $RUN_USER
echo "added $RUN_USER to kali-trusted group"
# 3. Reload systemd and enable the service
systemctl daemon-reload
systemctl enable "$SERVICE_NAME"
systemctl start "$SERVICE_NAME"

echo "netfang service installed and started successfully!"

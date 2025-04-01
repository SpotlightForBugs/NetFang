#!/bin/bash

SERVICE_NAME="netfang.service"
SERVICE_PATH="/etc/systemd/system/$SERVICE_NAME"
SUDOERS_FILE="/etc/sudoers.d/netfang-setup-manager"

# This is where your run.sh is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
RUN_SCRIPT="$SCRIPT_DIR/run.sh"


#if the flag "--without-additional-tools" is not passed, do the following:
    # Install additional tools
    if [[ "$1" != "--without-additional-tools" ]]; then
        echo "Installing additional tools..."
        sudo apt-get update
        sudo apt-get install -y btop htop curl
        echo "Additional tools installed."
    fi

#check if pip is installed, if not, install it
if ! command -v pip &> /dev/null; then
    echo "pip not found. Installing pip..."
    sudo apt-get install -y python3-pip
    echo "pip installed."
fi

#check if python3-venv is installed, if not, install it
if ! dpkg -l | grep python3-venv; then
    echo "python3-venv not found. Installing python3-venv..."
    sudo apt-get install -y python3-venv
    echo "python3-venv installed."
fi

#check if usb_modeswitch is installed, if not, install it
if ! dpkg -l | grep usb-modeswitch; then
    echo "usb-modeswitch not found. Installing usb-modeswitch..."
    sudo apt-get install -y usb-modeswitch usb-modeswitch-data
    echo "usb-modeswitch installed."
fi

# Automatically get the non-elevated username
if [ -n "$SUDO_USER" ]; then
    RUN_USER="$SUDO_USER"
elif [ -n "$LOGNAME" ]; then
    RUN_USER="$LOGNAME"
else
    # Fallback method using who
    RUN_USER=$(who am i | awk '{print $1}')
fi

# Validate that we got a username
if [ -z "$RUN_USER" ]; then
    echo "Error: Could not determine the original username."
    echo "Please run this script with sudo directly (not through su or other methods)."
    exit 1
fi

# check who owns the repository if it's not the $RUN_USER, change the ownership to $RUN_USER
if [ "$(stat -c '%U' "$SCRIPT_DIR")" != "$RUN_USER" ]; then
    echo "Changing ownership of $SCRIPT_DIR to $RUN_USER"
    sudo chown -R "$RUN_USER":"$RUN_USER" "$SCRIPT_DIR"
else
    echo "Ownership of $SCRIPT_DIR is already set to $RUN_USER"
fi

#make sure that the §RUN_USER owns its own home directory
if [ "$(stat -c '%U' /home/"$RUN_USER")" != "$RUN_USER" ]; then
    echo "Changing ownership of /home/$RUN_USER to $RUN_USER"
    sudo chown -R "$RUN_USER":"$RUN_USER" /home/"$RUN_USER"
else
    echo "Ownership of /home/$RUN_USER is already set to $RUN_USER"
fi

echo "adding the git repo to the safe directory list in case of bad permissions with the downloadable images"
git config --global --add safe.directory /home/"$RUN_USER"/"$SCRIPT_DIR" # eg /home/whitehat/netfang

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

echo "Installing netfang service with user: $RUN_USER..."

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
ExecStart=/bin/bash $RUN_SCRIPT -u
Restart=always
RestartSec=5
[Install]
WantedBy=multi-user.target
EOF

# Check if kali-trusted group exists before adding user to it
if getent group kali-trusted > /dev/null; then
    usermod -aG kali-trusted $RUN_USER
    echo "Added $RUN_USER to kali-trusted group"
else
    echo "Note: kali-trusted group doesn't exist on this system. Skipping group assignment."
fi

sudo bash headless.sh &

# 2. Reload systemd and enable the service
systemctl daemon-reload
systemctl enable "$SERVICE_NAME"
systemctl start "$SERVICE_NAME"

echo "netfang service installed and started successfully!"
echo "Service is running as user: $RUN_USER"
echo "Service status: $(systemctl is-active $SERVICE_NAME)"

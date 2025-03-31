#!/bin/bash

# Path to your user home and venv
VENV_DIR="$HOME/.netfang_venv"

# Parse command-line arguments
update_repo=false
run_hidden=false

while [[ $# -gt 0 ]]; do
  case $1 in
    -h)
      echo "Usage: ./run.sh [OPTIONS]"
      echo "  -h         Display help"
      echo "  -u         Update the repository"
      echo "  --hidden   Run in the background"
      exit 0
      ;;
    -u)
      update_repo=true
      ;;
    --hidden)
      run_hidden=true
      ;;
  esac
  shift
done

# Update the repository if requested
if [ "$update_repo" = true ]; then
  [ -f "netfang/config.json" ] && mv netfang/config.json /tmp/config.json && git stash
  git pull
  if [ -f "/tmp/config.json" ]; then
    mv /tmp/config.json netfang/config.json
    echo "Restored config.json"
    rm /tmp/config.json
  fi
fi

# Check if the virtual environment exists
if [ ! -d "$VENV_DIR" ] || [ ! -f "$VENV_DIR/bin/activate" ]; then
  echo "Virtual environment not found or corrupted. Creating a new one..."
  # Remove any existing venv
  rm -rf "$VENV_DIR"
  # Create a fresh virtual environment
  python3 -m venv "$VENV_DIR"
  echo "Virtual environment created."
else
  echo "Using existing virtual environment."
fi

# Activate the virtual environment
source "$VENV_DIR/bin/activate"
echo "Virtual environment activated."

# Ensure pip is installed and up to date
python -m ensurepip --upgrade
python -m pip install --upgrade pip
echo "Pip installed and updated."

# Check if requirements.txt exists
if [ ! -f "requirements.txt" ]; then
  echo "Error: requirements.txt not found in the current directory."
  echo "Current directory: $(pwd)"
  exit 1
fi

# Install requirements
pip install -r requirements.txt
echo "Requirements installed."

# Ensure scripts are executable
chmod +x netfang/scripts/arp_helper.py
chmod +x netfang/setup/setup_manager.py

# Run setup manager with sudo
echo "Running setup manager..."
sudo python netfang/setup/setup_manager.py &

echo "Starting network monitor..."
python netfang/api/netfang_monitor.py &

# Run the main application, optionally in the background
echo "Starting main application..."
if [ "$run_hidden" = true ]; then
  nohup python -m netfang.main > netfang.log 2>&1 &
  echo "Application running in background. Check netfang.log for output."
else
  python -m netfang.main
fi

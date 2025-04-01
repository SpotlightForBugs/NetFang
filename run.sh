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
  [ -f "netfang/config.json" ] && mv netfang/config.json /tmp/config.json &&git stash && git stash clear
  git pull
  if [ -f "/tmp/config.json" ]; then
    mv /tmp/config.json netfang/config.json
    echo "Restored config.json"
  fi
fi

# Check if either python3 or python is installed
if command -v python3 &> /dev/null; then
  py_exec="python3"
  echo "Python3 is installed."
elif command -v python &> /dev/null; then
  if python -V 2>&1 | grep -q "Python 3"; then
    py_exec="python"
    echo "Python 3.x is installed as python."
  else
    sudo apt-get install -y python3
    py_exec="python3"
    echo "Installed Python3."
  fi
else
  sudo apt-get install -y python3
  py_exec="python3"
  echo "Installed Python3."
fi

# Check if the virtual environment exists
if [ ! -d "$VENV_DIR" ] || [ ! -f "$VENV_DIR/bin/activate" ]; then
  echo "Virtual environment not found or corrupted. Creating a new one..."
  # Remove any existing venv
  rm -rf "$VENV_DIR"
  # Create a fresh virtual environment
  $py_exec -m venv "$VENV_DIR"
  echo "Virtual environment created."
else
  echo "Using existing virtual environment."
fi

# Activate the virtual environment
source "$VENV_DIR/bin/activate"
echo "Virtual environment activated."

# Ensure pip is installed and up to date
$py_exec -m ensurepip --upgrade
$py_exec -m pip install --upgrade pip
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

# Run the setup_manager with sudo
echo "Running setup manager..."
sudo $py_exec netfang/setup/setup_manager.py &

echo "Starting network monitor..."
$py_exec netfang/api/netfang_monitor.py &

# Run the main application, optionally in the background
echo "Starting main application..."
if [ "$run_hidden" = true ]; then
  nohup $py_exec -m netfang.main > netfang.log 2>&1 &
  echo "Application running in background. Check netfang.log for output."
else
  $py_exec -m netfang.main
fi

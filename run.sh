#!/bin/bash

# Path to your user home and venv.
VENV_DIR="$HOME/.netfang_venv"

# Check if the virtual environment exists
if [ ! -f "$VENV_DIR/bin/activate" ]; then
  echo "Virtual environment not found. Creating..."
  # Create and activate the virtual environment, then install requirements
  python3 -m venv "$VENV_DIR"
  echo "Virtual environment created."
  source "$VENV_DIR/bin/activate"
  echo "Virtual environment activated."
  pip install -r requirements.txt
  pip install eventlet>=0.33.1  # Ensure eventlet is installed
  echo "Requirements installed."
else
  # Activate the virtual environment and install requirements
  source "$VENV_DIR/bin/activate"
  pip install -r requirements.txt
  pip install eventlet>=0.33.1  # Ensure eventlet is installed
fi

update_repo=false
run_hidden=false

# Parse command-line arguments
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
  git pull
fi

# Ensure scripts are executable
chmod +x netfang/scripts/arp_helper.py
chmod +x netfang/setup/setup_manager.py

# Run setup manager with sudo
sudo python netfang/setup/setup_manager.py &

python netfang/api/netfang_monitor.py &

# Run the main application, optionally in the background
if [ "$run_hidden" = true ]; then
  nohup python -m netfang.main &
else
  python -m netfang.main
fi


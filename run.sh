#!/bin/bash

# Path to your user home and venv.
USER_HOME="/home/NetFang"
VENV_DIR="$USER_HOME/netfang/.venv"

# Check if the virtual environment exists
if [ ! -f "$VENV_DIR/bin/activate" ]; then
  # Create and activate the virtual environment, then install requirements
  python3 -m venv "$VENV_DIR"
  source "$VENV_DIR/bin/activate"
  pip install -r requirements.txt
else
  # Activate the virtual environment and install requirements
  source "$VENV_DIR/bin/activate"
  pip install -r requirements.txt
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

# Run setup manager with sudo (we'll give NetFang user no-password sudo for this)
sudo python netfang/setup/setup_manager.py

# Run the main application, optionally in the background
if [ "$run_hidden" = true ]; then
  nohup python -m netfang.main &
else
  python -m netfang.main
fi

# Optionally stop the setup manager at the end
# (If running in systemd, this may be undesired.)
sudo python netfang/setup/setup_manager.py stop

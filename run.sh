#!/bin/bash

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
      shift
      ;;
    --hidden)
      run_hidden=true
      shift
      ;;
    *)
      shift
      ;;
  esac
done

if [ "$update_repo" = true ]; then
  git pull
fi

chmod +x netfang/setup/arp_helper.py
chmod +x netfang/setup/setup_manager.py

sudo python netfang/setup/setup_manager.py &&

if [ "$run_hidden" = true ]; then
  sudo python -m netfang.main &
else
   python -m netfang.main
fi

sudo python netfang/setup/setup_manager.py stop

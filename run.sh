#!/bin/bash
sudo python netfang/setup/setup_manager.py && \
python -m netfang.main && \
sudo python netfang/setup/setup_manager.py stop
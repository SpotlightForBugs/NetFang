#!/bin/bash
sudo python netfang/setup_manager.py && \
python -m netfang.main && \
sudo python netfang/setup_manager.py stop
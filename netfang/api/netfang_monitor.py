#!/usr/bin/env python3
import json
import os
import subprocess
import time

# Assuming receiver.py remains in the same directory as this script.
MONITOR_DIR = os.path.dirname(os.path.abspath(__file__))
RECEIVER_PATH = os.path.join(MONITOR_DIR, "receiver.py")

with open('config.json') as f:
    data = json.load(f)
ethernet_interfaces = data["network_flows"]["network_interfaces"]["ethernet"]



def get_operstate(interface):
    try:
        with open(f"/sys/class/net/{interface}/operstate", "r") as f:
            return f.read().strip()
    except Exception:
        return None

def call_receiver(event, interface):
    print(f"Triggering event '{event}' for interface '{interface}'")
    subprocess.run(["/usr/bin/python3", RECEIVER_PATH, event, interface])

def monitor():
    last_state = None
    while True:
        for INTERFACE in ethernet_interfaces:
            state = get_operstate(INTERFACE)
            if state is None:
                print(f"Interface '{INTERFACE}' not found.")
            else:
                if last_state is None:
                    # On first detection, consider it as a cable insertion event.
                    call_receiver("cable_inserted", INTERFACE)
                    last_state = state
                elif state != last_state:
                    if state == "up":
                        call_receiver("connected", INTERFACE)
                    elif state == "down":
                        call_receiver("disconnected", INTERFACE)
                    last_state = state
            time.sleep(1)

if __name__ == "__main__":
    monitor()

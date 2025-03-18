import sys

import requests


def send_data(event_type, interface_name, retry=0):
    url = 'http://127.0.0.1:80/api/network-event'
    data = {'event_type': event_type, 'interface_name': interface_name}

    try:
        response = requests.post(url, json=data, timeout=5)
        response.raise_for_status()  # Raise an error for bad responses
    except Exception as e:
        if retry < 3:
            print(f"Retrying... Attempt {retry + 1}")
            send_data(event_type, interface_name, retry=retry + 1)
        else:
            print(f"Dropped event {event_type} for {interface_name} after 3 retries due to {e}")
            return
    else:
        print(response.text)

if __name__ == '__main__':
    print(sys.argv)
    # this can be called with python udev_receiver.py cable_inserted|connected|disconnected eth0|eth1|eth2|eth3|eth4
    event_type = sys.argv[1]
    interface_name = sys.argv[2]
    send_data(event_type, interface_name)

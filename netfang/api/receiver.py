import sys

import requests


def send_data(event_type, interface_name):
    url = 'http://127.0.0.1:80/api/network-event'
    data = {'event_type': event_type, 'interface_name': interface_name}
    response = requests.post(url, data=data, timeout=5)
    print(response.text)


if __name__ == '__main__':
    print(sys.argv)
    # this can be called with python receiver.py cable_inserted|connected|disconnected eth0|eth1|eth2|eth3|eth4
    event_type = sys.argv[1]
    interface_name = sys.argv[2]
    send_data(event_type, interface_name)

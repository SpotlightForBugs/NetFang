import requests


def send_data(event_type, interface_name):
    url = 'http://localhost:80/api/network_event'
    data = {'event_type': event_type}
    response = requests.post(url, data=data)
    print(response.text)


if __name__ == '__main__':
    # this can be called with python udev_receiver.py cable_inserted|connected|disconnected eth0|eth1|eth2|eth3|eth4
    import sys

    event_type = sys.argv[1]
    interface_name = sys.argv[2]
    send_data(event_type, interface_name)

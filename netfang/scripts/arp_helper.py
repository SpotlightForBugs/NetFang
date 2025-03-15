#!/usr/bin/env python3
import json
import sys

from scapy.layers.l2 import Ether, ARP, srp


def discover_mac_address(gateway_ip):
    """
    Discover the MAC address of a gateway IP using ARP requests.
    This requires root privileges to create raw sockets.
    """
    try:
        # Create and send ARP request
        broadcast = "ff:ff:ff:ff:ff:ff"
        arp_request = ARP(pdst=gateway_ip)
        broadcast_ether = Ether(dst=broadcast)
        arp_request_broadcast = broadcast_ether / arp_request
        
        # Send request and get response
        answered_list = srp(arp_request_broadcast, timeout=1, verbose=False)[0]
        
        # Process response
        for element in answered_list:
            if element[1].psrc == gateway_ip:
                return {
                    "success": True,
                    "mac_address": element[1].hwsrc
                }
        
        # If we reach here, no matching response was found
        return {
            "success": False,
            "error": f"No ARP response with matching gateway IP {gateway_ip}"
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }

if __name__ == "__main__":
    # Validate arguments
    if len(sys.argv) != 2:
        result = {
            "success": False,
            "error": "Usage: arp_helper.py <gateway_ip>"
        }
    else:
        # Get the gateway IP from command line argument
        gateway_ip = sys.argv[1]
        result = discover_mac_address(gateway_ip)
    
    # Output result as JSON
    print(json.dumps(result))
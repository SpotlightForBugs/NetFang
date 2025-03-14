#!/usr/bin/env python3
"""
Helper script to determine network status with root privileges.
Returns JSON with network interface information.
"""
import json
import sys
import netifaces

def get_active_interface():
    try:
        gateways = netifaces.gateways()
        default_gateway = gateways.get('default', [])
        if default_gateway and netifaces.AF_INET in default_gateway:
            # The interface is the second element in the tuple
            connected_interface = default_gateway[netifaces.AF_INET][1]
            return {
                "success": True,
                "interface": connected_interface
            }
        return {
            "success": True,
            "interface": ""  # No active interface with default gateway
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }

if __name__ == "__main__":
    result = get_active_interface()
    # Print as JSON to stdout for the parent process to parse
    print(json.dumps(result))
    sys.exit(0 if result["success"] else 1)
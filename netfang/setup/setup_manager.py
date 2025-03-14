import os
import subprocess
import sys

# New systemd unit file path & content
SYSTEMD_UNIT_PATH = "/etc/systemd/system/netfang-monitor.service"
MONITOR_SCRIPT_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), '../api/netfang_monitor.py'))
SYSTEMD_UNIT_CONTENT = f"""\
[Unit]
Description=NetFang Network Monitor Service
After=network.target

[Service]
Type=simple
ExecStart=/usr/bin/python3 {MONITOR_SCRIPT_PATH}
Restart=always

[Install]
WantedBy=multi-user.target
"""

def is_elevated():
    """Return True if the current user is root."""
    return os.getuid() == 0

def is_linux():
    """Return True if the operating system is Linux."""
    return os.name == "posix"

def should_deploy():
    """
    Check if deployment should proceed:
    - Only on Linux.
    - Only if '/proc/device-tree/model' exists and contains 'Raspberry Pi Zero 2 W'.
    """
    if not is_linux():
        return False
    try:
        with open("/proc/device-tree/model", "r") as f:
            model = f.read()
            return "Raspberry Pi Zero 2 W" in model
    except Exception:
        # File might not exist or cannot be read.
        return False

def setup_systemd_service():
    """Setup systemd service for network events on Raspberry Pi Zero 2 W."""
    print("Setting up systemd service for NetFang network monitoring...")
    # Write the systemd service file
    with open(SYSTEMD_UNIT_PATH, "w") as f:
        f.write(SYSTEMD_UNIT_CONTENT)
    print(f"Systemd service file written to {SYSTEMD_UNIT_PATH}")

    # Reload systemd daemon and enable the service immediately
    subprocess.run(["systemctl", "daemon-reload"], check=True)
    subprocess.run(["systemctl", "enable", "--now", "netfang-monitor.service"], check=True)

    print("Systemd service successfully enabled and started.")

def uninstall_systemd_service():
    """Uninstall the systemd service and remove the monitor."""
    print("Uninstalling systemd service for NetFang network monitoring...")

    # Stop and disable the service
    subprocess.run(["systemctl", "disable", "--now", "netfang-monitor.service"], check=True)

    # Remove the service file
    if os.path.exists(SYSTEMD_UNIT_PATH):
        os.remove(SYSTEMD_UNIT_PATH)
        print(f"Removed {SYSTEMD_UNIT_PATH}")

    subprocess.run(["systemctl", "daemon-reload"], check=True)
    print("Systemd service successfully uninstalled.")

def setup():
    """Main setup function to deploy or check NetFang system hooks."""
    if is_linux() and not is_elevated():
        print("NetFang needs root privileges to deploy.")
        sys.exit(1)

    if should_deploy():
        setup_systemd_service()
    else:
        print(
            "\033[91mNetFang does not support this device or operating system.\n"
            "No system hooks were installed.\n"
            "You can still use the test endpoint to simulate the system.\n"
            "Supported device: Raspberry Pi Zero 2 W\033[0m"
        )

def uninstall():
    """Main uninstall function to remove NetFang system hooks."""
    if is_linux() and not is_elevated():
        print("NetFang needs root privileges to uninstall.")
        sys.exit(1)

    if should_deploy():
        uninstall_systemd_service()
    else:
        print(
            "\033[91mNetFang does not support this device or operating system.\n"
            "No system hooks to clean up.\033[0m"
        )

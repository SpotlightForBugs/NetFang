#!/usr/bin/env python3
import os
import subprocess
import sys

# Base name for our systemd units
SYSTEMD_SERVICE_NAME = "netfang-network-monitor"
# Absolute paths for the main service and our additional units
SYSTEMD_SERVICE_PATH = f"/etc/systemd/system/{SYSTEMD_SERVICE_NAME}.service"

# Service units for specific events
SYSTEMD_INSERTED_SERVICE_PATH = f"/etc/systemd/system/{SYSTEMD_SERVICE_NAME}-inserted.service"
SYSTEMD_CONNECTED_SERVICE_PATH = f"/etc/systemd/system/{SYSTEMD_SERVICE_NAME}-connected.service"
SYSTEMD_DISCONNECTED_SERVICE_PATH = f"/etc/systemd/system/{SYSTEMD_SERVICE_NAME}-disconnected.service"

# .path unit files for triggering the events
SYSTEMD_PATH_INSERTED_PATH = f"/etc/systemd/system/{SYSTEMD_SERVICE_NAME}-inserted.path"
SYSTEMD_PATH_CONNECTED_PATH = f"/etc/systemd/system/{SYSTEMD_SERVICE_NAME}-connected.path"
SYSTEMD_PATH_DISCONNECTED_PATH = f"/etc/systemd/system/{SYSTEMD_SERVICE_NAME}-disconnected.path"

# For convenience when starting/stopping .path units, use just the filename.
SYSTEMD_PATH_INSERTED_UNIT = f"{SYSTEMD_SERVICE_NAME}-inserted.path"
SYSTEMD_PATH_CONNECTED_UNIT = f"{SYSTEMD_SERVICE_NAME}-connected.path"
SYSTEMD_PATH_DISCONNECTED_UNIT = f"{SYSTEMD_SERVICE_NAME}-disconnected.path"

# Absolute path to the udev receiver script (adjust as needed)
UDEV_RECEIVER_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "../api/udev_receiver.py")
)

# Main dummy service that simply exists as a dependency.
SYSTEMD_SERVICE_CONTENT = f"""\
[Unit]
Description=NetFang Network Monitor Service
After=network.target

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/bin/true

[Install]
WantedBy=multi-user.target
"""

# Service unit for handling cable insertion events.
SYSTEMD_INSERTED_SERVICE_CONTENT = f"""\
[Unit]
Description=Handle network cable insertion event
After=network.target

[Service]
Type=oneshot
ExecStart=/usr/bin/python3 {UDEV_RECEIVER_PATH} cable_inserted %i

[Install]
WantedBy=multi-user.target
"""

# Service unit for handling connection establishment events.
SYSTEMD_CONNECTED_SERVICE_CONTENT = f"""\
[Unit]
Description=Handle network connection established event
After=network.target

[Service]
Type=oneshot
ExecStart=/usr/bin/python3 {UDEV_RECEIVER_PATH} connected %i

[Install]
WantedBy=multi-user.target
"""

# Service unit for handling disconnection events.
SYSTEMD_DISCONNECTED_SERVICE_CONTENT = f"""\
[Unit]
Description=Handle network disconnection event
After=network.target

[Service]
Type=oneshot
ExecStart=/usr/bin/python3 {UDEV_RECEIVER_PATH} disconnected %i

[Install]
WantedBy=multi-user.target
"""

# .path unit for monitoring cable insertion.
SYSTEMD_PATH_INSERTED_CONTENT = f"""\
[Unit]
Description=Path Unit for Network Cable Insertion
After=network.target

[Path]
PathExists=/sys/class/net/%i/carrier
Unit={SYSTEMD_SERVICE_NAME}-inserted.service

[Install]
WantedBy=multi-user.target
"""

# .path unit for monitoring network connection changes.
SYSTEMD_PATH_CONNECTED_CONTENT = f"""\
[Unit]
Description=Path Unit for Network Connection Establishment
After=network.target

[Path]
PathChanged=/sys/class/net/%i/operstate
Unit={SYSTEMD_SERVICE_NAME}-connected.service

[Install]
WantedBy=multi-user.target
"""

# .path unit for monitoring network disconnection events.
SYSTEMD_PATH_DISCONNECTED_CONTENT = f"""\
[Unit]
Description=Path Unit for Network Disconnection
After=network.target

[Path]
PathChanged=/sys/class/net/%i/operstate
Unit={SYSTEMD_SERVICE_NAME}-disconnected.service

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
    - Only if '/proc/device-tree/model' exists and contains
      'Raspberry Pi Zero 2 W'.
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


def setup_systemd_units():
    """Setup systemd service and path units for network events."""
    print("Setting up systemd units for Raspberry Pi Zero 2 W...")

    # Write the main service unit
    with open(SYSTEMD_SERVICE_PATH, "w") as f:
        f.write(SYSTEMD_SERVICE_CONTENT)
    print(f"Main systemd service written to {SYSTEMD_SERVICE_PATH}")

    # Write the dedicated service units for events
    with open(SYSTEMD_INSERTED_SERVICE_PATH, "w") as f:
        f.write(SYSTEMD_INSERTED_SERVICE_CONTENT)
    print(f"Inserted service unit written to {SYSTEMD_INSERTED_SERVICE_PATH}")

    with open(SYSTEMD_CONNECTED_SERVICE_PATH, "w") as f:
        f.write(SYSTEMD_CONNECTED_SERVICE_CONTENT)
    print(f"Connected service unit written to {SYSTEMD_CONNECTED_SERVICE_PATH}")

    with open(SYSTEMD_DISCONNECTED_SERVICE_PATH, "w") as f:
        f.write(SYSTEMD_DISCONNECTED_SERVICE_CONTENT)
    print(f"Disconnected service unit written to {SYSTEMD_DISCONNECTED_SERVICE_PATH}")

    # Write the .path unit files that trigger the above service units
    with open(SYSTEMD_PATH_INSERTED_PATH, "w") as f:
        f.write(SYSTEMD_PATH_INSERTED_CONTENT)
    print(f"Inserted path unit written to {SYSTEMD_PATH_INSERTED_PATH}")

    with open(SYSTEMD_PATH_CONNECTED_PATH, "w") as f:
        f.write(SYSTEMD_PATH_CONNECTED_CONTENT)
    print(f"Connected path unit written to {SYSTEMD_PATH_CONNECTED_PATH}")

    with open(SYSTEMD_PATH_DISCONNECTED_PATH, "w") as f:
        f.write(SYSTEMD_PATH_DISCONNECTED_CONTENT)
    print(f"Disconnected path unit written to {SYSTEMD_PATH_DISCONNECTED_PATH}")

    # Reload systemd daemon and enable/start units.
    subprocess.run(["systemctl", "daemon-reload"], check=True)
    subprocess.run(["systemctl", "enable", SYSTEMD_SERVICE_NAME], check=True)
    subprocess.run(["systemctl", "enable", SYSTEMD_PATH_INSERTED_PATH], check=True)
    subprocess.run(["systemctl", "enable", SYSTEMD_PATH_CONNECTED_PATH], check=True)
    subprocess.run(["systemctl", "enable", SYSTEMD_PATH_DISCONNECTED_PATH], check=True)

    subprocess.run(["systemctl", "start", SYSTEMD_SERVICE_NAME], check=True)
    subprocess.run(["systemctl", "start", SYSTEMD_PATH_INSERTED_UNIT], check=True)
    subprocess.run(["systemctl", "start", SYSTEMD_PATH_CONNECTED_UNIT], check=True)
    subprocess.run(["systemctl", "start", SYSTEMD_PATH_DISCONNECTED_UNIT], check=True)

    print("Systemd units successfully set up, enabled, and started.")


def uninstall_systemd_units():
    """Uninstall systemd service and path units."""
    print("Uninstalling systemd units...")

    # Stop the .path and service units
    subprocess.run(["systemctl", "stop", SYSTEMD_PATH_INSERTED_UNIT], check=True)
    subprocess.run(["systemctl", "stop", SYSTEMD_PATH_CONNECTED_UNIT], check=True)
    subprocess.run(["systemctl", "stop", SYSTEMD_PATH_DISCONNECTED_UNIT], check=True)
    subprocess.run(["systemctl", "stop", SYSTEMD_SERVICE_NAME], check=True)
    subprocess.run(["systemctl", "stop", f"{SYSTEMD_SERVICE_NAME}-inserted.service"], check=True)
    subprocess.run(["systemctl", "stop", f"{SYSTEMD_SERVICE_NAME}-connected.service"], check=True)
    subprocess.run(["systemctl", "stop", f"{SYSTEMD_SERVICE_NAME}-disconnected.service"], check=True)

    # Disable the units
    subprocess.run(["systemctl", "disable", SYSTEMD_PATH_INSERTED_UNIT], check=True)
    subprocess.run(["systemctl", "disable", SYSTEMD_PATH_CONNECTED_UNIT], check=True)
    subprocess.run(["systemctl", "disable", SYSTEMD_PATH_DISCONNECTED_UNIT], check=True)
    subprocess.run(["systemctl", "disable", SYSTEMD_SERVICE_NAME], check=True)

    # Remove the unit files if they exist
    for path in [
        SYSTEMD_SERVICE_PATH,
        SYSTEMD_INSERTED_SERVICE_PATH,
        SYSTEMD_CONNECTED_SERVICE_PATH,
        SYSTEMD_DISCONNECTED_SERVICE_PATH,
        SYSTEMD_PATH_INSERTED_PATH,
        SYSTEMD_PATH_CONNECTED_PATH,
        SYSTEMD_PATH_DISCONNECTED_PATH,
    ]:
        if os.path.exists(path):
            os.remove(path)
            print(f"Removed {path}")

    # Reload systemd daemon
    subprocess.run(["systemctl", "daemon-reload"], check=True)
    print("Systemd units successfully uninstalled.")


def stop_systemd_units():
    """Stop systemd service and path units."""
    print("Stopping systemd units...")

    # Stop the .path and main service units.
    subprocess.run(["systemctl", "stop", SYSTEMD_PATH_INSERTED_UNIT], check=True)
    subprocess.run(["systemctl", "stop", SYSTEMD_PATH_CONNECTED_UNIT], check=True)
    subprocess.run(["systemctl", "stop", SYSTEMD_PATH_DISCONNECTED_UNIT], check=True)
    subprocess.run(["systemctl", "stop", SYSTEMD_SERVICE_NAME], check=True)

    print("Systemd units successfully stopped.")


def setup():
    """Main setup function to deploy or check NetFang system hooks."""
    # Ensure that if we are on Linux, the script is running with elevated privileges.
    if is_linux() and not is_elevated():
        print("NetFang needs root privileges to deploy.")
        sys.exit(1)

    if should_deploy():
        setup_systemd_units()
    else:
        print(
            "\033[91mNetFang does not support this device or operating system.\n"
            "No system hooks were installed.\n"
            "You can still use the test endpoint to simulate the system.\n"
            "Supported device: Raspberry Pi Zero 2 W\033[0m"
        )


def uninstall():
    """Main uninstallation function to remove NetFang system hooks."""
    if is_linux() and not is_elevated():
        print("NetFang needs root privileges to uninstall.")
        sys.exit(1)

    if should_deploy():
        uninstall_systemd_units()
    else:
        print(
            "\033[91mNetFang does not support this device or operating system.\n"
            "No system hooks to clean up.\033[0m"
        )


def stop():
    """Main stop function to stop NetFang system hooks."""
    if is_linux() and not is_elevated():
        print("NetFang needs root privileges to stop the services.")
        sys.exit(1)

    if should_deploy():
        stop_systemd_units()
    else:
        print(
            "\033[91mNetFang does not support this device or operating system.\n"
            "No system hooks to stop.\033[0m"
        )


if __name__ == "__main__":
    if len(sys.argv) > 1:
        if sys.argv[1] == "uninstall":
            uninstall()
        elif sys.argv[1] == "stop":
            stop()
        else:
            setup()
    else:
        setup()

import os
import subprocess
import sys

SYSTEMD_SERVICE_NAME = "netfang-network-monitor"
SYSTEMD_SERVICE_PATH = f"/etc/systemd/system/{SYSTEMD_SERVICE_NAME}.service"
SYSTEMD_PATH_INSERTED_PATH = (
    f"/etc/systemd/system/{SYSTEMD_SERVICE_NAME}-inserted.path"
)
SYSTEMD_PATH_CONNECTED_PATH = (
    f"/etc/systemd/system/{SYSTEMD_SERVICE_NAME}-connected.path"
)
SYSTEMD_PATH_DISCONNECTED_PATH = (
    f"/etc/systemd/system/{SYSTEMD_SERVICE_NAME}-disconnected.path"
)
SYSTEMD_PATH_INSERTED_UNIT = f"{SYSTEMD_SERVICE_NAME}-inserted.path"
SYSTEMD_PATH_CONNECTED_UNIT = f"{SYSTEMD_SERVICE_NAME}-connected.path"
SYSTEMD_PATH_DISCONNECTED_UNIT = f"{SYSTEMD_SERVICE_NAME}-disconnected.path"
UDEV_RECEIVER_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "../api/udev_receiver.py")
)

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

SYSTEMD_PATH_INSERTED_CONTENT = f"""\
[Unit]
Description=Path Unit for Network Cable Insertion
Requires={SYSTEMD_SERVICE_NAME}.service
After=network.target

[Path]
PathExists=/sys/class/net/%I/carrier
# Unit and Listen lines added to resolve mount unit issues
Unit={SYSTEMD_SERVICE_NAME}-inserted.service
Listen=/sys/class/net/%I/carrier
ExecStart=/usr/bin/python3 {UDEV_RECEIVER_PATH} cable_inserted %I

[Install]
WantedBy=multi-user.target
"""

SYSTEMD_PATH_CONNECTED_CONTENT = f"""\
[Unit]
Description=Path Unit for Network Connection Establishment
Requires={SYSTEMD_SERVICE_NAME}.service
After=network.target

[Path]
PathChanged=/sys/class/net/%I/operstate
# Unit and Listen lines added to resolve mount unit issues
Unit={SYSTEMD_SERVICE_NAME}-connected.service
Listen=/sys/class/net/%I/operstate
ExecStart=/usr/bin/python3 {UDEV_RECEIVER_PATH} connected %I

[Install]
WantedBy=multi-user.target
"""

SYSTEMD_PATH_DISCONNECTED_CONTENT = f"""\
[Unit]
Description=Path Unit for Network Disconnection
Requires={SYSTEMD_SERVICE_NAME}.service
After=network.target

[Path]
PathChanged=/sys/class/net/%I/operstate
# Unit and Listen lines added to resolve mount unit issues
Unit={SYSTEMD_SERVICE_NAME}-disconnected.service
Listen=/sys/class/net/%I/operstate
ExecStart=/usr/bin/python3 {UDEV_RECEIVER_PATH} disconnected %I

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

    # Write the systemd service file
    with open(SYSTEMD_SERVICE_PATH, "w") as f:
        f.write(SYSTEMD_SERVICE_CONTENT)
    print(f"Systemd service written to {SYSTEMD_SERVICE_PATH}")

    # Write the systemd path units
    with open(SYSTEMD_PATH_INSERTED_PATH, "w") as f:
        f.write(SYSTEMD_PATH_INSERTED_CONTENT)
    print(f"Systemd path unit written to {SYSTEMD_PATH_INSERTED_PATH}")

    with open(SYSTEMD_PATH_CONNECTED_PATH, "w") as f:
        f.write(SYSTEMD_PATH_CONNECTED_CONTENT)
    print(f"Systemd path unit written to {SYSTEMD_PATH_CONNECTED_PATH}")

    with open(SYSTEMD_PATH_DISCONNECTED_PATH, "w") as f:
        f.write(SYSTEMD_PATH_DISCONNECTED_CONTENT)
    print(f"Systemd path unit written to {SYSTEMD_PATH_DISCONNECTED_PATH}")

    # Enable and start the systemd units
    subprocess.run(["systemctl", "daemon-reload"], check=True)
    subprocess.run(["systemctl", "enable", SYSTEMD_SERVICE_NAME], check=True)
    subprocess.run(
        ["systemctl", "enable", SYSTEMD_PATH_INSERTED_PATH], check=True
    )
    subprocess.run(
        ["systemctl", "enable", SYSTEMD_PATH_CONNECTED_PATH], check=True
    )
    subprocess.run(["systemctl", "start", SYSTEMD_SERVICE_NAME], check=True)
    subprocess.run(
        ["systemctl", "start", SYSTEMD_PATH_INSERTED_UNIT], check=True
    )
    subprocess.run(
        ["systemctl", "start", SYSTEMD_PATH_CONNECTED_UNIT], check=True
    )
    subprocess.run(
        ["systemctl", "start", SYSTEMD_PATH_DISCONNECTED_UNIT], check=True
    )

    print("Systemd units successfully set up, enabled, and started.")


def uninstall_systemd_units():
    """Uninstall systemd service and path units."""
    print("Uninstalling systemd units...")

    # Stop and disable the systemd units
    subprocess.run(["systemctl", "stop", SYSTEMD_PATH_INSERTED_UNIT], check=True)
    subprocess.run(["systemctl", "stop", SYSTEMD_PATH_CONNECTED_UNIT], check=True)
    subprocess.run(
        ["systemctl", "stop", SYSTEMD_PATH_DISCONNECTED_UNIT], check=True
    )
    subprocess.run(["systemctl", "stop", SYSTEMD_SERVICE_NAME], check=True)

    subprocess.run(
        ["systemctl", "disable", SYSTEMD_PATH_INSERTED_UNIT], check=True
    )
    subprocess.run(
        ["systemctl", "disable", SYSTEMD_PATH_CONNECTED_UNIT], check=True
    )
    subprocess.run(
        ["systemctl", "disable", SYSTEMD_PATH_DISCONNECTED_UNIT], check=True
    )
    subprocess.run(["systemctl", "disable", SYSTEMD_SERVICE_NAME], check=True)

    # Remove the systemd unit files
    if os.path.exists(SYSTEMD_SERVICE_PATH):
        os.remove(SYSTEMD_SERVICE_PATH)
        print(f"Removed {SYSTEMD_SERVICE_PATH}")

    if os.path.exists(SYSTEMD_PATH_INSERTED_PATH):
        os.remove(SYSTEMD_PATH_INSERTED_PATH)
        print(f"Removed {SYSTEMD_PATH_INSERTED_PATH}")

    if os.path.exists(SYSTEMD_PATH_CONNECTED_PATH):
        os.remove(SYSTEMD_PATH_CONNECTED_PATH)
        print(f"Removed {SYSTEMD_PATH_CONNECTED_PATH}")

    if os.path.exists(SYSTEMD_PATH_DISCONNECTED_PATH):
        os.remove(SYSTEMD_PATH_DISCONNECTED_PATH)
        print(f"Removed {SYSTEMD_PATH_DISCONNECTED_PATH}")

    # Reload systemd daemon
    subprocess.run(["systemctl", "daemon-reload"], check=True)

    print("Systemd units successfully uninstalled.")


def stop_systemd_units():
    """Stop systemd service and path units."""
    print("Stopping systemd units...")

    # Stop the systemd units
    subprocess.run(["systemctl", "stop", SYSTEMD_PATH_INSERTED_UNIT], check=True)
    subprocess.run(["systemctl", "stop", SYSTEMD_PATH_CONNECTED_UNIT], check=True)
    subprocess.run(
        ["systemctl", "stop", SYSTEMD_PATH_DISCONNECTED_UNIT], check=True
    )
    subprocess.run(["systemctl", "stop", SYSTEMD_SERVICE_NAME], check=True)

    print("Systemd units successfully stopped.")


def setup():
    """Main setup function to deploy or check NetFang system hooks."""
    # Ensure that if we are on Linux, the script is running with elevated
    # privileges.
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
    # Ensure that if we are on Linux, the script is running with elevated
    # privileges.
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
    # Ensure that if we are on Linux, the script is running with elevated
    # privileges.
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

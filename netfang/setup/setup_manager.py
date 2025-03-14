import os
import subprocess
import sys

UDEV_RULES_PATH = "/etc/udev/rules.d/99-netfang-network.rules"
UDEV_RECEIVER_PATH = os.path.join(os.path.dirname(__file__), "udev_receiver.py")

UDEV_RULES_CONTENT = f"""\
# Rule for detecting network cable insertion
ACTION=="add", SUBSYSTEM=="net", KERNEL=="eth0", RUN+="python {UDEV_RECEIVER_PATH} cable_inserted eth0%k" 
ACTION=="add", SUBSYSTEM=="net", KERNEL=="eth1", RUN+="python {UDEV_RECEIVER_PATH} cable_inserted eth1%k"
ACTION=="add", SUBSYSTEM=="net", KERNEL=="eth2", RUN+="python {UDEV_RECEIVER_PATH} cable_inserted eth2%k"
ACTION=="add", SUBSYSTEM=="net", KERNEL=="eth3", RUN+="python {UDEV_RECEIVER_PATH} cable_inserted eth3%k"
ACTION=="add", SUBSYSTEM=="net", KERNEL=="eth4", RUN+="python {UDEV_RECEIVER_PATH} cable_inserted eth4%k"

# Rule for detecting network connection establishment
ACTION=="change", SUBSYSTEM=="net", KERNEL=="eth0", ATTR{{operstate}}=="up", RUN+="python {UDEV_RECEIVER_PATH} connected eth0%k"
ACTION=="change", SUBSYSTEM=="net", KERNEL=="eth1", ATTR{{operstate}}=="up", RUN+="python {UDEV_RECEIVER_PATH} connected eth1%k"
ACTION=="change", SUBSYSTEM=="net", KERNEL=="eth2", ATTR{{operstate}}=="up", RUN+="python {UDEV_RECEIVER_PATH} connected eth2%k"
ACTION=="change", SUBSYSTEM=="net", KERNEL=="eth3", ATTR{{operstate}}=="up", RUN+="python {UDEV_RECEIVER_PATH} connected eth3%k"
ACTION=="change", SUBSYSTEM=="net", KERNEL=="eth4", ATTR{{operstate}}=="up", RUN+="python {UDEV_RECEIVER_PATH} connected eth4%k"

# Rule for detecting network disconnection
ACTION=="change", SUBSYSTEM=="net", KERNEL=="eth0", ATTR{{operstate}}=="down", RUN+="python {UDEV_RECEIVER_PATH} disconnected eth0%k"
ACTION=="change", SUBSYSTEM=="net", KERNEL=="eth1", ATTR{{operstate}}=="down", RUN+="python {UDEV_RECEIVER_PATH} disconnected eth1%k"
ACTION=="change", SUBSYSTEM=="net", KERNEL=="eth2", ATTR{{operstate}}=="down", RUN+="python {UDEV_RECEIVER_PATH} disconnected eth2%k"
ACTION=="change", SUBSYSTEM=="net", KERNEL=="eth3", ATTR{{operstate}}=="down", RUN+="python {UDEV_RECEIVER_PATH} disconnected eth3%k"
ACTION=="change", SUBSYSTEM=="net", KERNEL=="eth4", ATTR{{operstate}}=="down", RUN+="python {UDEV_RECEIVER_PATH} disconnected eth4%k"
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


def setup_udev_rules():
    """Setup udev rules for network events on Raspberry Pi Zero 2 W."""
    print("Setting up udev rules for Raspberry Pi Zero 2 W...")

    # Write the udev rules file
    with open(UDEV_RULES_PATH, "w") as f:
        f.write(UDEV_RULES_CONTENT)
    print(f"Udev rules written to {UDEV_RULES_PATH}")

    # Reload udev rules
    subprocess.run(["udevadm", "control", "--reload-rules"], check=True)
    subprocess.run(["udevadm", "trigger"], check=True)

    print("Udev rules successfully set up and reloaded.")


def uninstall_udev_rules():
    """Uninstall udev rules and remove the handler script."""
    print("Uninstalling udev rules for Raspberry Pi Zero 2 W...")

    # Remove udev rules file
    if os.path.exists(UDEV_RULES_PATH):
        os.remove(UDEV_RULES_PATH)
        print(f"Removed {UDEV_RULES_PATH}")

    # Remove Python handler script
    if os.path.exists(UDEV_RULES_CONTENT):
        os.remove(UDEV_RULES_CONTENT)
        print(f"Removed {UDEV_RULES_CONTENT}")

    # Reload udev rules
    subprocess.run(["udevadm", "control", "--reload-rules"], check=True)
    subprocess.run(["udevadm", "trigger"], check=True)

    print("Udev rules successfully uninstalled.")


def setup():
    """Main setup function to deploy or check NetFang system hooks."""
    # Ensure that if we are on Linux, the script is running with elevated privileges.
    if is_linux() and not is_elevated():
        print("NetFang needs root privileges to deploy.")
        sys.exit(1)

    if should_deploy():
        setup_udev_rules()
    else:
        print(
            "\033[91mNetFang does not support this device or operating system.\n"
            "No system hooks were installed.\n"
            "You can still use the test endpoint to simulate the system.\n"
            "Supported device: Raspberry Pi Zero 2 W\033[0m"
        )


def uninstall():
    """Main uninstall function to remove NetFang system hooks."""
    # Ensure that if we are on Linux, the script is running with elevated privileges.
    if is_linux() and not is_elevated():
        print("NetFang needs root privileges to uninstall.")
        sys.exit(1)

    if should_deploy():
        uninstall_udev_rules()
    else:
        print(
            "\033[91mNetFang does not support this device or operating system.\n"
            "No system hooks to clean up.\033[0m"
        )

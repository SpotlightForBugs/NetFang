import os
import subprocess
import sys


MONITOR_SCRIPT_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), '../api/netfang_monitor.py'))

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


def run_monitor_script():
    print("Running NetFang monitor script...")
    subprocess.Popen(
        ["python3", MONITOR_SCRIPT_PATH],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        preexec_fn=os.setpgrp  # This detaches the child process
    )


def add_usb_modeswitch_rule():
    MODESWITCH_RULE_CONTENT = """
# /etc/usb_modeswitch.d/0bda:8151
# Realtek RTL8151
TargetVendor=0x0bda
TargetProduct=8152
MessageContent="555342430860d9a9c0000000800006e0000000000000000000000000000000"
"""
    MODESWITCH_RULE_PATH = "/etc/usb_modeswitch.d/0bda:8151"
    if not os.path.exists(MODESWITCH_RULE_PATH):
        print("Adding USB mode switch rule for Realtek RTL8151...")
        with open(MODESWITCH_RULE_PATH, "w") as f:
            f.write(MODESWITCH_RULE_CONTENT)
        print(f"USB mode switch rule written to {MODESWITCH_RULE_PATH}")
    else:
        print("USB mode switch rule already exists.")


def remove_usb_modeswitch_rule():
    MODESWITCH_RULE_PATH = "/etc/usb_modeswitch.d/0bda:8151"
    if os.path.exists(MODESWITCH_RULE_PATH):
        print("Removing USB mode switch rule for Realtek RTL8151...")
        os.remove(MODESWITCH_RULE_PATH)
        print(f"Removed {MODESWITCH_RULE_PATH}")
    else:
        print("USB mode switch rule does not exist.")


def add_modeswitch_udev_rule():
    MODESWITCH_UDEV_RULE_CONTENT = """# /etc/udev/rules.d/40-usb_modeswitch.rules
# Custom usb_modeswitch rules
# If matched, usb_modeswitch refers to the external rules in /etc/usb_modeswitch.d/xxxx:yyyy
# Where xxxx and yyyy are vendor ID and device ID.
# Realtek RTL8151
ATTR{idVendor}=="0bda", ATTR{idProduct}=="8151", RUN+="/usr/sbin/usb_modeswitch -c /etc/usb_modeswitch.d/0bda:8151"
"""
    MODESWITCH_UDEV_RULE_PATH = "/etc/udev/rules.d/40-usb_modeswitch.rules"
    if not os.path.exists(MODESWITCH_UDEV_RULE_PATH):
        print("Adding USB mode switch udev rule for Realtek RTL8151...")
        with open(MODESWITCH_UDEV_RULE_PATH, "w") as f:
            f.write(MODESWITCH_UDEV_RULE_CONTENT)
        print(f"USB mode switch udev rule written to {MODESWITCH_UDEV_RULE_PATH}")
    else:
        print("USB mode switch udev rule already exists.")


def remove_modeswitch_udev_rule():
    MODESWITCH_UDEV_RULE_PATH = "/etc/udev/rules.d/40-usb_modeswitch.rules"
    if os.path.exists(MODESWITCH_UDEV_RULE_PATH):
        print("Removing USB mode switch udev rule for Realtek RTL8151...")
        os.remove(MODESWITCH_UDEV_RULE_PATH)
        print(f"Removed {MODESWITCH_UDEV_RULE_PATH}")
    else:
        print("USB mode switch udev rule does not exist.")


def apply_udev_changes():
    print("Applying udev changes...")
    subprocess.run(["udevadm", "control", "--reload-rules"], check=True)
    subprocess.run(["udevadm", "trigger"], check=True)
    print("Udev changes successfully applied.")

def setup():
    """Main setup function to deploy or check NetFang system hooks."""
    if is_linux() and not is_elevated():
        print("NetFang needs root privileges to deploy.")
        sys.exit(1)

    if should_deploy():
        add_usb_modeswitch_rule()
        add_modeswitch_udev_rule()
        apply_udev_changes()
        run_monitor_script()
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
        remove_usb_modeswitch_rule()
        remove_modeswitch_udev_rule()
        apply_udev_changes()
    else:
        print(
            "\033[91mNetFang does not support this device or operating system.\n"
            "No system hooks to clean up.\033[0m"
        )


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "uninstall":
        uninstall()
    else:
        setup()

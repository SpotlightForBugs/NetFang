import sys


def is_pi() -> bool:
    # Check /sys/firmware/devicetree/base/model (modern)
    try:
        with open("/sys/firmware/devicetree/base/model", "r") as f:
            if "raspberry pi" in f.read().lower():
                return True
    except OSError:
        pass

    # Fallback to parsing /proc/cpuinfo (older)
    try:
        with open("/proc/cpuinfo", "r") as f:
            cpuinfo = f.read().lower()
            # Checking for 'raspberry pi' or 'bcm' references that are typical
            if "raspberry pi" in cpuinfo or "bcm" in cpuinfo:
                return True
    except OSError:
        pass

    return False


def get_pi_serial() -> str:
    serial = "Unknown"
    try:
        with open('/proc/cpuinfo', 'r') as f:
            for line in f:
                if line.startswith('Serial'):
                    # Split on ':' and take the second half, stripping whitespace
                    serial = line.split(':')[1].strip()
                    break
    except OSError:
        pass
    return serial


def linux_machine_id() -> str:
    try:
        with open('/etc/machine-id', 'r') as f:
            return f.read().strip()
    except OSError:
        return "Unknown"


def is_linux() -> bool:
    return sys.platform.startswith("linux")

def is_pi_zero_2():
    try:
        with open("/sys/firmware/devicetree/base/model", "r") as f:
            return "raspberry pi zero 2" in f.read().lower()
    except OSError:
        return False

if __name__ == "__main__":
    is_pi = is_pi()
    print(f"Is Raspberry Pi: {is_pi}")
    if is_pi:
        print("Pi Serial:", get_pi_serial())
    if is_linux():
        print("Machine ID:", linux_machine_id())

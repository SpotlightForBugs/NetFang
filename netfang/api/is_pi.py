def check() -> bool:
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


if __name__ == "__main__":
    print(check())

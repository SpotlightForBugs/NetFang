Below is a revised version of the README that cleans up the instructions, removes the development tags, and adds details on assembling the PoE/USB Hub HAT or UPS HAT for the Raspberry Pi Zero 2 W.

---

# NetFang

**WORK IN PROGRESS, NOT READY FOR USE**

[![wakatime](https://wakatime.com/badge/github/SpotlightForBugs/NetFang.svg?q=cachebusting_is_great)](https://wakatime.com/badge/github/SpotlightForBugs/NetFang)

## Description

NetFang is a Hak5-inspired SharkJack clone built on the Raspberry Pi. 
The RaspberryPi Zero 2 W is the only supported hardware at the moment, but this project is built to be modular and support other hardware in the future.


---

## Supported Hardware

The following hardware is supported (✓ = Done, ✖ = In progress):

- **Raspberry Pi Zero 2 W** ✓

**Ethernet:**

- Your standard USB to Ethernet adapter ✓
- Eth/USB Hub HAT (B) from Waveshare ✓
- PoE/USB Hub HAT from Waveshare – Plug and Play, no setup required ✓

**Power:**

- Waveshare UPS HAT (C) (if not using PoE) ✓  
- Any external Battery Bank ✓

**LED Hat (for debugging purposes):**

- Waveshare RGB LED HAT ✖  

**Storage:**

- MicroSD Card ✓
- USB Flash Drive ✖ 

---
```plaintext
┌─────────────────────────────────────────────────────────────────────┐
│                      HARDWARE DECISION TREE                         │
└─────────────────────────────────────────────────────────────────────┘

Start → Do you need battery backup?
├── Yes → Use Waveshare UPS HAT (C)
│   │
│   └── For Ethernet, you must use either:
│       │
│       ├── Configuration A:
│       │   ┌─────────────────────┐
│       │   │  Eth/USB Hub HAT (B)│ ← Top (requires headers)
│       │   ├─────────────────────┤
│       │   │  Raspberry Pi Zero 2│ ← Middle
│       │   ├─────────────────────┤
│       │   │  Waveshare UPS HAT  │ ← Bottom (connects to pads under Pi)
│       │   └─────────────────────┘
│       │   Optional: RGB LED HAT can be added on top of Eth/USB Hub HAT (B)
│       │
│       └── Configuration B:
│           ┌─────────────────────┐
│           │  USB Ethernet Adapter│ ← Connected via USB
│           ├─────────────────────┤
│           │  Raspberry Pi Zero 2│ ← Middle
│           ├─────────────────────┤
│           │  Waveshare UPS HAT  │ ← Bottom (connects to pads under Pi)
│           └─────────────────────┘
│
└── No → Do you want to use PoE?
    │
    ├── Yes → Configuration C:
    │       ┌─────────────────────┐
    │       │  Raspberry Pi Zero 2│ ← Top
    │       ├─────────────────────┤
    │       │  PoE/USB Hub HAT    │ ← Bottom (provides Ethernet & power)
    │       └─────────────────────┘
    │       Note: Not compatible with UPS HAT as PoE HAT blocks access to required pads
    │       Note: Does not require headers
    │
    └── No → Choose either:
        │
        ├── Configuration D:
        │   ┌─────────────────────┐
        │   │  Eth/USB Hub HAT (B)│ ← Top (requires headers)
        │   ├─────────────────────┤
        │   │  Raspberry Pi Zero 2│ ← Bottom
        │   └─────────────────────┘
        │   Note: Powered via standard USB power
        │   Optional: RGB LED HAT can be added on top of Eth/USB Hub HAT (B)
        │
        └── Configuration E:
            ┌─────────────────────┐
            │  USB Ethernet Adapter│ ← Connected via USB
            ├─────────────────────┤
            │  Raspberry Pi Zero 2│ ← Single board
            └─────────────────────┘
            Note: Powered via standard USB power
            Optional: RGB LED HAT can be added on top of Pi (requires headers)
```
---

## Setup Guide

Follow these steps to set up your NetFang device using Kali Linux.

### 1. Prepare Your MicroSD Card with Kali Linux

1. Download and install the official [Raspberry Pi Imager](https://www.raspberrypi.com/software/) for your operating system.
2. Open Raspberry Pi Imager and select **Kali Linux** as the OS.
3. Insert your MicroSD card into your computer.
4. Select the correct storage device (your MicroSD card) and write the Kali Linux image to it.
5. Use the advanced settings (accessible via the settings icon) to:
   - Set the hostname (e.g., `NetFang`)
   - Set a secure password
   - Enable SSH in the services tab

### 2. Assemble & Set Up Your Raspberry Pi

1. **Insert the MicroSD Card:**
   - Safely eject the MicroSD card from your computer and insert it into your Raspberry Pi.
2. **Assemble the Hardware:**
   - **For PoE/USB Hub HAT Users:**  
     Attach the PoE/USB Hub HAT from Waveshare directly to the Raspberry Pi Zero 2 W’s header. This HAT provides both Ethernet connectivity and power over Ethernet—no further configuration is needed^*
   - **For UPS HAT (or Battery Bank) Users:**  
     If you are not using PoE, attach the Waveshare UPS HAT (C) according to the manufacturer’s instructions. Make sure that any external battery bank is securely connected.
3. **Power Up Your Raspberry Pi:**
   - Connect your Raspberry Pi to a power source. If you are using a UPS or Battery Bank, ensure that all connections are secure.
   - If using the PoE HAT, simply connect the Ethernet cable from a PoE-capable switch or injector, and your Raspberry Pi will be powered.

### 3. Install Required Software

1. Open the terminal on your Raspberry Pi.
2. Update your package list:
   ```bash
   sudo apt update
   ```
3. Install Git (if not already installed):
   ```bash
   sudo apt install git
   ```

### 4. Clone the NetFang Repository

1. Navigate to the directory where you want to clone the repository (e.g., your home directory):
   ```bash
   cd ~
   ```
2. Clone the repository:
   ```bash
   git clone https://github.com/SpotlightForBugs/NetFang.git
   ```
3. Change into the NetFang directory:
   ```bash
   cd NetFang
   ```

### 5. Install NetFang

1. Run the installation script with sudo privileges:
   ```bash
   sudo bash install.sh
   ```
   > **Note:** Always review scripts before running them with elevated privileges.

### 6. Verify the NetFang Service

Monitor the NetFang service logs with:
```bash
sudo journalctl -u netfang.service -f
```
- The `-u netfang.service` flag filters the logs for the NetFang service.
- The `-f` flag follows the log file for live updates.

### 7. Uninstalling NetFang (Optional)

If you need to uninstall NetFang, run:
```bash
sudo bash install.sh --uninstall
```
If you also wish to remove the cloned repository, execute:
```bash
rm -rf ~/NetFang
```
> **Warning:** The `rm -rf` command permanently deletes files and directories. Make sure you really want to remove the repository before running this command.

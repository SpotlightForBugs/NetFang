# netfang/database.py

import sqlite3
from typing import Any, Dict, Optional

def init_db(db_path: str) -> None:
    """
    Create initial schema if not present.
    Tables:
      - networks: known networks with MAC, blacklist and home flags.
      - devices: scanned hosts and their services.
      - plugin_logs: record plugin events.
      - alerts: record alerts
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS networks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mac_address TEXT UNIQUE,
            is_blacklisted BOOLEAN,
            is_home BOOLEAN,
            first_seen DATETIME DEFAULT CURRENT_TIMESTAMP,
            last_seen DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS devices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ip_address TEXT,
            mac_address TEXT,
            hostname TEXT,
            services TEXT,
            vendor TEXT,
            deviceclass TEXT,
            network_id INTEGER,
            FOREIGN KEY(network_id) REFERENCES networks(id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS plugin_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            plugin_name TEXT,
            event TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            message TEXT,
            is_resolved BOOLEAN,
            resolved_at DATETIME,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()
    conn.close()


def add_or_update_network(db_path: str, mac_address: str,
                          is_blacklisted: bool = False, is_home: bool = False) -> None:
    """
    Insert a new network or update an existing one by MAC address.
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("SELECT id FROM networks WHERE mac_address = ?", (mac_address,))
    row = cursor.fetchone()

    if row is None:
        cursor.execute("""
            INSERT INTO networks (mac_address, is_blacklisted, is_home)
            VALUES (?, ?, ?)
        """, (mac_address, is_blacklisted, is_home))
    else:
        cursor.execute("""
            UPDATE networks
            SET is_blacklisted = ?,
                is_home = ?,
                last_seen = CURRENT_TIMESTAMP
            WHERE mac_address = ?
        """, (is_blacklisted, is_home, mac_address))

    conn.commit()
    conn.close()

def get_network_by_mac(db_path: str, mac_address: str) -> Optional[Dict[str, Any]]:
    """
    Retrieve network details by MAC address.
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM networks WHERE mac_address = ?", (mac_address,))
    row = cursor.fetchone()
    conn.close()

    return dict(row) if row else None

def add_plugin_log(db_path: str, plugin_name: str, event: str) -> None:
    """
    Log plugin events for diagnostics.
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO plugin_logs (plugin_name, event)
        VALUES (?, ?)
    """, (plugin_name, event))

    conn.commit()
    conn.close()


def add_alert(db_path: str, message, is_resolved=False, resolved_at=None) -> None:
    """
    This saves the alerts that can be displayed in the UI.
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO alerts (message, is_resolved, resolved_at)
        VALUES (?, ?, ?)
    """, (message, is_resolved, resolved_at))

    conn.commit()
    conn.close()



def add_or_update_device(db_path: str, ip_address: str, mac_address: str,
                         hostname: str | None, services: str | None, network_id: int, vendor: str | None,
                         deviceclass: str | None) -> None:
    """
    Insert a new device or update an existing one by MAC address.
    """

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("SELECT id FROM devices WHERE mac_address = ?", (mac_address,))
    row = cursor.fetchone()

    if row is None:
        cursor.execute("""
            INSERT INTO devices (ip_address, mac_address, hostname, services, network_id, vendor, deviceclass)
            VALUES (?, ?, ?, ?, ?)
        """, (ip_address, mac_address, hostname, services, network_id, vendor, deviceclass))
    else:
        cursor.execute("""
            UPDATE devices
            SET ip_address = ?,
                hostname = ?,
                services = ?,
                network_id = ?,
                vendor = ?,
                deviceclass = ?
            WHERE mac_address = ?
        """, (ip_address, hostname, services, network_id, mac_address, vendor, deviceclass))

    conn.commit()
    conn.close()


def verify_network_id(db_path: str, network_id: int) -> bool:
    """
    Check if a network ID exists in the database.
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("SELECT id FROM networks WHERE id = ?", (network_id,))
    row = cursor.fetchone()

    conn.close()

    return row is not None

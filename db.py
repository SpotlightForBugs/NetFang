# netfang/db.py

import sqlite3
from typing import Any, Dict, List, Optional

def init_db(db_path: str) -> None:
    """
    Create initial schema if not present.
    Tables:
      networks: store known networks (MAC, SSID), whether blacklisted or home
      devices: store scanned hosts on a network
      plugin_logs: record plugin events
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS networks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mac_address TEXT UNIQUE,
            name TEXT,
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

    conn.commit()
    conn.close()

def add_or_update_network(db_path: str, mac_address: str, name: str,
                          is_blacklisted: bool = False, is_home: bool = False) -> None:
    """
    Insert or update a network in the DB by unique mac_address.
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("SELECT id FROM networks WHERE mac_address = ?", (mac_address,))
    row = cursor.fetchone()

    if row is None:
        # Insert new
        cursor.execute("""
            INSERT INTO networks (mac_address, name, is_blacklisted, is_home)
            VALUES (?, ?, ?, ?)
        """, (mac_address, name, is_blacklisted, is_home))
    else:
        # Update existing
        cursor.execute("""
            UPDATE networks
            SET name = ?,
                is_blacklisted = ?,
                is_home = ?,
                last_seen = CURRENT_TIMESTAMP
            WHERE mac_address = ?
        """, (name, is_blacklisted, is_home, mac_address))

    conn.commit()
    conn.close()

def get_network_by_mac(db_path: str, mac_address: str) -> Optional[Dict[str, Any]]:
    """
    Returns a dict with the row data for the given MAC address, or None if not found.
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM networks WHERE mac_address = ?", (mac_address,))
    row = cursor.fetchone()
    conn.close()

    if row:
        return dict(row)
    return None

def add_plugin_log(db_path: str, plugin_name: str, event: str) -> None:
    """
    Inserts a row into plugin_logs for debugging or event tracing.
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO plugin_logs (plugin_name, event) VALUES (?, ?)
    """, (plugin_name, event))

    conn.commit()
    conn.close()

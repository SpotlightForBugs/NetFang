# netfang/db/database.py

import sqlite3
from typing import Any, Dict, Optional, List
import datetime


def init_db(db_path: str) -> None:
    """
    Creates the initial schema if not present, and ensures all necessary columns
    exist in each table.
    Tables:
      - networks: known networks with MAC, blacklist and home flags.
      - devices: scanned hosts and their services.
      - plugin_logs: record plugin events.
      - alerts: record alerts.
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Create networks table if it does not exist.
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS networks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mac_address TEXT UNIQUE,
            is_blacklisted BOOLEAN,
            is_home BOOLEAN,
            first_seen DATETIME DEFAULT CURRENT_TIMESTAMP,
            last_seen DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    # Create devices table if it does not exist.
    cursor.execute(
        """
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
        """
    )

    # Create plugin_logs table if it does not exist.
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS plugin_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            plugin_name TEXT,
            event TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    # Create alerts table if it does not exist.
    # Note: The session_id column is added to support session-based filtering.
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            message TEXT,
            category TEXT,
            level TEXT,
            is_resolved BOOLEAN,
            resolved_at DATETIME,
            network_id INTEGER,
            session_id TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.commit()
    conn.close()

    # Ensure that each table contains all required columns.
    _ensure_table_columns(
        db_path,
        "networks",
        {
            "id": "INTEGER PRIMARY KEY AUTOINCREMENT",
            "mac_address": "TEXT UNIQUE",
            "is_blacklisted": "BOOLEAN",
            "is_home": "BOOLEAN",
            "first_seen": "DATETIME DEFAULT CURRENT_TIMESTAMP",
            "last_seen": "DATETIME DEFAULT CURRENT_TIMESTAMP",
        },
    )
    _ensure_table_columns(
        db_path,
        "devices",
        {
            "id": "INTEGER PRIMARY KEY AUTOINCREMENT",
            "ip_address": "TEXT",
            "mac_address": "TEXT",
            "hostname": "TEXT",
            "services": "TEXT",
            "vendor": "TEXT",
            "deviceclass": "TEXT",
            "network_id": "INTEGER",
        },
    )
    _ensure_table_columns(
        db_path,
        "plugin_logs",
        {
            "id": "INTEGER PRIMARY KEY AUTOINCREMENT",
            "plugin_name": "TEXT",
            "event": "TEXT",
            "timestamp": "DATETIME DEFAULT CURRENT_TIMESTAMP",
        },
    )
    _ensure_table_columns(
        db_path,
        "alerts",
        {
            "id": "INTEGER PRIMARY KEY AUTOINCREMENT",
            "message": "TEXT",
            "category": "TEXT",
            "level": "TEXT",
            "is_resolved": "BOOLEAN",
            "resolved_at": "DATETIME",
            "network_id": "INTEGER",
            "session_id": "TEXT",
            "timestamp": "DATETIME DEFAULT CURRENT_TIMESTAMP",
        },
    )


def _ensure_table_columns(
        db_path: str, table: str, expected_columns: Dict[str, str]
) -> None:
    """
    Ensures that the given table has all the expected columns.
    If a column is missing, it will be added to the table.
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute(f"PRAGMA table_info({table})")
    rows: List[Any] = cursor.fetchall()
    # Extract existing column names.
    existing_columns = {row[1] for row in rows}
    for col, definition in expected_columns.items():
        if col not in existing_columns:
            # Note: SQLite's ALTER TABLE only supports adding a column.
            cursor.execute(f"ALTER TABLE {table} ADD COLUMN {col} {definition}")
    conn.commit()
    conn.close()


def add_or_update_alert(
        db_path: str,
        message: str,
        category: str,
        level: str,
        is_resolved: bool = False,
        resolved_at: Optional[str] = None,
        network_id: Optional[int] = None,
        session_id: Optional[str] = None,
        alert_id: Optional[int] = None,
) -> int:
    """
    Inserts a new alert or updates an existing alert in the database.
    Returns the alert ID.
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    if alert_id is None:
        cursor.execute(
            """
            INSERT INTO alerts (message, category, level, is_resolved, resolved_at, network_id, session_id)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (message, category, level, int(is_resolved), resolved_at, network_id, session_id),
        )
        new_alert_id: int = cursor.lastrowid
        conn.commit()
        conn.close()
        return new_alert_id
    else:
        cursor.execute(
            """
            UPDATE alerts
            SET message = ?,
                category = ?,
                level = ?,
                is_resolved = ?,
                resolved_at = ?,
                network_id = ?,
                session_id = ?
            WHERE id = ?
            """,
            (message, category, level, int(is_resolved), resolved_at, network_id, session_id, alert_id),
        )
        conn.commit()
        conn.close()
        return alert_id


def resolve_alert(db_path: str, alert_id: int) -> None:
    """
    Marks the alert with the given ID as resolved by updating the is_resolved flag
    and setting the resolved_at timestamp.
    """
    resolved_time: str = datetime.datetime.now(datetime.timezone.utc).isoformat()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE alerts
        SET is_resolved = 1,
            resolved_at = ?
        WHERE id = ?
        """,
        (resolved_time, alert_id),
    )
    conn.commit()
    conn.close()


def close_alert(db_path: str, alert_id: int) -> None:
    """
    Deletes the alert with the given ID from the database.
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM alerts WHERE id = ?", (alert_id,))
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


def get_alerts(
        db_path: str,
        limit: Optional[int] = None,
        only_unresolved: bool = False,
        only_resolved: bool = False,
        session_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Retrieves alerts from the database with optional filtering.

    :param db_path: Path to the database.
    :param limit: Maximum number of alerts to retrieve (if None, no limit).
    :param only_unresolved: If True, select only unresolved alerts.
    :param only_resolved: If True, select only resolved alerts.
    :param session_id: If provided, filters alerts for the given session.
    :return: A list of dictionaries representing the alerts.
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    query: str = "SELECT * FROM alerts"
    conditions: List[str] = []
    params: List[Any] = []
    if only_unresolved and not only_resolved:
        conditions.append("is_resolved = 0")
    elif only_resolved and not only_unresolved:
        conditions.append("is_resolved = 1")
    if session_id is not None:
        conditions.append("session_id = ?")
        params.append(session_id)
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    query += " ORDER BY timestamp DESC"
    if limit is not None:
        query += " LIMIT ?"
        params.append(limit)
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

import sqlite3
from typing import Any, Dict, Optional, List, Set, Tuple, cast
import datetime

# Global variable to track if the database has been initialized
db_init: bool = False


def _ensure_db_initialized(db_path: str) -> None:
    """
    Ensures that the database has been initialized.
    If the database is not initialized, it calls init_db.

    :param db_path: Path to the database file.
    """
    global db_init
    if not db_init:
        init_db(db_path)


def init_db(db_path: str) -> None:
    """
    Creates the initial schema if not present, and ensures all necessary columns
    exist in each table.
    Tables:
      - networks: known networks with MAC, blacklist and home flags.
      - devices: scanned hosts and their services.
      - plugin_logs: record plugin events.
      - alerts: record alerts.

    :param db_path: Path to the database file.
    """
    conn: sqlite3.Connection = sqlite3.connect(db_path)
    cursor: sqlite3.Cursor = conn.cursor()

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
            fingerprint TEXT,
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
            "fingerprint": "TEXT",
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

    # Verify all required tables exist with proper structure
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT name, sql FROM sqlite_master WHERE type='table'")
    table_rows: List[Tuple[str, str]] = cursor.fetchall()
    table_definitions: Dict[str, str] = {row[0]: row[1] for row in table_rows}

    required_tables: Dict[str, str] = {
        "networks": "CREATE TABLE networks",
        "devices": "CREATE TABLE devices",
        "plugin_logs": "CREATE TABLE plugin_logs",
        "alerts": "CREATE TABLE alerts"
    }

    # Check that all required tables exist
    for table_name, table_prefix in required_tables.items():
        if table_name not in table_definitions:
            raise RuntimeError(f"Failed to create required table: {table_name}")

        # Basic check that the table definition contains expected prefix
        if not table_definitions[table_name].startswith(table_prefix):
            raise RuntimeError(f"Table {table_name} has unexpected definition")
    conn.close()

    # Set the global flag indicating that the database has been initialized
    global db_init
    db_init = True


def _ensure_table_columns(
        db_path: str, table: str, expected_columns: Dict[str, str]
) -> None:
    """
    Ensures that the given table has all the expected columns.
    If a column is missing, it will be added to the table.

    :param db_path: Path to the database file.
    :param table: Name of the table to check.
    :param expected_columns: Dictionary mapping column names to their definitions.
    """
    conn: sqlite3.Connection = sqlite3.connect(db_path)
    cursor: sqlite3.Cursor = conn.cursor()
    cursor.execute(f"PRAGMA table_info({table})")
    rows: List[Tuple[Any, ...]] = cursor.fetchall()
    # Extract existing column names.
    existing_columns: Set[str] = {cast(str, row[1]) for row in rows}
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

    :param db_path: Path to the database file.
    :param message: Alert message text.
    :param category: Alert category.
    :param level: Alert severity level.
    :param is_resolved: Whether the alert is resolved.
    :param resolved_at: When the alert was resolved.
    :param network_id: Associated network ID if applicable.
    :param session_id: Session identifier for the alert.
    :param alert_id: ID of existing alert to update.
    :return: ID of the created or updated alert.
    """
    _ensure_db_initialized(db_path)

    conn: sqlite3.Connection = sqlite3.connect(db_path)
    cursor: sqlite3.Cursor = conn.cursor()
    if alert_id is None:
        cursor.execute(
            """
            INSERT INTO alerts (message, category, level, is_resolved, resolved_at, network_id, session_id)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (message, category, level, int(is_resolved), resolved_at, network_id, session_id),
        )
        new_alert_id: int = cast(int, cursor.lastrowid)
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

    :param db_path: Path to the database file.
    :param alert_id: ID of the alert to resolve.
    """
    _ensure_db_initialized(db_path)

    resolved_time: str = datetime.datetime.now(datetime.timezone.utc).isoformat()
    conn: sqlite3.Connection = sqlite3.connect(db_path)
    cursor: sqlite3.Cursor = conn.cursor()
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

    :param db_path: Path to the database file.
    :param alert_id: ID of the alert to delete.
    """
    _ensure_db_initialized(db_path)

    conn: sqlite3.Connection = sqlite3.connect(db_path)
    cursor: sqlite3.Cursor = conn.cursor()
    cursor.execute("DELETE FROM alerts WHERE id = ?", (alert_id,))
    conn.commit()
    conn.close()


def verify_network_id(db_path: str, network_id: int) -> bool:
    """
    Check if a network ID exists in the database.

    :param db_path: Path to the database file.
    :param network_id: Network ID to verify.
    :return: True if the network ID exists, False otherwise.
    """
    _ensure_db_initialized(db_path)

    conn: sqlite3.Connection = sqlite3.connect(db_path)
    cursor: sqlite3.Cursor = conn.cursor()
    cursor.execute("SELECT id FROM networks WHERE id = ?", (network_id,))
    row: Optional[Tuple[Any, ...]] = cursor.fetchone()
    conn.close()
    return row is not None


def get_network_by_mac(db_path: str, mac_address: str) -> Optional[Dict[str, Any]]:
    """
    Retrieve network details by MAC address.

    :param db_path: Path to the database file.
    :param mac_address: MAC address to look up.
    :return: Dictionary of network details if found, None otherwise.
    """
    _ensure_db_initialized(db_path)

    conn: sqlite3.Connection = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor: sqlite3.Cursor = conn.cursor()
    cursor.execute("SELECT * FROM networks WHERE mac_address = ?", (mac_address,))
    row: Optional[sqlite3.Row] = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def add_or_update_network(
        db_path: str,
        mac_address: str,
        is_blacklisted: bool = False,
        is_home: bool = False
) -> None:
    """
    Insert a new network or update an existing one by MAC address.

    :param db_path: Path to the database file.
    :param mac_address: MAC address of the network.
    :param is_blacklisted: Whether the network is blacklisted.
    :param is_home: Whether the network is a home network.
    """
    _ensure_db_initialized(db_path)

    conn: sqlite3.Connection = sqlite3.connect(db_path)
    cursor: sqlite3.Cursor = conn.cursor()
    cursor.execute("SELECT id FROM networks WHERE mac_address = ?", (mac_address,))
    row: Optional[Tuple[Any, ...]] = cursor.fetchone()
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
    Log plugin events for diagnostics and also stream to dashboard if SocketIO handler is available.

    :param db_path: Path to the database file.
    :param plugin_name: Name of the plugin logging the event.
    :param event: Description of the event.
    """
    _ensure_db_initialized(db_path)

    # Store in database
    conn: sqlite3.Connection = sqlite3.connect(db_path)
    cursor: sqlite3.Cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO plugin_logs (plugin_name, event)
        VALUES (?, ?)
    """, (plugin_name, event))
    conn.commit()
    conn.close()
    
    # Stream to dashboard in real-time if SocketIO handler is available
    try:
        from netfang.socketio_handler import handler
        import asyncio
        
        # Create and run a coroutine to stream the log
        async def stream_log():
            await handler.stream_plugin_log(plugin_name, event)
            
        # Get the current event loop or create one if it doesn't exist
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.create_task(stream_log())
            else:
                loop.run_until_complete(stream_log())
        except RuntimeError:
            # If no event loop is available in this thread, just log without streaming
            pass
    except ImportError:
        # SocketIO handler not available, just log without streaming
        pass


def get_alerts(
        db_path: str,
        limit: Optional[int] = None,
        only_unresolved: bool = False,
        only_resolved: bool = False,
        session_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Retrieves alerts from the database with optional filtering.

    :param db_path: Path to the database file.
    :param limit: Maximum number of alerts to retrieve (if None, no limit).
    :param only_unresolved: If True, select only unresolved alerts.
    :param only_resolved: If True, select only resolved alerts.
    :param session_id: If provided, filters alerts for the given session.
    :return: A list of dictionaries representing the alerts.
    """
    _ensure_db_initialized(db_path)

    conn: sqlite3.Connection = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor: sqlite3.Cursor = conn.cursor()
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
    rows: List[sqlite3.Row] = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_networks(db_path: str, limit: Optional[int] = None) -> List[Dict[str, Any]]:
    """
    Retrieves all networks from the database.

    :param db_path: Path to the database file.
    :param limit: Maximum number of networks to retrieve (if None, no limit).
    :return: A list of dictionaries representing the networks.
    """
    _ensure_db_initialized(db_path)

    conn: sqlite3.Connection = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor: sqlite3.Cursor = conn.cursor()
    query: str = "SELECT * FROM networks ORDER BY last_seen DESC"
    params: List[Any] = []
    if limit is not None:
        query += " LIMIT ?"
        params.append(limit)
    cursor.execute(query, params)
    rows: List[sqlite3.Row] = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_devices(db_path: str, network_id: Optional[int] = None, limit: Optional[int] = None) -> List[Dict[str, Any]]:
    """
    Retrieves devices from the database, optionally filtered by network ID.

    :param db_path: Path to the database file.
    :param network_id: If provided, only devices from this network are returned.
    :param limit: Maximum number of devices to retrieve (if None, no limit).
    :return: A list of dictionaries representing the devices.
    """
    _ensure_db_initialized(db_path)

    conn: sqlite3.Connection = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor: sqlite3.Cursor = conn.cursor()
    query: str = "SELECT * FROM devices"
    params: List[Any] = []
    if network_id is not None:
        query += " WHERE network_id = ?"
        params.append(network_id)
    query += " ORDER BY id DESC"
    if limit is not None:
        query += " LIMIT ?"
        params.append(limit)
    cursor.execute(query, params)
    rows: List[sqlite3.Row] = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_plugin_logs(db_path: str, plugin_name: Optional[str] = None, limit: Optional[int] = None) -> List[Dict[str, Any]]:
    """
    Retrieves plugin logs from the database, optionally filtered by plugin name.

    :param db_path: Path to the database file.
    :param plugin_name: If provided, only logs from this plugin are returned.
    :param limit: Maximum number of logs to retrieve (if None, no limit).
    :return: A list of dictionaries representing the plugin logs.
    """
    _ensure_db_initialized(db_path)

    conn: sqlite3.Connection = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor: sqlite3.Cursor = conn.cursor()
    query: str = "SELECT * FROM plugin_logs"
    params: List[Any] = []
    if plugin_name is not None:
        query += " WHERE plugin_name = ?"
        params.append(plugin_name)
    query += " ORDER BY timestamp DESC"
    if limit is not None:
        query += " LIMIT ?"
        params.append(limit)
    cursor.execute(query, params)
    rows: List[sqlite3.Row] = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_dashboard_data(db_path: str,alert_limit=50,plugin_log_limit=20) -> Dict[str, Any]:
    """
    Retrieves all relevant data for the dashboard in a single call.
    This reduces the number of database connections needed for syncing.

    :param db_path: Path to the database file.
    :return: A dictionary with all dashboard data.
    """
    return {
        "networks": get_networks(db_path),
        "devices": get_devices(db_path),
        "alerts": get_alerts(db_path, alert_limit),
        "plugin_logs": get_plugin_logs(db_path, plugin_log_limit)
    }


def add_or_update_device(
        db_path: str,
        ip_address: str,
        mac_address: str,
        hostname: Optional[str] = None,
        services: Optional[str] = None,
        network_id: Optional[int] = None,
        vendor: Optional[str] = None,
        deviceclass: Optional[str] = None,
        fingerprint: Optional[str] = None
) -> None:
    """
    Insert a new device or update an existing one by IP address.

    :param db_path: Path to the database file.
    :param ip_address: IP address of the device.
    :param mac_address: MAC address of the device.
    :param hostname: Optional hostname.
    :param services: Optional services information.
    :param network_id: Optional associated network ID.
    :param vendor: Optional vendor information.
    :param deviceclass: Optional device class/type.
    :param fingerprint: Optional ARP fingerprint data.
    """
    _ensure_db_initialized(db_path)

    conn: sqlite3.Connection = sqlite3.connect(db_path)
    cursor: sqlite3.Cursor = conn.cursor()
    cursor.execute("SELECT id FROM devices WHERE ip_address = ? AND mac_address = ?", 
                  (ip_address, mac_address))
    row: Optional[Tuple[Any, ...]] = cursor.fetchone()
    if row is None:
        cursor.execute("""
            INSERT INTO devices (ip_address, mac_address, hostname, services, network_id, vendor, deviceclass, fingerprint)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (ip_address, mac_address, hostname, services, network_id, vendor, deviceclass, fingerprint))
    else:
        cursor.execute("""
            UPDATE devices
            SET hostname = COALESCE(?, hostname),
                services = COALESCE(?, services),
                network_id = COALESCE(?, network_id),
                vendor = COALESCE(?, vendor),
                deviceclass = COALESCE(?, deviceclass),
                fingerprint = COALESCE(?, fingerprint)
            WHERE ip_address = ? AND mac_address = ?
        """, (hostname, services, network_id, vendor, deviceclass, fingerprint, ip_address, mac_address))
    conn.commit()
    conn.close()

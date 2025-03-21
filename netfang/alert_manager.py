import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, Callable, Any, Dict, List

# Import alert DB functions from the database module.
from netfang.db.database import (
    add_or_update_alert,
    resolve_alert as db_resolve_alert,
    close_alert as db_close_alert,
    get_alerts as db_get_alerts,
)


class AlertCategory(Enum):
    GENERAL = "general"
    NETWORK = "network"
    SECURITY = "security"
    BATTERY = "battery"
    POWER = "power"
    INTERFACE = "interface"
    TEMPERATURE = "temperature"


class AlertLevel(Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass
class Alert:
    category: AlertCategory
    level: AlertLevel
    message: str
    is_resolved: bool = False
    resolved_at: Optional[datetime] = None
    autodismisses_after: Optional[float] = None  # Time in seconds
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    id: Optional[int] = None
    network_id: Optional[int] = None  # Optional network ID associated with the alert
    session_id: Optional[str] = None  # Session identifier

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "category": self.category.value,
            "level": self.level.value,
            "message": self.message,
            "is_resolved": self.is_resolved,
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
            "autodismisses_after": self.autodismisses_after,
            "timestamp": self.timestamp.isoformat(),
            "network_id": self.network_id,
            "session_id": self.session_id,
        }

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> "Alert":
        return Alert(
            category=AlertCategory(data["category"]),
            level=AlertLevel(data["level"]),
            message=data["message"],
            is_resolved=bool(data["is_resolved"]),
            resolved_at=datetime.fromisoformat(data["resolved_at"]) if data["resolved_at"] else None,
            autodismisses_after=data.get("autodismisses_after"),
            timestamp=datetime.fromisoformat(data["timestamp"]),
            id=data.get("id"),
            network_id=data.get("network_id"),
            session_id=data.get("session_id"),
        )


class AlertManager:
    """
    The AlertManager creates alerts, stores them in the database,
    triggers plugin notifications, and can push alerts via websockets.

    This class uses a singleton pattern so that it can be accessed via:
      AlertManager.instance.alert_manager.raise_alert_from_data(alert_data, check_duplicate=True)
      and
      AlertManager.instance.get_alerts(...)

    A new session is generated when the server starts.
    """

    # Singleton instance
    instance: Optional["AlertManager"] = None

    def __init__(
            self,
            plugin_manager: Any,
            db_path: str,
            alert_callback: Optional[Callable[[Alert], None]] = None,
    ) -> None:
        """
        :param plugin_manager: An object that handles plugin notification methods.
        :param db_path: Path to the database.
        :param alert_callback: Optional callback for pushing alert updates (e.g., via websockets).
        """
        self.plugin_manager: Any = plugin_manager
        self.db_path: str = db_path
        self.alert_callback: Optional[Callable[[Alert], None]] = alert_callback

        # Generate a new session ID when the server starts.
        self.session: str = str(uuid.uuid4())

        # Set the singleton instance and alias.
        AlertManager.instance = self
        self.alert_manager = self  # Allows: AlertManager.instance.alert_manager

    def raise_alert(
            self,
            category: AlertCategory,
            level: AlertLevel,
            message: str,
            autodismisses_after: Optional[float] = None,
            network_id: Optional[int] = None,
            session_id: Optional[str] = None,
            check_duplicate: bool = False,
    ) -> Alert:
        """
        Create a new alert, store it in the database, and notify plugins/websocket clients.
        If autodismisses_after is provided, the alert will automatically be resolved
        after the specified time.

        :param category: Alert category.
        :param level: Alert severity level.
        :param message: Alert message.
        :param autodismisses_after: Time in seconds after which the alert is auto-dismissed.
        :param network_id: Optional network ID related to this alert.
        :param session_id: Optional session identifier. Defaults to the current session if not provided.
        :param check_duplicate: Whether to check for duplicate unresolved alerts.
        :return: The created Alert object.
        """
        if session_id is None:
            session_id = self.session

        # Check for duplicates if requested
        if check_duplicate:
            duplicate = self.find_unresolved_alert(category, message)
            if duplicate is not None:
                return duplicate

        alert: Alert = Alert(
            category=category,
            level=level,
            message=message,
            autodismisses_after=autodismisses_after,
            network_id=network_id,
            session_id=session_id,
        )

        # Save the alert in the database and assign its unique ID.
        alert.id = add_or_update_alert(
            self.db_path,
            alert.message,
            alert.category.value,
            alert.level.value,
            is_resolved=alert.is_resolved,
            resolved_at=(alert.resolved_at.isoformat() if alert.resolved_at else None),
            network_id=alert.network_id,
            session_id=alert.session_id,
        )

        # Notify plugins if they implement the on_alerting method.
        if hasattr(self.plugin_manager, "on_alerting"):
            self.plugin_manager.on_alerting(alert)

        # Execute the alert callback (e.g., sending via WebSocket) if provided.
        if self.alert_callback is not None:
            self.alert_callback(alert)

        # Setup auto-dismissal timer if specified.
        if autodismisses_after is not None:
            timer: threading.Timer = threading.Timer(
                autodismisses_after, self.resolve_alert, args=(alert,)
            )
            timer.start()

        return alert

    def resolve_alert(self, alert: Alert) -> None:
        """
        Mark an alert as resolved, update it in the database,
        and notify plugins and callback clients.
        """
        if alert.id is None:
            raise ValueError("Alert has not been saved to the database.")

        alert.is_resolved = True
        alert.resolved_at = datetime.now(timezone.utc)

        db_resolve_alert(self.db_path, alert.id)

        if hasattr(self.plugin_manager, "on_alert_resolved"):
            self.plugin_manager.on_alert_resolved(alert)

        if self.alert_callback is not None:
            self.alert_callback(alert)

    def close_alert(self, alert: Alert) -> None:
        """
        Close the alert by removing it from the database and notifying listeners.
        """
        if alert.id is None:
            raise ValueError("Alert has not been saved to the database.")

        db_close_alert(self.db_path, alert.id)

        if hasattr(self.plugin_manager, "on_alert_closed"):
            self.plugin_manager.on_alert_closed(alert)

        if self.alert_callback is not None:
            self.alert_callback(alert)

    def raise_alert_from_data(self, alert_data: Dict[str, Any], check_duplicate: bool = False) -> Alert:
        """
        Create a new alert from a JSON-like dictionary input.
        Expected keys:
          - "type": Alert category as a string (e.g., "general", "network", "security",
                    "battery", "interface", "temperature").
          - "message": Alert message.
          - "level": (optional) Alert severity level; defaults to "info" if omitted.
          - "autodismisses_after": (optional) Time in seconds for auto-dismissal.
          - "network_id": (optional) The network ID associated with the alert.
          - "session_id": (optional) The session identifier associated with the alert.
        If check_duplicate is True, then an unresolved alert with the same category and message
        (within the current session) is returned instead of creating a new alert.

        :param alert_data: Dictionary containing alert information.
        :param check_duplicate: Whether to check for duplicate unresolved alerts.
        :return: The created or existing Alert object.
        """
        category_str: str = alert_data.get("type", "general").lower()
        try:
            category: AlertCategory = AlertCategory(category_str)
        except ValueError:
            raise ValueError(
                f"Invalid alert type: {category_str}. "
                f"Expected one of {[e.value for e in AlertCategory]}"
            )

        level_str: str = alert_data.get("level", "info").lower()
        try:
            level: AlertLevel = AlertLevel(level_str)
        except ValueError:
            raise ValueError(
                f"Invalid alert level: {level_str}. "
                f"Expected one of {[e.value for e in AlertLevel]}"
            )

        message: Optional[str] = alert_data.get("message")
        if not message:
            raise ValueError("Alert message must be provided in alert_data under the key 'message'.")

        autodismisses_after: Optional[float] = alert_data.get("autodismisses_after")
        network_id: Optional[int] = alert_data.get("network_id")
        session_id: Optional[str] = alert_data.get("session_id", self.session)

        return self.raise_alert(
            category,
            level,
            message,
            autodismisses_after,
            network_id,
            session_id,
            check_duplicate=check_duplicate
        )

    def find_unresolved_alert(self, category: AlertCategory, message: str) -> Optional[Alert]:
        """
        Searches for the latest unresolved alert with the specified category and message in the current session.
        :param category: Category of the alert.
        :param message: Alert message.
        :return: Alert object if found, otherwise None.
        """
        alerts_data: List[Dict[str, Any]] = self.get_alerts(
            limit=None, only_unresolved=True, limit_to_this_session=True
        )
        latest_alert: Optional[Alert] = None
        for alert_dict in alerts_data:
            if alert_dict.get("category") == category.value and alert_dict.get("message") == message:
                latest_alert = Alert.from_dict(alert_dict)
        return latest_alert

    def get_alerts(
            self,
            limit: Optional[int] = None,
            only_unresolved: bool = False,
            only_resolved: bool = False,
            limit_to_this_session: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        Retrieves alerts from the database with optional filtering.
        If limit_to_this_session is True, only alerts from the current session are returned.

        :param limit: Maximum number of alerts to retrieve.
        :param only_unresolved: Only return unresolved alerts.
        :param only_resolved: Only return resolved alerts.
        :param limit_to_this_session: Only return alerts from the current session.
        :return: A list of dictionaries representing the alerts.
        """
        session_id: Optional[str] = self.session if limit_to_this_session else None
        return db_get_alerts(self.db_path, limit, only_unresolved, only_resolved, session_id)

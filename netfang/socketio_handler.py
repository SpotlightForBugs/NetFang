import logging
from typing import Dict, Any, Optional, Callable
import json

# This class will serve as a bridge between the state machine and Flask-SocketIO
# The actual Flask-SocketIO instance will be passed in from main.py
class SocketIOHandler:
    """
    Handles Socket.IO communication throughout the application.
    This class serves as a bridge between components and the Flask-SocketIO instance.
    """
    
    def __init__(self):
        """Initialize the Socket.IO handler"""
        self.socketio = None
        self.logger = logging.getLogger(__name__)
        self.logger.info("SocketIO Handler initialized")
        self.db_path = None  # Will be set from main.py
        
    def set_socketio(self, socketio_instance):
        """Set the Flask-SocketIO instance"""
        self.socketio = socketio_instance
        self.logger.info("SocketIO instance set in handler")
        
    def set_db_path(self, db_path: str):
        """Set the database path for dashboard queries"""
        self.db_path = db_path
        self.logger.info(f"Database path set to: {db_path}")
        
    async def broadcast_state_change(self, state, context: Dict[str, Any]) -> None:
        """
        Broadcast a state change to all connected clients.
        
        Args:
            state: The new state
            context: Additional context information for the state change
        """
        if not self.socketio:
            self.logger.warning("Cannot broadcast state change: SocketIO instance not set")
            return
            
        # Check if state is None and log a warning
        if state is None:
            self.logger.warning("Cannot broadcast state change: Received None state")
            return
            
        # Convert context to a JSON-serializable format if needed
        safe_context = {}
        for key, value in context.items():
            if isinstance(value, dict):
                # For nested dictionaries, we need to make them serializable too
                safe_context[key] = {}
                for k, v in value.items():
                    if isinstance(v, (str, int, float, bool, list, dict)) or v is None:
                        safe_context[key][k] = v
                    else:
                        safe_context[key][k] = str(v)
            elif isinstance(value, (str, int, float, bool, list)) or value is None:
                safe_context[key] = value
            else:
                safe_context[key] = str(value)

        # Emit the state update
        try:
            self.socketio.emit(
                "state_update",
                {"state": state.value, "context": safe_context},
            )
            self.logger.debug(f"Broadcasted state change: {state.value}")
        except Exception as e:
            self.logger.error(f"Error broadcasting state change: {str(e)}")
            
    async def broadcast_dashboard_update(self) -> None:
        """
        Broadcast dashboard updates to all connected clients.
        This is called periodically to keep the dashboard up to date.
        """
        if not self.socketio:
            self.logger.warning("Cannot broadcast dashboard update: SocketIO instance not set")
            return
            
        if not self.db_path:
            self.logger.warning("Cannot broadcast dashboard update: DB path not set")
            return
            
        # Import here to avoid circular imports
        from netfang.db.database import get_dashboard_data
        
        try:
            # Get dashboard data from database using the configured db_path
            dashboard_data = get_dashboard_data(self.db_path)
            
            # Emit the dashboard update
            self.socketio.emit("dashboard_data", dashboard_data)
            self.logger.debug("Broadcasted dashboard update")
        except Exception as e:
            self.logger.error(f"Error broadcasting dashboard update: {str(e)}")
            
    async def emit_alert(self, alert_data: Dict[str, Any]) -> None:
        """
        Emit an alert to all connected clients.
        
        Args:
            alert_data: Alert information
        """
        if not self.socketio:
            self.logger.warning("Cannot emit alert: SocketIO instance not set")
            return
            
        try:
            self.socketio.emit("alert_sync", alert_data)
            self.logger.debug(f"Emitted alert: {alert_data.get('message', 'No message')}")
        except Exception as e:
            self.logger.error(f"Error emitting alert: {str(e)}")

# Create a singleton instance to be used throughout the application
handler = SocketIOHandler()
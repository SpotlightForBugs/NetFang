import json
import asyncio
from typing import Set, Dict, Any
import logging

from flask import session
from flask_sock import Sock

from netfang.network_states import State

logger = logging.getLogger(__name__)

# Keep track of active WebSocket connections
active_connections: Set = set()
# Store last known state to send to new connections
last_known_state: Dict[str, Any] = {"type": "state_update", "state": State.WAITING_FOR_NETWORK.value}

def setup_websocket(app):
    """
    Initialize WebSocket handling for the Flask app
    """
    sock = Sock(app)
    
    @sock.route('/ws')
    def ws(ws):
        # Check if user is authenticated
        if not session.get('logged_in'):
            ws.send(json.dumps({"type": "error", "message": "Unauthorized"}))
            return
        
        # Add this connection to active connections
        active_connections.add(ws)
        
        try:
            # Send the last known state immediately
            try:
                ws.send(json.dumps(last_known_state))
            except Exception as e:
                logger.error("Error sending initial WebSocket state: %s", str(e))
            # Process incoming messages
            while True:
                data = ws.receive()
                try:
                    message = json.loads(data)
                    if message.get('action') == 'get_state':
                        from netfang.state_machine import NetworkManager
                        ws.send(json.dumps({
                            "type": "state_update",
                            "state": NetworkManager.instance.current_state.value
                        }))
                except json.JSONDecodeError:
                    logger.warning("Received invalid JSON data: %s", data)
                except Exception as e:
                    logger.error("Error processing WebSocket message: %s", str(e))
                    
        except Exception as e:
            logger.error("WebSocket error: %s", str(e))
        finally:
            # Remove this connection when done
            if ws in active_connections:
                active_connections.remove(ws)

async def broadcast_state_update(state: State):
    """
    Broadcast a state update to all connected clients
    """
    global last_known_state
    
    # Update the last known state
    update_message = {
        "type": "state_update",
        "state": state.value
    }
    last_known_state = update_message
    
    # Convert to JSON string
    message = json.dumps(update_message)
    
    # Make a copy of active_connections to avoid modification during iteration
    connections = active_connections.copy()
    
    # Send to all active connections
    for ws in connections:
        try:
            # We're running in an async context, but flask-sock uses a synchronous API
            # So we need to run the send in a thread to avoid blocking
            await asyncio.to_thread(ws.send, message)
        except Exception as e:
            logger.error("Error sending WebSocket update: %s", str(e))
            # Connection might be dead, remove it
            if ws in active_connections:
                active_connections.remove(ws)

async def broadcast_alert(alert_type: str, message: str):
    """
    Broadcast an alert to all connected clients
    """
    alert_message = {
        "type": "alert",
        "alert_type": alert_type,
        "message": message
    }
    
    # Convert to JSON string
    message = json.dumps(alert_message)
    
    # Make a copy of active_connections to avoid modification during iteration
    connections = active_connections.copy()
    
    # Send to all active connections
    for ws in connections:
        try:
            await asyncio.to_thread(ws.send, message)
        except Exception as e:
            logger.error("Error sending WebSocket alert: %s", str(e))
            # Connection might be dead, remove it
            if ws in active_connections:
                active_connections.remove(ws)
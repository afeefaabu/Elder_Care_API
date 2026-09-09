import json
from typing import Dict, List
from fastapi import WebSocket

class AdherenceBroadcaster:
    """Manages live WebSocket connections for Caregivers."""
    
    def __init__(self):
        # Key: caregiver_id, Value: list of active WebSockets
        self.active_connections: Dict[int, List[WebSocket]] = {}

    async def connect(self, caregiver_id: int, websocket: WebSocket):
        await websocket.accept()
        if caregiver_id not in self.active_connections:
            self.active_connections[caregiver_id] = []
        self.active_connections[caregiver_id].append(websocket)

    def disconnect(self, caregiver_id: int, websocket: WebSocket):
        if caregiver_id in self.active_connections:
            if websocket in self.active_connections[caregiver_id]:
                self.active_connections[caregiver_id].remove(websocket)
            if not self.active_connections[caregiver_id]:
                del self.active_connections[caregiver_id]

    async def broadcast_to_caregiver(self, caregiver_id: int, event_type: str, payload: dict):
        if caregiver_id in self.active_connections:
            message = json.dumps({"event": event_type, "data": payload})
            for connection in self.active_connections[caregiver_id]:
                try:
                    await connection.send_text(message)
                except Exception:
                    pass

adherence_broadcaster = AdherenceBroadcaster()

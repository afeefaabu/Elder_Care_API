import json
from typing import Dict, List
from fastapi import WebSocket
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.pairing import ElderPairing
from app.models.user import User

class AdherenceBroadcaster:
    """Manages live WebSocket connections for every paired app user."""
    
    def __init__(self):
        # Key: user id, Value: all active devices for that user.
        self.active_connections: Dict[int, List[WebSocket]] = {}

    async def connect(self, user_id: int, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.setdefault(user_id, []).append(websocket)

    def disconnect(self, user_id: int, websocket: WebSocket):
        connections = self.active_connections.get(user_id)
        if not connections:
            return
        if websocket in connections:
            connections.remove(websocket)
        if not connections:
            del self.active_connections[user_id]

    async def broadcast_to_caregiver(self, caregiver_id: int, event_type: str, payload: dict):
        """Compatibility wrapper for existing adherence and SOS callers."""
        await self.broadcast_to_user(caregiver_id, event_type, payload)

    async def broadcast_to_user(self, user_id: int, event_type: str, payload: dict):
        message = json.dumps({"event": event_type, "data": payload})
        for connection in list(self.active_connections.get(user_id, [])):
            try:
                await connection.send_text(message)
            except Exception:
                self.disconnect(user_id, connection)

    async def broadcast_to_active_caregivers(
        self,
        db: AsyncSession,
        elder_id: int,
        event_type: str,
        payload: dict,
    ):
        """Send a sensitive event only to currently active care connections."""
        result = await db.execute(
            select(ElderPairing.caregiver_id).where(
                ElderPairing.elder_id == elder_id,
                ElderPairing.status == "ACTIVE",
            )
        )
        for caregiver_id in set(result.scalars().all()):
            await self.broadcast_to_user(caregiver_id, event_type, payload)

    async def broadcast_to_administrators(
        self,
        db: AsyncSession,
        event_type: str,
        payload: dict,
    ):
        """Keep connected administrator dashboards current without exposing care data publicly."""
        result = await db.execute(
            select(User.id).where(User.role == "ADMIN", User.is_active == True)
        )
        for administrator_id in set(result.scalars().all()):
            await self.broadcast_to_user(administrator_id, event_type, payload)

    async def publish_elder_update(
        self,
        db: AsyncSession,
        elder_id: int,
        resource: str,
        action: str,
        **details,
    ):
        """Signals the elder and each caregiver to reload shared elder data."""
        payload = {
            "elder_id": elder_id,
            "resource": resource,
            "action": action,
            **details,
        }
        await self.broadcast_to_user(elder_id, "ELDER_DATA_UPDATED", payload)
        await self.broadcast_to_active_caregivers(
            db, elder_id, "ELDER_DATA_UPDATED", payload
        )
        await self.broadcast_to_administrators(db, "ADMIN_DATA_UPDATED", payload)

adherence_broadcaster = AdherenceBroadcaster()

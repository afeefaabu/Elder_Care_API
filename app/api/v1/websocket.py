from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.services.adherence_service import adherence_broadcaster

router = APIRouter(tags=["Real-Time WebSockets"])

@router.websocket("/ws/adherence/{user_id}")
async def websocket_adherence_endpoint(websocket: WebSocket, user_id: int):
    """One live channel per signed-in elder or caregiver device."""
    await adherence_broadcaster.connect(user_id, websocket)
    try:
        while True:
            # Keep socket alive and receive client heartbeats/pings
            data = await websocket.receive_text()
            # Echo heartbeat
            await websocket.send_text(f'{{"type": "PONG", "received": "{data}"}}')
    except WebSocketDisconnect:
        adherence_broadcaster.disconnect(user_id, websocket)

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.services.adherence_service import adherence_broadcaster

router = APIRouter(tags=["Real-Time WebSockets"])

@router.websocket("/ws/adherence/{caregiver_id}")
async def websocket_adherence_endpoint(websocket: WebSocket, caregiver_id: int):
    await adherence_broadcaster.connect(caregiver_id, websocket)
    try:
        while True:
            # Keep socket alive and receive client heartbeats/pings
            data = await websocket.receive_text()
            # Echo heartbeat
            await websocket.send_text(f'{{"type": "PONG", "received": "{data}"}}')
    except WebSocketDisconnect:
        adherence_broadcaster.disconnect(caregiver_id, websocket)

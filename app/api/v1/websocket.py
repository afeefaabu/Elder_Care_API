import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.core.security import decode_access_token
from app.models.pairing import ElderPairing
from app.models.user import User
from app.services.adherence_service import adherence_broadcaster

router = APIRouter(tags=["Real-Time WebSockets"])

_CALL_SIGNAL_TYPES = {"INVITE", "ACCEPT", "REJECT", "CANCEL", "END"}


async def _paired_call_recipient(sender_id: int, target_id: int) -> User | None:
    """Return a recipient only when two active users are paired family members."""
    if sender_id == target_id:
        return None

    async with AsyncSessionLocal() as db:
        sender = await db.get(User, sender_id)
        recipient = await db.get(User, target_id)
        if not sender or not recipient or not sender.is_active or not recipient.is_active:
            return None
        if {sender.role, recipient.role} != {"CAREGIVER", "ELDER"}:
            return None

        caregiver_id = sender_id if sender.role == "CAREGIVER" else target_id
        elder_id = sender_id if sender.role == "ELDER" else target_id
        pairing_id = await db.scalar(
            select(ElderPairing.id).where(
                ElderPairing.caregiver_id == caregiver_id,
                ElderPairing.elder_id == elder_id,
                ElderPairing.status == "ACTIVE",
            )
        )
        return recipient if pairing_id is not None else None


async def _relay_call_signal(sender_id: int, raw_message: str) -> None:
    """Relay authenticated call control between a caregiver and paired elder."""
    if len(raw_message) > 4096:
        return
    try:
        message = json.loads(raw_message)
        if not isinstance(message, dict) or message.get("type") != "CALL_SIGNAL":
            return
        signal_type = str(message.get("signal_type", "")).upper()
        target_id = int(message.get("target_user_id"))
        call_id = str(message.get("call_id", "")).strip()
    except (TypeError, ValueError, json.JSONDecodeError):
        return

    if signal_type not in _CALL_SIGNAL_TYPES or not call_id or len(call_id) > 128:
        return

    recipient = await _paired_call_recipient(sender_id, target_id)
    if recipient is None:
        return

    async with AsyncSessionLocal() as db:
        sender = await db.get(User, sender_id)
        if sender is None:
            return
        sender_name = sender.full_name
        sender_phone = sender.phone_number

    await adherence_broadcaster.broadcast_to_user(
        target_id,
        "CALL_SIGNAL",
        {
            "call_id": call_id,
            "signal_type": signal_type,
            "from_user_id": sender_id,
            "from_name": sender_name,
            "from_phone": sender_phone,
        },
    )

@router.websocket("/ws/adherence/{user_id}")
async def websocket_adherence_endpoint(
    websocket: WebSocket,
    user_id: int,
    token: str | None = None,
):
    """One authenticated live channel per signed-in elder or caregiver device."""
    payload = decode_access_token(token or "")
    if not payload or payload.get("sub") != str(user_id):
        await websocket.close(code=1008)
        return
    await adherence_broadcaster.connect(user_id, websocket)
    try:
        while True:
            data = await websocket.receive_text()
            await _relay_call_signal(user_id, data)
            await websocket.send_text(json.dumps({"type": "PONG"}))
    except WebSocketDisconnect:
        adherence_broadcaster.disconnect(user_id, websocket)

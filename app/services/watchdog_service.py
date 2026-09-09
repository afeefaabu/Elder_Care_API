import asyncio
import logging
from datetime import timedelta
from sqlalchemy import select
from app.core.database import AsyncSessionLocal, utc_now
from app.core.config import settings
from app.models.adherence import AdherenceLog
from app.models.medication import Medication
from app.models.user import User
from app.services.telephony_service import telephony_service
from app.services.adherence_service import adherence_broadcaster

logger = logging.getLogger("watchdog")

class MedicationEscalationWatchdog:
    def __init__(self):
        self.is_running = False
        self._task = None

    async def start(self):
        self.is_running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info("25-Minute Medication Escalation Watchdog started.")

    async def stop(self):
        self.is_running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("25-Minute Medication Escalation Watchdog stopped.")

    async def _run_loop(self):
        while self.is_running:
            try:
                await self.check_missed_medications()
            except Exception as e:
                logger.error(f"Error in watchdog escalation loop: {e}")
            await asyncio.sleep(settings.WATCHDOG_CHECK_INTERVAL_SECONDS)

    async def check_missed_medications(self):
        now = utc_now()
        threshold_time = now - timedelta(minutes=settings.MISSED_MEDICATION_THRESHOLD_MINUTES)
        
        async with AsyncSessionLocal() as session:
            stmt = (
                select(AdherenceLog, Medication, User)
                .join(Medication, AdherenceLog.medication_id == Medication.id)
                .join(User, AdherenceLog.elder_id == User.id)
                .where(
                    AdherenceLog.status == "PENDING",
                    AdherenceLog.escalation_notified == False,
                    AdherenceLog.scheduled_time <= threshold_time,
                    Medication.escalation_enabled == True
                )
            )
            result = await session.execute(stmt)
            overdue_items = result.all()
            
            for log, med, elder in overdue_items:
                log.status = "MISSED_UNACKNOWLEDGED"
                log.escalation_notified = True
                log.escalation_time = now
                
                caregiver_stmt = select(User).where(User.id == med.caregiver_id)
                cg_res = await session.execute(caregiver_stmt)
                caregiver = cg_res.scalar_one_or_none()
                
                alert_text = (
                    f"URGENT: {elder.full_name} has not taken their {log.scheduled_slot} "
                    f"medication ({med.name} {med.strength}). "
                    f"25 minutes have elapsed without confirmation. Please call them immediately!"
                )
                
                if caregiver and caregiver.phone_number:
                    await telephony_service.send_sms(
                        to_phone=caregiver.phone_number,
                        body=alert_text
                    )
                    await telephony_service.send_push_notification(
                        token=caregiver.fcm_token or "mock_fcm_token",
                        title=f"🚨 MISSED MEDICATION: {elder.full_name}",
                        body=alert_text,
                        channel_id="siren_escalation_channel",
                        data={"adherence_id": log.id, "elder_id": elder.id, "action": "CALL_ELDER"}
                    )
                    await adherence_broadcaster.broadcast_to_caregiver(
                        caregiver_id=caregiver.id,
                        event_type="MISSED_PILL_ESCALATION",
                        payload={
                            "adherence_id": log.id,
                            "elder_id": elder.id,
                            "elder_name": elder.full_name,
                            "medication_name": med.name,
                            "scheduled_slot": log.scheduled_slot,
                            "status": log.status,
                            "alert_message": alert_text
                        }
                    )
            
            if overdue_items:
                await session.commit()

watchdog_engine = MedicationEscalationWatchdog()

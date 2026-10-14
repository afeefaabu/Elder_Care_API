"""Daily medication schedule creation shared by elder and caregiver flows."""

from datetime import timedelta
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import utc_now
from app.models.adherence import AdherenceLog
from app.models.medication import Medication


async def ensure_daily_medication_logs(
    db: AsyncSession,
    elder_id: Optional[int] = None,
) -> int:
    """Create one pending dose per active medication alarm for the current day.

    Completion is deliberately stored per calendar day.  At the next midnight,
    a fresh pending dose is created while the previous day's taken/missed log
    remains available as history.
    """
    now = utc_now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    tomorrow_start = today_start + timedelta(days=1)

    medication_stmt = select(Medication).where(Medication.is_active == True)
    if elder_id is not None:
        medication_stmt = medication_stmt.where(Medication.elder_id == elder_id)
    medication_result = await db.execute(medication_stmt)
    medications = medication_result.scalars().all()
    if not medications:
        return 0

    medication_ids = [medication.id for medication in medications]
    existing_stmt = select(AdherenceLog.medication_id, AdherenceLog.scheduled_slot).where(
        AdherenceLog.medication_id.in_(medication_ids),
        AdherenceLog.scheduled_time >= today_start,
        AdherenceLog.scheduled_time < tomorrow_start,
    )
    existing_result = await db.execute(existing_stmt)
    existing_slots = {
        (medication_id, scheduled_slot)
        for medication_id, scheduled_slot in existing_result.all()
    }

    created = 0
    for medication in medications:
        for slot in (value.strip() for value in medication.alarm_times_csv.split(',')):
            if not slot or (medication.id, slot) in existing_slots:
                continue
            try:
                hour, minute = map(int, slot.split(':'))
                scheduled_time = today_start.replace(hour=hour, minute=minute)
            except (TypeError, ValueError):
                # Invalid legacy data must not prevent valid medicines from
                # receiving their daily schedule.
                continue

            db.add(AdherenceLog(
                elder_id=medication.elder_id,
                medication_id=medication.id,
                scheduled_slot=slot,
                scheduled_time=scheduled_time,
                status='PENDING',
            ))
            created += 1

    if created:
        await db.commit()
    return created

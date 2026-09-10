import os
import shutil
from typing import List, Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db, utc_now
from app.models.workout import SeniorWorkout
from app.models.routine import DailyRoutine
from app.models.pairing import ElderPairing
from app.models.user import User
from app.schemas.workout import (
    WorkoutCreate,
    WorkoutUpdate,
    WorkoutResponse,
    WorkoutLibraryItem
)
from app.services.adherence_service import adherence_broadcaster

router = APIRouter(prefix='/workouts', tags=['Senior Workouts & Guided Videos'])

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
WORKOUT_UPLOAD_DIR = os.path.join(BASE_DIR, 'uploads', 'workouts')
os.makedirs(WORKOUT_UPLOAD_DIR, exist_ok=True)

DOCTOR_APPROVED_LIBRARY: List[WorkoutLibraryItem] = [
    WorkoutLibraryItem(
        id='chair-yoga-15',
        title='15-Minute Chair Yoga & Joint Mobility',
        category='CHAIR_YOGA',
        default_duration=15,
        description='Doctor-approved seated spine & neck mobility routine designed for seniors with arthritis and high BP.',
        benefits='Improves spinal alignment, reduces joint stiffness, regulates resting blood pressure.',
        default_video_url='https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/ForBiggerBlazes.mp4',
        instructions='Sit upright on a stable armless chair. Keep your feet flat on the floor. Follow the instructor gentle neck and shoulder rotations. Breathe in slowly through the nose.',
        default_voice_prompt='It is time for your 15-minute chair yoga and mobility session!'
    ),
    WorkoutLibraryItem(
        id='cardiac-breathing-10',
        title='10-Minute Deep Diaphragmatic Breathing',
        category='BREATHING',
        default_duration=10,
        description='Cardiologist-recommended rhythmic breathing pattern (Pranayama) to stabilize heart rate variability.',
        benefits='Oxygenates blood flow, reduces cortisol and anxiety, stabilizes heart rhythm.',
        default_video_url='https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/ForBiggerEscapes.mp4',
        instructions='Rest hands comfortably on your abdomen. Inhale deeply through your nose for 4 seconds, hold for 2 seconds, and exhale gently through your mouth for 6 seconds.',
        default_voice_prompt='Time for your 10-minute relaxing deep breathing exercise.'
    ),
    WorkoutLibraryItem(
        id='ankle-knee-12',
        title='12-Minute Seated Ankle & Knee Rotations',
        category='MOBILITY',
        default_duration=12,
        description='Physiotherapy protocol for promoting venous return in lower limbs and preventing deep vein thrombosis.',
        benefits='Enhances lower limb circulation, lubricates knee joints, prevents swelling.',
        default_video_url='https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/ForBiggerFun.mp4',
        instructions='Gently extend right leg and rotate ankle clockwise 10 times, then counter-clockwise. Switch to left leg. Next, gently flex and straighten both knees.',
        default_voice_prompt='Time for your 12-minute ankle and knee circulation routine.'
    ),
]

@router.get('/library', response_model=List[WorkoutLibraryItem])
async def get_workout_library():
    return DOCTOR_APPROVED_LIBRARY

@router.post('/upload-video')
async def upload_workout_video(file: UploadFile = File(...)):
    ext = os.path.splitext(file.filename)[1].lower()
    allowed = ['.mp4', '.mov', '.webm', '.mkv', '.avi', '.m4v']
    if ext not in allowed:
        allowed_str = ", ".join(allowed)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f'Unsupported video format. Allowed formats: {allowed_str}'
        )
    timestamp = utc_now().strftime('%Y%m%d%H%M%S')
    filename = f'workout_{timestamp}_{file.filename}'
    filepath = os.path.join(WORKOUT_UPLOAD_DIR, filename)
    with open(filepath, 'wb') as buffer:
        shutil.copyfileobj(file.file, buffer)
    return {
        'status': 'success',
        'video_url': f'/uploads/workouts/{filename}',
        'filename': filename
    }

@router.get('', response_model=List[WorkoutResponse])
async def get_workouts(elder_id: int, db: AsyncSession = Depends(get_db)):
    stmt = (
        select(SeniorWorkout)
        .where(SeniorWorkout.elder_id == elder_id)
        .order_by(SeniorWorkout.scheduled_time)
    )
    res = await db.execute(stmt)
    return res.scalars().all()

@router.post('', response_model=WorkoutResponse)
async def create_workout(payload: WorkoutCreate, db: AsyncSession = Depends(get_db)):
    workout = SeniorWorkout(
        elder_id=payload.elder_id,
        title=payload.title.strip(),
        description=payload.description.strip() if payload.description else None,
        category=payload.category.upper(),
        video_url=payload.video_url.strip() if payload.video_url else None,
        duration_minutes=payload.duration_minutes,
        scheduled_time=payload.scheduled_time.strip(),
        instructions=payload.instructions.strip() if payload.instructions else None,
        voice_prompt=payload.voice_prompt.strip() if payload.voice_prompt else None,
        is_active=True,
        created_at=utc_now()
    )
    db.add(workout)
    await db.commit()
    await db.refresh(workout)

    routine_stmt = select(DailyRoutine).where(
        DailyRoutine.elder_id == payload.elder_id,
        DailyRoutine.category == 'MOBILITY',
        DailyRoutine.time_str == payload.scheduled_time.strip()
    )
    routine_res = await db.execute(routine_stmt)
    existing_routine = routine_res.scalar_one_or_none()
    if not existing_routine:
        new_routine = DailyRoutine(
            elder_id=payload.elder_id,
            time_str=payload.scheduled_time.strip(),
            category='MOBILITY',
            title=payload.title.strip(),
            description=payload.description or f'{payload.duration_minutes}-min guided workout',
            voice_prompt=payload.voice_prompt or f'Time for your {payload.duration_minutes}-minute {payload.title}',
            target_metric=f'{payload.duration_minutes} mins',
            is_active=True,
            created_at=utc_now()
        )
        db.add(new_routine)
        await db.commit()

    return workout

@router.put('/{workout_id}', response_model=WorkoutResponse)
async def update_workout(workout_id: int, payload: WorkoutUpdate, db: AsyncSession = Depends(get_db)):
    stmt = select(SeniorWorkout).where(SeniorWorkout.id == workout_id)
    res = await db.execute(stmt)
    workout = res.scalar_one_or_none()
    if not workout:
        raise HTTPException(status_code=404, detail='Workout not found')

    if payload.title is not None:
        workout.title = payload.title.strip()
    if payload.description is not None:
        workout.description = payload.description.strip()
    if payload.category is not None:
        workout.category = payload.category.upper()
    if payload.video_url is not None:
        workout.video_url = payload.video_url.strip()
    if payload.duration_minutes is not None:
        workout.duration_minutes = payload.duration_minutes
    if payload.scheduled_time is not None:
        workout.scheduled_time = payload.scheduled_time.strip()
    if payload.instructions is not None:
        workout.instructions = payload.instructions.strip()
    if payload.voice_prompt is not None:
        workout.voice_prompt = payload.voice_prompt.strip()
    if payload.is_active is not None:
        workout.is_active = payload.is_active

    await db.commit()
    await db.refresh(workout)
    return workout

@router.delete('/{workout_id}')
async def delete_workout(workout_id: int, db: AsyncSession = Depends(get_db)):
    stmt = select(SeniorWorkout).where(SeniorWorkout.id == workout_id)
    res = await db.execute(stmt)
    workout = res.scalar_one_or_none()
    if not workout:
        raise HTTPException(status_code=404, detail='Workout not found')

    await db.delete(workout)
    await db.commit()
    return {'status': 'success', 'message': f'Workout {workout_id} deleted.'}

@router.post('/{workout_id}/toggle', response_model=WorkoutResponse)
async def toggle_workout(workout_id: int, db: AsyncSession = Depends(get_db)):
    stmt = select(SeniorWorkout).where(SeniorWorkout.id == workout_id)
    res = await db.execute(stmt)
    workout = res.scalar_one_or_none()
    if not workout:
        raise HTTPException(status_code=404, detail='Workout not found')

    workout.is_active = not workout.is_active
    await db.commit()
    await db.refresh(workout)
    return workout

@router.post('/{workout_id}/complete')
async def complete_workout(workout_id: int, db: AsyncSession = Depends(get_db)):
    stmt = select(SeniorWorkout).where(SeniorWorkout.id == workout_id)
    res = await db.execute(stmt)
    workout = res.scalar_one_or_none()
    if not workout:
        raise HTTPException(status_code=404, detail='Workout not found')

    now = utc_now()
    workout.last_completed_at = now
    await db.commit()

    pairing_stmt = select(ElderPairing).where(ElderPairing.elder_id == workout.elder_id)
    pairing_res = await db.execute(pairing_stmt)
    pairing = pairing_res.scalar_one_or_none()
    if pairing:
        elder_stmt = select(User).where(User.id == workout.elder_id)
        elder_res = await db.execute(elder_stmt)
        elder = elder_res.scalar_one_or_none()
        elder_name = elder.full_name if elder else 'Senior Citizen'

        await adherence_broadcaster.broadcast_to_caregiver(
            caregiver_id=pairing.caregiver_id,
            event_type='WORKOUT_COMPLETED',
            payload={
                'workout_id': workout.id,
                'elder_id': workout.elder_id,
                'title': workout.title,
                'duration_minutes': workout.duration_minutes,
                'completed_at': now.isoformat(),
                'status': 'COMPLETED',
                'message': f'?? {elder_name} completed {workout.title} ({workout.duration_minutes} mins)!'
            }
        )

    return {
        'status': 'success',
        'message': f'Great job! {workout.title} marked as completed.',
        'last_completed_at': now.isoformat()
    }


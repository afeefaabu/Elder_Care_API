"""Small, server-side Gemini adapter for the senior voice assistant.

Only a short, non-identifying care-plan summary is sent to Gemini.  The
backend validates every returned intent and performs the real action itself.
"""

import json
from typing import Any

import httpx

from app.core.config import settings


ALLOWED_INTENTS = {
    "PENSION_STATUS",
    "NEXT_MEDICINE",
    "LOG_WATER",
    "TAKE_MEDICINE",
    "COMPLETE_ROUTINE",
    "BOOK_TAXI",
    "CALL_DOCTOR",
    "EMERGENCY",
    "GENERAL",
}


class GeminiVoiceService:
    """Uses Gemini only for intent recognition, never for authorizing actions."""

    async def understand(self, query: str, context: dict[str, Any]) -> dict[str, str]:
        if not settings.GEMINI_API_KEY:
            return {
                "intent": "GENERAL",
                "reply": "Voice help is almost ready. Please add the Gemini API key to the backend settings.",
                "target_name": "",
            }

        prompt = """You are a voice assistant for an older adult using ElderCare.
Return JSON only, with these keys: intent, target_name, reply.

Allowed intents: PENSION_STATUS, NEXT_MEDICINE, LOG_WATER, TAKE_MEDICINE,
COMPLETE_ROUTINE, BOOK_TAXI, CALL_DOCTOR, EMERGENCY, GENERAL.

Rules:
- You understand the user's request but you do not diagnose, prescribe, or change medication.
- For symptoms, danger, falls, chest pain, breathing problems, or emergencies, use EMERGENCY and tell the user to use SOS or local emergency help.
- For an action, use the closest allowed intent. target_name must be a name from the supplied care plan, or an empty string.
- Keep reply short, gentle, and easy to understand. Do not claim an action was completed.

Care plan summary (do not repeat private details):
""" + json.dumps(context, ensure_ascii=False) + "\n\nUser request: " + query

        endpoint = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{settings.GEMINI_MODEL}:generateContent"
        )
        body = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.1,
                "maxOutputTokens": 180,
                "responseMimeType": "application/json",
            },
        }
        try:
            async with httpx.AsyncClient(timeout=12.0) as client:
                response = await client.post(
                    endpoint,
                    params={"key": settings.GEMINI_API_KEY},
                    json=body,
                )
            response.raise_for_status()
            payload = response.json()
            text = payload["candidates"][0]["content"]["parts"][0]["text"]
            result = json.loads(text)
        except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError):
            return {
                "intent": "GENERAL",
                "reply": "I could not reach voice help right now. Please try again or use one of the large buttons below.",
                "target_name": "",
            }

        intent = str(result.get("intent", "GENERAL")).upper()
        return {
            "intent": intent if intent in ALLOWED_INTENTS else "GENERAL",
            "reply": str(result.get("reply", "How can I help you today?"))[:280],
            "target_name": str(result.get("target_name", ""))[:120],
        }


gemini_voice_service = GeminiVoiceService()

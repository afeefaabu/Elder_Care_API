"""Small, server-side Gemini adapter for the senior voice assistant.

Only a short, non-identifying care-plan summary is sent to Gemini.  The
backend validates every returned intent and performs the real action itself.
"""

import json
import logging
from typing import Any

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


ALLOWED_INTENTS = {
    "PENSION_STATUS",
    "NEXT_ACTIVITY",
    "NEXT_WORKOUT",
    "NEXT_MEDICINE",
    "LOG_WATER",
    "TAKE_MEDICINE",
    "COMPLETE_ROUTINE",
    "BOOK_TAXI",
    "CALL_DOCTOR",
    "EMERGENCY",
    "GENERAL",
}


def _local_intent(query: str, language: str = "en") -> dict[str, str]:
    """Keep core elder-care commands useful during a temporary AI outage."""
    text = query.casefold()
    is_malayalam = language == "ml"
    replies = {
        "emergency": "അടിയന്തരാവസ്ഥയാണെങ്കിൽ ഇപ്പോൾ ചുവന്ന SOS ബട്ടൺ അമർത്തുക. പ്രാദേശിക അടിയന്തര സേവനത്തെ വിളിക്കുക.",
        "pension": "നിങ്ങളുടെ പെൻഷൻ നില ഞാൻ പരിശോധിക്കാം.",
        "next_activity": "നിങ്ങളുടെ അടുത്ത പ്രവർത്തനം ഞാൻ പരിശോധിക്കാം.",
        "next_medicine": "നിങ്ങളുടെ അടുത്ത മരുന്ന് ഞാൻ പരിശോധിക്കാം.",
        "water": "ഒരു ഗ്ലാസ് വെള്ളം രേഖപ്പെടുത്തട്ടേ?",
        "taxi": "നിങ്ങളുടെ വിശ്വസ്ത ടാക്സി കോൺടാക്ടിനെ വിളിക്കാൻ ഞാൻ സഹായിക്കാം.",
        "doctor": "നിങ്ങളുടെ വിശ്വസ്ത ഡോക്ടറെ വിളിക്കാൻ ഞാൻ സഹായിക്കാം.",
        "medicine": "നിങ്ങൾക്കായി ബാക്കി നിൽക്കുന്ന മരുന്ന് ഞാൻ പരിശോധിക്കാം.",
        "routine": "നിങ്ങൾ പൂർത്തിയാക്കാൻ ആഗ്രഹിക്കുന്ന പ്രവർത്തനം ഞാൻ പരിശോധിക്കാം.",
        "general": "അടുത്ത പ്രവർത്തനം, മരുന്ന്, വെള്ളം, ഡോക്ടർ, ടാക്സി, പെൻഷൻ, SOS എന്നിവയിൽ ഞാൻ സഹായിക്കും. ലളിതമായി ചോദിക്കൂ.",
    }

    def reply(key: str, english: str) -> str:
        return replies[key] if is_malayalam else english

    malayalam_emergency = ("അടിയന്തര", "സഹായം", "വീണ", "നെഞ്ച്", "ശ്വാസ")
    malayalam_medicine = ("മരുന്ന്", "ഗുളിക", "ടാബ്ലറ്റ്")
    malayalam_next = ("അടുത്ത", "അടുത്തത്")
    if any(word in text for word in ("emergency", "sos", "fell", "chest pain", "cannot breathe")):
        return {"intent": "EMERGENCY", "reply": reply("emergency", "Please use the red SOS button now. If this is an emergency, call local emergency services."), "target_name": ""}
    if any(word in text for word in malayalam_emergency):
        return {"intent": "EMERGENCY", "reply": reply("emergency", "Please use the red SOS button now. If this is an emergency, call local emergency services."), "target_name": ""}
    if "pension" in text or "പെൻഷൻ" in text:
        return {"intent": "PENSION_STATUS", "reply": reply("pension", "I will check your pension status."), "target_name": ""}
    if ("next" in text and "workout" in text) or (any(word in text for word in malayalam_next) and "വ്യായാമം" in text):
        return {"intent": "NEXT_WORKOUT", "reply": reply("next_activity", "I will open your next workout."), "target_name": ""}
    if ("next" in text and any(word in text for word in ("activity", "task", "schedule", "routine"))) or (any(word in text for word in malayalam_next) and any(word in text for word in ("പ്രവർത്തനം", "പട്ടിക"))):
        return {"intent": "NEXT_ACTIVITY", "reply": reply("next_activity", "I will check your next activity."), "target_name": ""}
    if ("next" in text and any(word in text for word in ("medicine", "medication", "pill", "tablet"))) or (any(word in text for word in malayalam_next) and any(word in text for word in malayalam_medicine)):
        return {"intent": "NEXT_MEDICINE", "reply": reply("next_medicine", "I will check your next medicine."), "target_name": ""}
    if any(word in text for word in ("water", "drink", "glass", "വെള്ളം")):
        return {"intent": "LOG_WATER", "reply": reply("water", "Would you like me to record one glass of water?"), "target_name": ""}
    if any(word in text for word in ("taxi", "cab", "driver", "ടാക്സി")):
        return {"intent": "BOOK_TAXI", "reply": reply("taxi", "I can help you call your trusted taxi contact."), "target_name": ""}
    if any(word in text for word in ("doctor", "clinic", "appointment", "ഡോക്ടർ")):
        return {"intent": "CALL_DOCTOR", "reply": reply("doctor", "I can help you call your trusted doctor."), "target_name": ""}
    if any(word in text for word in ("medicine", "medication", "pill", "tablet", "took", *malayalam_medicine)):
        return {"intent": "TAKE_MEDICINE", "reply": reply("medicine", "I will check the medicine waiting for you."), "target_name": ""}
    if any(word in text for word in ("done", "completed", "finished", "പൂർത്തി")):
        return {"intent": "COMPLETE_ROUTINE", "reply": reply("routine", "I will check the routine you would like to mark complete."), "target_name": ""}
    return {
        "intent": "GENERAL",
        "reply": reply("general", "I can help with your next activity, medicines, water, doctor, taxi, pension, and SOS. Please ask one of these in simple words."),
        "target_name": "",
    }


class GeminiVoiceService:
    """Uses Gemini only for intent recognition, never for authorizing actions."""

    async def understand(
        self, query: str, context: dict[str, Any], language: str = "en"
    ) -> dict[str, str]:
        if not settings.GEMINI_API_KEY:
            return _local_intent(query, language)

        prompt = """You are a voice assistant for an older adult using ElderCare.
Return JSON only, with these keys: intent, target_name, reply.

Allowed intents: PENSION_STATUS, NEXT_ACTIVITY, NEXT_WORKOUT, NEXT_MEDICINE, LOG_WATER, TAKE_MEDICINE,
COMPLETE_ROUTINE, BOOK_TAXI, CALL_DOCTOR, EMERGENCY, GENERAL.

Rules:
- You understand the user's request but you do not diagnose, prescribe, or change medication.
- For symptoms, danger, falls, chest pain, breathing problems, or emergencies, use EMERGENCY and tell the user to use SOS or local emergency help.
- For an action, use the closest allowed intent. target_name must be a name from the supplied care plan, or an empty string.
- Keep reply short, gentle, and easy to understand. Do not claim an action was completed.
- Never invent a medicine, activity, contact, date, payment, or health fact. Use only the supplied care plan.
- For a request outside the supplied information, do not say "I don't know". Briefly explain the safe limit and offer the closest supported next step.
- Answer in Malayalam script when requested_language is "ml". Otherwise answer in English.

Care plan summary (do not repeat private details):
""" + json.dumps(context, ensure_ascii=False) + "\n\nrequested_language: " + language + "\n\nUser request: " + query

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
        except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as error:
            logger.warning("Gemini voice request failed (%s); using local care-plan fallback.", type(error).__name__)
            return _local_intent(query, language)

        intent = str(result.get("intent", "GENERAL")).upper()
        return {
            "intent": intent if intent in ALLOWED_INTENTS else "GENERAL",
            "reply": str(result.get("reply", "How can I help you today?"))[:280],
            "target_name": str(result.get("target_name", ""))[:120],
        }


gemini_voice_service = GeminiVoiceService()

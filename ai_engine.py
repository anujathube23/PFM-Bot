"""Gemini integration. The API key is read from the environment only; it is never
sent to the browser or stored in the database."""
import json
import os
import re

from google import genai
from google.genai import errors
from google.genai import types

REQUIRED_KEYS = ("budget_plan", "saving_suggestions", "monthly_summary")

PERSONA_HINTS = {
    "salaried": "Fixed monthly salary. Focus on the monthly surplus and automating savings.",
    "student": "Fixed limited allowance. Compare essential vs discretionary spending and recommend spending discipline.",
    "freelancer": "Variable multi-client income. Consider income volatility and recommend an emergency fund (3-6 months of expenses).",
    "household": "Shared family expenses. Flag every category over its budget and suggest where to trim.",
}

SYSTEM_PROMPT = """You are a careful personal finance advisor. Analyze the JSON snapshot
of one user's month and reply with ONLY a JSON object (no markdown) shaped exactly like:
{
  "budget_plan": "string: a customized budgeting strategy with rough per-category targets",
  "saving_suggestions": ["string", "..."],
  "monthly_summary": "string: income vs expenses, savings rate, and a financial health verdict"
}
Rules: use the snapshot's currency; base every number on the snapshot; give 3-6 specific,
actionable suggestions; keep it practical and non-judgmental. This is general guidance,
not licensed financial advice."""


class AIEngineError(Exception):
    pass


def _parse_json(text):
    """Models occasionally wrap JSON in code fences; strip them defensively."""
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()
    return json.loads(text)


def analyze_finances(snapshot: dict) -> dict:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise AIEngineError("GEMINI_API_KEY is not set. Add it to your environment or .env file.")

    # Initialize the modern Google GenAI client
    client = genai.Client(api_key=api_key)
    model_name = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
    fallback_model = os.environ.get("GEMINI_FALLBACK_MODEL", "gemini-1.5-flash")

    hint = PERSONA_HINTS.get(snapshot.get("persona"), "")
    prompt = f"User type guidance: {hint}\n\nFinancial snapshot:\n{json.dumps(snapshot, indent=2)}"

    try:
        config = types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            response_mime_type="application/json",
            temperature=0.4,
        )
        try:
            response = client.models.generate_content(
                model=model_name, contents=prompt, config=config,
            )
        except errors.APIError as exc:
            if exc.code != 503 or not fallback_model or fallback_model == model_name:
                raise
            try:
                response = client.models.generate_content(
                    model=fallback_model, contents=prompt, config=config,
                )
            except errors.APIError as fallback_exc:
                raise AIEngineError(
                    f"Primary model '{model_name}' returned 503; fallback model "
                    f"'{fallback_model}' failed: {fallback_exc}"
                ) from fallback_exc
        data = _parse_json(response.text)
    except json.JSONDecodeError as exc:
        raise AIEngineError("The AI returned a response that was not valid JSON. Try again.") from exc
    except AIEngineError:
        raise
    except Exception as exc:  # network, quota, invalid key, blocked content...
        raise AIEngineError(f"Gemini request failed: {exc}") from exc

    missing = [k for k in REQUIRED_KEYS if k not in data]
    if missing:
        raise AIEngineError(f"AI response is missing: {', '.join(missing)}")
    if not isinstance(data["saving_suggestions"], list):
        data["saving_suggestions"] = [str(data["saving_suggestions"])]
    return {k: data[k] for k in REQUIRED_KEYS}
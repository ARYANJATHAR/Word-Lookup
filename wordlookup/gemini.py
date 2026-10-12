import json
import logging
import re
import threading
from collections import OrderedDict
from dataclasses import asdict, dataclass, field

import requests

from wordlookup.config import app_data_dir

API_ROOT = "https://generativelanguage.googleapis.com/v1beta"
TIMEOUT = (5, 20)  # connect, read

_RESPONSE_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "part_of_speech": {"type": "STRING"},
        "pronunciation": {"type": "STRING"},
        "meaning": {"type": "STRING"},
        "example": {"type": "STRING"},
        "synonyms": {"type": "ARRAY", "items": {"type": "STRING"}},
    },
    "required": ["meaning", "synonyms"],
}

_WORD = r"[^\W\d_]+(?:['’\-][^\W\d_]+)*"
_PHRASE_RE = re.compile(rf"{_WORD}(?: {_WORD}){{0,2}}")


class LookupFailed(Exception):
    """A lookup error with a message that is safe to show to the user."""


@dataclass
class Definition:
    phrase: str
    meaning: str
    synonyms: list = field(default_factory=list)
    part_of_speech: str = ""
    pronunciation: str = ""
    example: str = ""


def normalize_phrase(text):
    """Return a cleaned 1-3 word phrase, or None if the text isn't something to look up."""
    if not text or len(text) > 80:
        return None
    text = " ".join(text.split()).strip(".,;:!?\"'“”‘’()[]{}")
    if not text or len(text) > 60 or not _PHRASE_RE.fullmatch(text):
        return None
    return text


def _error_message(response, model):
    try:
        detail = response.json().get("error", {})
    except ValueError:
        detail = {}
    text = json.dumps(detail)
    status = response.status_code
    if "API_KEY_INVALID" in text or status in (401, 403):
        return "Your Gemini API key was rejected. Update it in Settings."
    if status == 404:
        return f"The model “{model}” isn't available. Choose another one in Settings."
    if status == 429:
        return "Gemini rate limit reached. Wait a moment and try again."
    if status >= 500:
        return "Gemini is having trouble right now. Try again shortly."
    return detail.get("message") or f"Gemini returned an error (HTTP {status})."


def lookup(phrase, api_key, model):
    prompt = (
        f'Define the English word or phrase "{phrase}" for a quick dictionary popup.\n'
        "- part_of_speech: short label such as noun, verb, adjective, idiom\n"
        "- pronunciation: IPA for single words, empty string otherwise\n"
        "- meaning: its most common meaning in one clear sentence of at most 25 words\n"
        "- example: one short, natural sentence that uses it\n"
        "- synonyms: 3 to 5 synonyms, or an empty list if none fit"
    )
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "responseMimeType": "application/json",
            "responseSchema": _RESPONSE_SCHEMA,
            "temperature": 0.2,
        },
    }
    try:
        response = requests.post(
            f"{API_ROOT}/models/{model}:generateContent",
            headers={"x-goog-api-key": api_key},
            json=body,
            timeout=TIMEOUT,
        )
    except requests.Timeout:
        raise LookupFailed("Gemini took too long to respond. Try again.")
    except requests.ConnectionError:
        raise LookupFailed("Couldn't reach Gemini. Check your internet connection.")

    if response.status_code != 200:
        logging.warning(f"Gemini HTTP {response.status_code} for model {model}")
        raise LookupFailed(_error_message(response, model))

    try:
        text = response.json()["candidates"][0]["content"]["parts"][0]["text"]
        data = json.loads(text)
    except (KeyError, IndexError, ValueError):
        raise LookupFailed("Gemini didn't return a definition for this word.")

    synonyms = [s.strip() for s in data.get("synonyms") or [] if s and s.strip()]
    return Definition(
        phrase=phrase,
        meaning=(data.get("meaning") or "").strip(),
        synonyms=[s for s in synonyms if s.lower() != phrase.lower()][:5],
        part_of_speech=(data.get("part_of_speech") or "").strip(),
        pronunciation=(data.get("pronunciation") or "").strip().strip("/"),
        example=(data.get("example") or "").strip(),
    )


class Cache:
    """Small persistent LRU cache of definitions; also serves as lookup history."""

    def __init__(self, limit=500):
        self._path = app_data_dir() / "cache.json"
        self._limit = limit
        self._lock = threading.Lock()
        self._items = OrderedDict()
        try:
            for key, value in json.loads(self._path.read_text(encoding="utf-8")):
                self._items[key] = Definition(**value)
        except FileNotFoundError:
            pass
        except Exception as e:
            logging.warning(f"Ignoring unreadable cache: {e}")

    @staticmethod
    def _key(model, phrase):
        return f"{model}|{phrase.lower()}"

    def get(self, model, phrase):
        with self._lock:
            key = self._key(model, phrase)
            item = self._items.get(key)
            if item:
                self._items.move_to_end(key)
            return item

    def put(self, model, definition):
        with self._lock:
            key = self._key(model, definition.phrase)
            self._items[key] = definition
            self._items.move_to_end(key)
            while len(self._items) > self._limit:
                self._items.popitem(last=False)
            data = [(k, asdict(v)) for k, v in self._items.items()]
        try:
            self._path.write_text(json.dumps(data), encoding="utf-8")
        except OSError as e:
            logging.warning(f"Could not save cache: {e}")

    def recent(self, count=8):
        with self._lock:
            seen, result = set(), []
            for item in reversed(self._items.values()):
                if item.phrase.lower() not in seen:
                    seen.add(item.phrase.lower())
                    result.append(item)
                if len(result) == count:
                    break
            return result

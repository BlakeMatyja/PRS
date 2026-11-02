"""AI categorization adapter (AIR-01, AIR-02, FR-07).

The AI only SUGGESTS a category. It never saves anything.
Two implementations share one interface:
  * ClaudeCategorizer          - real LLM call (needs ANTHROPIC_API_KEY)
  * KeywordFallbackCategorizer - simple keyword matching. NOT an AI model;
                                 a clearly labeled temporary fallback only.
"""
import json
import os
import urllib.request
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

from .exceptions import AIUnavailableError

CATEGORIES = ("Respiratory", "Digestive", "Musculoskeletal", "General/Other")


@dataclass
class Suggestion:
    category: Optional[str]   # None means "cannot recommend"
    source: str               # "ai" or "fallback"
    message: str


class Categorizer(ABC):
    label = "unknown"
    source = "unknown"

    @abstractmethod
    def suggest(self, text) -> Optional[str]:
        """Return a category, or None if uncertain. Raise AIUnavailableError on failure."""


class ClaudeCategorizer(Categorizer):
    label = "Claude AI model"
    source = "ai"
    URL = "https://api.anthropic.com/v1/messages"
    MODEL = "claude-haiku-5-5"

    def __init__(self, api_key, timeout=3):
        self.api_key = api_key
        self.timeout = timeout

    def suggest(self, text):
        prompt = (
            "Classify this clinic visit note into exactly one category: "
            "Respiratory, Digestive, Musculoskeletal, or General/Other. "
            "Reply with only the category name, or UNCERTAIN if you cannot tell. "
            "This is a filing label, not a diagnosis.\n\nNote: " + text
        )
        body = json.dumps({
            "model": self.MODEL,
            "max_tokens": 20,
            "messages": [{"role": "user", "content": prompt}],
        }).encode()
        request = urllib.request.Request(self.URL, data=body, headers={
            "content-type": "application/json",
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
        })
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as resp:
                data = json.loads(resp.read())
            answer = data["content"][0]["text"].strip()
        except Exception as exc:
            raise AIUnavailableError("AI service unavailable: %s" % exc)
        return answer if answer in CATEGORIES else None


class KeywordFallbackCategorizer(Categorizer):
    label = "Keyword fallback (NOT an AI model)"
    source = "fallback"
    KEYWORDS = {
        "Respiratory": ["cough", "breath", "wheez", "asthma", "lung", "chest", "congestion", "sinus"],
        "Digestive": ["stomach", "nausea", "vomit", "diarrhea", "abdominal", "constipation", "bowel"],
        "Musculoskeletal": ["back pain", "knee", "joint", "muscle", "sprain", "fracture", "shoulder"],
    }

    def suggest(self, text):
        text = text.lower()
        scores = {cat: sum(k in text for k in words) for cat, words in self.KEYWORDS.items()}
        best = max(scores.values())
        winners = [c for c, s in scores.items() if s == best]
        if best == 0 or len(winners) != 1:
            return None
        return winners[0]


class CategorizationService:
    """Never raises: any AI problem results in a Suggestion with category=None."""

    def __init__(self, primary: Optional[Categorizer] = None,
                 fallback: Optional[Categorizer] = None):
        self.primary = primary
        self.fallback = fallback

    @classmethod
    def from_environment(cls):
        key = os.environ.get("ANTHROPIC_API_KEY")
        primary = ClaudeCategorizer(key) if key else None
        return cls(primary, KeywordFallbackCategorizer())

    def suggest(self, text) -> Suggestion:
        notice = ""
        if self.primary is not None:
            try:
                category = self.primary.suggest(text)
                if category:
                    return Suggestion(category, self.primary.source, self.primary.label)
                return Suggestion(None, self.primary.source,
                                  "The AI cannot recommend a category for this note.")
            except AIUnavailableError:
                notice = "AI service unavailable; using keyword fallback. "
        if self.fallback is not None:
            try:
                category = self.fallback.suggest(text)
            except Exception:
                category = None
            if category:
                return Suggestion(category, self.fallback.source, notice + self.fallback.label)
        return Suggestion(None, "none", notice + "Cannot recommend a category.")

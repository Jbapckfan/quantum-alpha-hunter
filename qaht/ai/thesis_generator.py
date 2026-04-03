"""OpenRouter-backed trade thesis generation."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger("qaht.ai.thesis")

_OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
_CACHE_TTL = timedelta(hours=4)


class ThesisGenerator:
    """Generate concise three-sentence trade theses from scan data."""

    _CACHE: Dict[str, tuple[datetime, Dict[str, Any]]] = {}

    def __init__(
        self,
        provider: str = "openrouter",
        model: str = "meta-llama/llama-3.3-70b-instruct:free",
    ) -> None:
        self.provider = provider
        self.model = model
        self.api_key = os.environ.get("OPENROUTER_API_KEY", "").strip()

    def generate(
        self,
        scan_result: Dict[str, Any],
        resistance_levels: List[Dict[str, Any]],
        combo_result: Optional[Any] = None,
    ) -> str:
        """Generate or retrieve a cached thesis for one ticker."""
        ticker = str(scan_result.get("ticker", "")).upper()
        cached = self._CACHE.get(ticker)
        now = datetime.utcnow()
        if cached and (now - cached[0]) < _CACHE_TTL:
            return str(cached[1]["thesis"])

        if not self.api_key:
            raise RuntimeError("OPENROUTER_API_KEY env var is required for thesis generation")

        prompt = self._build_prompt(scan_result, resistance_levels, combo_result=combo_result)
        thesis = self._call_openrouter(prompt)
        payload = {
            "ticker": ticker,
            "thesis": thesis,
            "generated_at": now.isoformat(),
        }
        self._CACHE[ticker] = (now, payload)
        return thesis

    def batch_generate(self, high_confidence_results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Generate theses for up to five top plays."""
        rows: List[Dict[str, Any]] = []
        for result in high_confidence_results[:5]:
            ticker = str(result.get("ticker", "")).upper()
            rows.append({"ticker": ticker, "thesis": self.generate(result, resistance_levels=[])} if ticker else {})
        return [row for row in rows if row]

    def _call_openrouter(self, prompt: str) -> str:
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are a concise technical analyst. Write a 3-sentence trade thesis. "
                        "Sentence 1: the setup (what happened). "
                        "Sentence 2: the catalyst (what's changing). "
                        "Sentence 3: the trade (entry, target, risk). No disclaimers."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://quantum-alpha-hunter.local",
            "X-Title": "Quantum Alpha Hunter",
        }

        for attempt in range(2):
            try:
                with httpx.Client(timeout=15.0) as client:
                    response = client.post(_OPENROUTER_URL, headers=headers, json=payload)
                    response.raise_for_status()
                    content = response.json()["choices"][0]["message"]["content"]
                    return self._normalize_thesis(str(content))
            except httpx.HTTPError:
                logger.warning("OpenRouter thesis request failed on attempt %d", attempt + 1, exc_info=True)
                if attempt == 1:
                    raise
        raise RuntimeError("Failed to generate thesis")

    @staticmethod
    def _normalize_thesis(content: str) -> str:
        sentences = [sentence.strip() for sentence in content.replace("\n", " ").split(".") if sentence.strip()]
        normalized = ". ".join(sentences[:3])
        return f"{normalized}." if normalized and not normalized.endswith(".") else normalized

    @staticmethod
    def _build_prompt(
        scan_result: Dict[str, Any],
        resistance_levels: List[Dict[str, Any]],
        combo_result: Optional[Any] = None,
    ) -> str:
        top_signals = sorted(
            (scan_result.get("signal_breakdown") or {}).items(),
            key=lambda item: float(item[1]),
            reverse=True,
        )[:5]
        signal_text = ", ".join(f"{name} ({weight})" for name, weight in top_signals) or "None"
        resistance_text = ", ".join(
            f"{level.get('level')} ({level.get('strength')})"
            for level in resistance_levels[:3]
        ) or "None"

        combo_name = "None"
        combo_hit_rate = None
        trap_warnings = "None"
        if combo_result is not None:
            matched_combos = getattr(combo_result, "matched_combos", None)
            if matched_combos:
                combo_name = str(matched_combos[0].name)
                combo_hit_rate = getattr(matched_combos[0], "hit_rate", None)
            traps = getattr(combo_result, "trap_warnings", None)
            if traps:
                trap_warnings = ", ".join(getattr(trap, "message", str(trap)) for trap in traps)

        combo_text = combo_name if combo_hit_rate is None else f"{combo_name} ({combo_hit_rate:.1%})"
        return (
            f"Ticker: {scan_result.get('ticker')}, Price: ${scan_result.get('price')}, "
            f"Score: {scan_result.get('score')}, Stage: {scan_result.get('stage')}\n"
            f"Signals: {signal_text}\n"
            f"Resistance: {resistance_text}\n"
            f"Combo: {combo_text}\n"
            f"Trap warnings: {trap_warnings}\n"
            f"Exit plan: Stop ${scan_result.get('stop')}, T1 ${scan_result.get('t1')}, "
            f"T2 ${scan_result.get('t2')}, T3 ${scan_result.get('t3')}"
        )

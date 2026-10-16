"""OpenAI-backed extractor, called over the plain REST API (no SDK, so it works on old Pythons).

The key is read from the OPENAI_API_KEY environment variable or a git-ignored `.env` file.
"""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
from typing import Dict, List

import requests

from .claims import JSON_SCHEMA
from .extract import Extractor, render_prompt

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MODEL = "gpt-4o"
URL = "https://api.openai.com/v1/chat/completions"


def load_env(path: Path = ROOT / ".env") -> None:
    """Minimal .env reader: KEY=value lines; real environment variables win."""
    if not Path(path).exists():
        return
    for line in Path(path).read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def api_schema() -> dict:
    """Schema for the API's strict mode, which does not accept `pattern`; code validates quarters."""
    s = copy.deepcopy(JSON_SCHEMA)
    s["properties"]["claims"]["items"]["properties"]["quarter"].pop("pattern", None)
    return s


def openai_extractor(model: str = None, temperature: float = 0.0, timeout: int = 60) -> Extractor:
    load_env()
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        raise RuntimeError("OPENAI_API_KEY not set (put it in .env)")
    model = model or os.environ.get("OPENAI_MODEL", DEFAULT_MODEL)

    def extract(transcript: str) -> List[Dict]:
        resp = requests.post(
            URL, timeout=timeout, headers={"Authorization": f"Bearer {key}"},
            json={"model": model, "temperature": temperature,
                  "messages": [{"role": "user", "content": render_prompt(transcript)}],
                  "response_format": {"type": "json_schema", "json_schema": {
                      "name": "claims", "strict": True, "schema": api_schema()}}})
        if resp.status_code != 200:
            raise RuntimeError(f"OpenAI API error {resp.status_code}: {resp.text[:300]}")
        return json.loads(resp.json()["choices"][0]["message"]["content"])["claims"]

    return extract

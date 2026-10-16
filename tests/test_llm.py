import json

import pytest

from portfolio_agent import llm
from portfolio_agent.extract import STUB_ROWS


class FakeResp:
    status_code = 200

    def __init__(self, rows):
        self._rows = rows

    def json(self):
        return {"choices": [{"message": {"content": json.dumps({"claims": self._rows})}}]}


def test_extractor_posts_schema_and_parses(monkeypatch):
    seen = {}

    def fake_post(url, **kw):
        seen.update(kw)
        return FakeResp(STUB_ROWS)

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(llm.requests, "post", fake_post)
    rows = llm.openai_extractor(model="m", temperature=0)("some transcript")
    assert rows == STUB_ROWS
    assert seen["json"]["response_format"]["json_schema"]["strict"] is True
    assert "some transcript" in seen["json"]["messages"][0]["content"]
    assert seen["headers"]["Authorization"] == "Bearer test-key"


def test_api_schema_drops_pattern_only_in_copy():
    from portfolio_agent.claims import JSON_SCHEMA
    q = lambda s: s["properties"]["claims"]["items"]["properties"]["quarter"]
    assert "pattern" not in q(llm.api_schema()) and "pattern" in q(JSON_SCHEMA)


def test_missing_key_fails(monkeypatch, tmp_path):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(llm, "ROOT", tmp_path)
    monkeypatch.setattr(llm, "load_env", lambda *a, **k: None)
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        llm.openai_extractor()


def test_load_env(tmp_path, monkeypatch):
    f = tmp_path / ".env"
    f.write_text("# c\nFOO_TEST_KEY=abc\nBAR_TEST_KEY='x y'\n")
    monkeypatch.delenv("FOO_TEST_KEY", raising=False)
    monkeypatch.delenv("BAR_TEST_KEY", raising=False)
    llm.load_env(f)
    import os
    assert os.environ["FOO_TEST_KEY"] == "abc" and os.environ["BAR_TEST_KEY"] == "x y"

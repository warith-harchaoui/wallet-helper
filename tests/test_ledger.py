"""Content-addressed ledger — keys, storage, hits, stats.

Author
------
Warith HARCHAOUI — https://linkedin.com/in/warith-harchaoui
"""
from __future__ import annotations

from pathlib import Path

import pytest

from wallet_helper.ledger import Ledger, make_key


@pytest.fixture()
def ledger(tmp_path: Path) -> Ledger:
    return Ledger(tmp_path)


def test_key_is_order_independent() -> None:
    assert make_key("ns", {"a": 1, "b": 2}) == make_key("ns", {"b": 2, "a": 1})


def test_key_separates_namespaces() -> None:
    assert make_key("a", {"x": 1}) != make_key("b", {"x": 1})


def test_key_content_addresses_a_file(tmp_path: Path) -> None:
    f = tmp_path / "clip.raw"
    f.write_bytes(b"same-bytes")
    assert make_key("ns", f) == make_key("ns", b"same-bytes")  # file == its bytes


def test_put_get_roundtrip_preserves_json(ledger: Ledger) -> None:
    payload = {"utterances": [{"speaker": "0", "text": "café ☕"}], "n": [1, 2]}
    key = make_key("gladia", {"file": "a.wav"})
    ledger.put(key, payload, cost=0.75, currency="USD")
    assert ledger.has(key) and ledger.get(key) == payload


def test_stats_track_spend_and_savings(ledger: Ledger) -> None:
    key = make_key("gladia", {"file": "a.wav"})
    ledger.put(key, {"ok": True}, cost=0.75, currency="USD")
    ledger.register_hit(key)
    ledger.register_hit(key)  # reused twice → saved 2 × 0.75
    s = ledger.stats()
    assert s["entries"] == 1 and s["hits"] == 2
    assert round(s["spent"], 2) == 0.75
    assert round(s["saved"], 2) == 1.50
    assert round(s["by_currency"]["USD"]["saved"], 2) == 1.50


def test_missing_key_returns_none(ledger: Ledger) -> None:
    assert ledger.get("absent") is None and ledger.get_record("absent") is None

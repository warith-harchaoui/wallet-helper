"""Content-addressed ledger: keys, storage, hits, stats, namespaces.

Author
------
Warith HARCHAOUI, https://linkedin.com/in/warith-harchaoui
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
    a = tmp_path / "clip.raw"
    a.write_bytes(b"same-bytes")
    b = tmp_path / "renamed.raw"
    b.write_bytes(b"same-bytes")
    # Same content hits after a rename; ascii bytes hash like the file holding them.
    assert make_key("ns", a) == make_key("ns", b)
    assert make_key("ns", a) == make_key("ns", b"same-bytes")


def test_put_get_roundtrip_preserves_json(ledger: Ledger) -> None:
    payload = {"utterances": [{"speaker": "0", "text": "cafe"}], "n": [1, 2]}
    key = make_key("asr", {"file": "a.wav"})
    ledger.put(key, payload)
    assert ledger.has(key) and ledger.get(key) == payload


def test_stats_count_entries_and_saved_calls(ledger: Ledger) -> None:
    key = make_key("asr", {"file": "a.wav"})
    ledger.put(key, {"ok": True})
    ledger.register_hit(key)
    ledger.register_hit(key)  # reused twice, so two calls were saved
    s = ledger.stats()
    assert s == {"entries": 1, "hits": 2}


def test_stats_and_clear_scope_to_a_namespace(ledger: Ledger) -> None:
    ledger.put(make_key("a", {"x": 1}), 1)
    ledger.put(make_key("b", {"x": 1}), 2)
    assert ledger.stats("a")["entries"] == 1
    ledger.clear("a")
    assert ledger.stats("a")["entries"] == 0
    assert ledger.stats("b")["entries"] == 1  # other namespace untouched


def test_missing_key_returns_none(ledger: Ledger) -> None:
    assert ledger.get("absent") is None and ledger.get_record("absent") is None

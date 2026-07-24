"""Content-addressed ledger: keys, storage, hits, stats, namespaces.

Author
------
Warith HARCHAOUI, https://linkedin.com/in/warith-harchaoui
"""
from __future__ import annotations

import threading
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


def test_key_content_addresses_a_nested_file(tmp_path: Path) -> None:
    # A path is usually one argument among several, not the whole payload.
    a = tmp_path / "here" / "clip.raw"
    a.parent.mkdir()
    a.write_bytes(b"same-bytes")
    b = tmp_path / "there" / "other-name.raw"
    b.parent.mkdir()
    b.write_bytes(b"same-bytes")
    payload_a = {"args": (str(a),), "kwargs": {"lang": "fr"}}
    payload_b = {"args": (str(b),), "kwargs": {"lang": "fr"}}
    # Identical files reached by different paths share one entry.
    assert make_key("asr", payload_a) == make_key("asr", payload_b)


def test_key_separates_nested_files_by_content(tmp_path: Path) -> None:
    a = tmp_path / "a.raw"
    a.write_bytes(b"alpha")
    b = tmp_path / "b.raw"
    b.write_bytes(b"beta")
    ka = make_key("asr", {"args": (str(a),), "kwargs": {}})
    kb = make_key("asr", {"args": (str(b),), "kwargs": {}})
    assert ka != kb


def test_nested_path_accepts_pathlike(tmp_path: Path) -> None:
    f = tmp_path / "clip.raw"
    f.write_bytes(b"same-bytes")
    # A path can arrive as a str or as any os.PathLike; both key the same file.
    as_str = make_key("asr", {"args": (str(f),), "kwargs": {}})
    as_path = make_key("asr", {"args": (f,), "kwargs": {}})
    assert as_str == as_path


def test_non_file_string_is_not_content_addressed(tmp_path: Path) -> None:
    # A plain string that is not a file must key by its text, not be mistaken
    # for a path, so two different non-file strings stay distinct.
    k1 = make_key("ns", {"args": ("hello.raw",), "kwargs": {}})
    k2 = make_key("ns", {"args": ("world.raw",), "kwargs": {}})
    assert k1 != k2


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


def test_concurrent_hits_are_not_lost(ledger: Ledger) -> None:
    # The hit counter is a locked read-modify-write, so parallel increments from
    # several threads all land instead of clobbering each other.
    ledger.put("ns_k", "v")

    def bump() -> None:
        for _ in range(50):
            ledger.register_hit("ns_k")

    threads = [threading.Thread(target=bump) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert ledger.stats()["hits"] == 200


def test_max_entries_auto_evicts(tmp_path: Path) -> None:
    ledger = Ledger(tmp_path, max_entries=2)
    ledger.put("ns_a", 1)
    ledger.put("ns_b", 2)
    ledger.put("ns_c", 3)
    assert ledger.stats()["entries"] == 2  # each put keeps the store within the cap

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
    # Same content hits after a rename, whatever the path.
    assert make_key("ns", a) == make_key("ns", b)


def test_file_and_raw_bytes_are_distinct_key_spaces(tmp_path: Path) -> None:
    a = tmp_path / "clip.raw"
    a.write_bytes(b"same-bytes")
    # A file path and equal raw bytes are different kinds of argument, so they key
    # differently and never alias, consistently for text and binary content alike.
    assert make_key("ns", a) != make_key("ns", b"same-bytes")


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


def test_forged_marker_string_does_not_collide_with_a_file(tmp_path: Path) -> None:
    # A crafted argument equal to a file marker must not alias a real file's key.
    import os_helper as osh

    from wallet_helper.ledger import _FILE_MARK

    f = tmp_path / "clip.raw"
    f.write_bytes(b"payload")
    forged = _FILE_MARK + osh.hashfile(str(f))  # looks exactly like the marker
    real = make_key("ns", {"args": (str(f),), "kwargs": {}})
    crafted = make_key("ns", {"args": (forged,), "kwargs": {}})
    assert real != crafted


def test_pathlike_that_raises_is_treated_as_not_a_file(tmp_path: Path) -> None:
    class Angry:
        def __fspath__(self) -> str:
            raise RuntimeError("no path for you")

        def __repr__(self) -> str:
            return "Angry()"  # content-bearing, so it keys by value not address

    # A misbehaving os.PathLike must not crash key construction; it falls through
    # to normal keying via its repr instead of propagating the __fspath__ error.
    angry = Angry()
    k1 = make_key("ns", {"args": (angry,), "kwargs": {}})
    k2 = make_key("ns", {"args": (angry,), "kwargs": {}})
    assert isinstance(k1, str) and k1 == k2  # no exception, stable


def test_file_inside_a_set_is_content_addressed(tmp_path: Path) -> None:
    a = tmp_path / "one" / "clip.raw"
    a.parent.mkdir()
    a.write_bytes(b"same-bytes")
    b = tmp_path / "two" / "other.raw"
    b.parent.mkdir()
    b.write_bytes(b"same-bytes")
    ka = make_key("ns", {"args": (frozenset({str(a), "tag"}),), "kwargs": {}})
    kb = make_key("ns", {"args": (frozenset({str(b), "tag"}),), "kwargs": {}})
    assert ka == kb  # identical file content, different path, inside a set


def test_opaque_object_is_keyed_by_state_not_address() -> None:
    class Handle:  # only the default object repr: <...Handle object at 0x...>
        def __init__(self, x: int) -> None:
            self.x = x

    # Keying on the address would never hit across processes; we key on the
    # object's state instead, so equal state hits and different state does not.
    same1 = make_key("ns", {"args": (Handle(5),), "kwargs": {}})
    same2 = make_key("ns", {"args": (Handle(5),), "kwargs": {}})
    other = make_key("ns", {"args": (Handle(6),), "kwargs": {}})
    assert same1 == same2  # deterministic, distinct instances of equal state
    assert same1 != other  # different state, different key


def test_opaque_object_state_includes_inherited_slots() -> None:
    class Base:
        __slots__ = ("a",)

    class Child(Base):  # Child.__slots__ only lists "b"; "a" comes from Base
        __slots__ = ("b",)

    c1 = Child()
    c1.a, c1.b = 1, 2
    c2 = Child()
    c2.a, c2.b = 999, 2  # differs only in the inherited slot "a"

    k1 = make_key("ns", {"args": (c1,), "kwargs": {}})
    k2 = make_key("ns", {"args": (c2,), "kwargs": {}})
    # Reading only type(value).__slots__ would miss "a" and collide the two.
    assert k1 != k2


def test_function_argument_keys_by_identity_not_address() -> None:
    def transform(x: int) -> int:
        return x

    def other(x: int) -> int:
        return x

    # A callback passed as an argument keys by its (module, qualname), so it dedups
    # rather than keying on the address in its repr, and distinct functions differ.
    k1 = make_key("ns", {"args": (transform,), "kwargs": {}})
    k2 = make_key("ns", {"args": (transform,), "kwargs": {}})
    assert k1 == k2
    assert k1 != make_key("ns", {"args": (other,), "kwargs": {}})
    assert k1 != make_key("ns", {"args": (len,), "kwargs": {}})  # a builtin too


def test_functools_partial_keys_structurally() -> None:
    import functools

    def base(a: int, b: int) -> int:
        return a + b

    p1 = functools.partial(base, 1)
    p2 = functools.partial(base, 1)
    # A partial keys by its wrapped function plus bound args, deterministically,
    # not by the address in its repr.
    assert make_key("ns", {"args": (p1,), "kwargs": {}}) == make_key("ns", {"args": (p2,), "kwargs": {}})
    assert make_key("ns", {"args": (p1,), "kwargs": {}}) != make_key(
        "ns", {"args": (functools.partial(base, 2),), "kwargs": {}}
    )


def test_cyclic_object_graph_does_not_crash() -> None:
    class Node:
        pass

    n = Node()
    n.self = n  # a self-referential graph must not blow the stack
    k1 = make_key("ns", {"args": (n,), "kwargs": {}})
    k2 = make_key("ns", {"args": (n,), "kwargs": {}})
    assert isinstance(k1, str) and k1 == k2

    a, b = Node(), Node()
    a.other, b.other = b, a  # indirect cycle
    assert isinstance(make_key("ns", {"args": (a,), "kwargs": {}}), str)


def test_cyclic_graphs_with_different_back_edges_do_not_collide() -> None:
    # Two graphs identical except for which ancestor the back-edge targets must
    # not share a key (the cycle marker records the target's depth).
    x: dict = {}
    x["child"] = {"up": x}  # inner.up -> the root
    y: dict = {}
    inner: dict = {}
    inner["up"] = inner  # inner.up -> itself
    y["child"] = inner
    assert make_key("ns", x) != make_key("ns", y)


def test_getattr_raising_non_attributeerror_does_not_crash() -> None:
    class Hostile:
        def __getattr__(self, name: str) -> object:
            raise ValueError(f"boom {name}")

    # A __getattr__ that raises something other than AttributeError must not
    # propagate out of key construction.
    k = make_key("ns", {"args": (Hostile(),), "kwargs": {}})
    assert isinstance(k, str)


def test_stateless_opaque_objects_of_a_type_share_a_key() -> None:
    class Marker:  # no attributes to distinguish instances
        pass

    # With no distinguishing state, two instances are content-equivalent, so they
    # deterministically share one key rather than leaking two addresses.
    k1 = make_key("ns", {"args": (Marker(),), "kwargs": {}})
    k2 = make_key("ns", {"args": (Marker(),), "kwargs": {}})
    assert k1 == k2


def test_opaque_object_state_content_addresses_a_nested_file(tmp_path: Path) -> None:
    a = tmp_path / "one" / "clip.raw"
    a.parent.mkdir()
    a.write_bytes(b"same-bytes")
    b = tmp_path / "two" / "other.raw"
    b.parent.mkdir()
    b.write_bytes(b"same-bytes")

    class Job:
        def __init__(self, path: str) -> None:
            self.path = path

    # A file path held in an object's state is content-addressed like any other.
    assert make_key("ns", {"args": (Job(str(a)),), "kwargs": {}}) == make_key(
        "ns", {"args": (Job(str(b)),), "kwargs": {}}
    )


def test_object_with_a_content_repr_keys_stably() -> None:
    class Point:
        def __init__(self, x: int) -> None:
            self.x = x

        def __repr__(self) -> str:
            return f"Point({self.x})"

    k1 = make_key("ns", {"args": (Point(3),), "kwargs": {}})
    k2 = make_key("ns", {"args": (Point(3),), "kwargs": {}})
    assert k1 == k2  # stable, content-bearing repr
    assert k1 != make_key("ns", {"args": (Point(4),), "kwargs": {}})


def test_non_string_dict_keys_do_not_crash_and_stay_distinct() -> None:
    # Tuple, bytes, and mixed int/str keys would make json.dumps raise or fail to
    # sort; key construction must handle them deterministically instead.
    make_key("ns", {"args": ({(1, 2): "v"},), "kwargs": {}})
    make_key("ns", {"args": ({b"k": "v"},), "kwargs": {}})
    k1 = make_key("ns", {"args": ({1: "a", "b": 2},), "kwargs": {}})
    k2 = make_key("ns", {"args": ({1: "a", "b": 2},), "kwargs": {}})
    assert k1 == k2  # deterministic
    # An int key and a string key of the same text do not alias.
    assert make_key("ns", {1: "v"}) != make_key("ns", {"1": "v"})


def test_byte_like_types_are_content_addressed_and_stable() -> None:
    # bytes, bytearray, and memoryview of the same content key identically and
    # deterministically (no repr-with-address leaking into the key).
    kb = make_key("ns", {"args": (b"abc",), "kwargs": {}})
    kba = make_key("ns", {"args": (bytearray(b"abc"),), "kwargs": {}})
    kmv = make_key("ns", {"args": (memoryview(b"abc"),), "kwargs": {}})
    assert kb == kba == kmv


def test_set_and_list_with_equal_members_stay_distinct() -> None:
    # A set argument and a list argument are different kinds of value; they must
    # not share a cache entry even when their members coincide.
    as_set = make_key("ns", {"args": (frozenset({1, 2}),), "kwargs": {}})
    as_list = make_key("ns", {"args": ([1, 2],), "kwargs": {}})
    assert as_set != as_list


def test_set_is_order_independent() -> None:
    # Same members in a different insertion order hash the same.
    k1 = make_key("ns", {"args": (frozenset({"a", "b", "c"}),), "kwargs": {}})
    k2 = make_key("ns", {"args": (frozenset({"c", "a", "b"}),), "kwargs": {}})
    assert k1 == k2


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


def test_namespace_glob_metacharacters_do_not_leak_across_namespaces(ledger: Ledger) -> None:
    # "a*b" is a literal namespace name, not a glob pattern. Unescaped, it would
    # also match keys under an unrelated namespace like "axxxb".
    ledger.put("a_1", 1)
    ledger.put("axxxb_2", 2)
    assert ledger.stats("a*b") == {"entries": 0, "hits": 0}
    ledger.clear("a*b")
    assert ledger.stats("a")["entries"] == 1 and ledger.stats("axxxb")["entries"] == 1


def test_json_store_filename_is_windows_safe(tmp_path: Path) -> None:
    # A default namespace is module.qualname; for a nested function or a lambda
    # that contains "<locals>" / "<lambda>", and "<" ">" (plus : " / \ | ? *)
    # are illegal in a Windows filename, which used to crash Ledger.put there.
    # The round-trip must work and the on-disk name must carry none of them.
    # OS-independent: it asserts on the filename, so it guards the Windows path
    # even when the suite runs on POSIX (where those characters happen to be legal).
    ledger = Ledger(tmp_path)
    key = make_key("mod.outer.<locals>.inner:weird*name?", {"x": 1})
    ledger.put(key, "v")
    assert ledger.get(key) == "v"  # round-trips despite the forbidden characters
    forbidden = set('<>:"/\\|?*')
    on_disk = [p.name for p in tmp_path.glob("*.json")]
    assert len(on_disk) == 1
    assert not (forbidden & set(on_disk[0])), on_disk[0]


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


def test_hit_counter_survives_without_fcntl(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # The Windows path: no fcntl, so the cross-process advisory lock is skipped
    # and only the in-process threading lock guards register_hit. Simulate it on
    # any OS by blanking fcntl, and confirm concurrent hits from several threads
    # still all land (the in-process guarantee holds even without fcntl).
    import wallet_helper.ledger as ledger_module

    monkeypatch.setattr(ledger_module, "fcntl", None)
    ledger = Ledger(tmp_path)
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

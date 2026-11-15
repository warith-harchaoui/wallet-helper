"""on_repeat="refuse": an identical call within the ttl is blocked, not served.

The use case: a paid call (the same prompt to the same model) must never be
paid twice within a window, yet the same call after the window is a new,
legitimate measurement and runs again.

Author
------
Warith HARCHAOUI, https://linkedin.com/in/warith-harchaoui
"""

from __future__ import annotations

import asyncio
import threading
import time
from pathlib import Path

import pytest

from wallet_helper import AlreadyPaid, memoize
from wallet_helper.guard import Wallet
from wallet_helper.ledger import Ledger
from wallet_helper.sqlite_ledger import SqliteLedger


def _counter():
    runs = {"n": 0}

    def heavy() -> str:
        runs["n"] += 1
        return f"answer {runs['n']}"

    return runs, heavy


@pytest.mark.parametrize("backend", ["json", "sqlite"])
def test_refused_within_ttl_then_allowed_after(tmp_path: Path, backend: str) -> None:
    ledger = Ledger(tmp_path) if backend == "json" else SqliteLedger(tmp_path / "ledger.db")
    wallet = Wallet(ledger)
    runs, heavy = _counter()

    value, hit = wallet.call("llm", {"prompt": "p"}, heavy, ttl=0.2, on_repeat="refuse")
    assert (value, hit, runs["n"]) == ("answer 1", False, 1)

    with pytest.raises(AlreadyPaid) as caught:
        wallet.call("llm", {"prompt": "p"}, heavy, ttl=0.2, on_repeat="refuse")
    assert runs["n"] == 1  # nothing ran, nothing was paid
    assert caught.value.paid_at is not None and caught.value.allowed_after > caught.value.paid_at

    time.sleep(0.25)  # the window has passed: the same call is a new one
    value, hit = wallet.call("llm", {"prompt": "p"}, heavy, ttl=0.2, on_repeat="refuse")
    assert (value, hit, runs["n"]) == ("answer 2", False, 2)


def test_a_different_call_is_never_refused(tmp_path: Path) -> None:
    wallet = Wallet(Ledger(tmp_path))
    runs, heavy = _counter()
    wallet.call("llm", {"prompt": "p", "replicate": 1}, heavy, ttl=60, on_repeat="refuse")
    wallet.call("llm", {"prompt": "p", "replicate": 2}, heavy, ttl=60, on_repeat="refuse")
    wallet.call("other-llm", {"prompt": "p", "replicate": 1}, heavy, ttl=60, on_repeat="refuse")
    assert runs["n"] == 3


def test_a_failed_call_is_not_counted_as_paid(tmp_path: Path) -> None:
    wallet = Wallet(Ledger(tmp_path))

    def broken() -> str:
        raise ConnectionError("network down")

    with pytest.raises(ConnectionError):
        wallet.call("llm", {"prompt": "p"}, broken, ttl=60, on_repeat="refuse")
    runs, heavy = _counter()
    assert wallet.call("llm", {"prompt": "p"}, heavy, ttl=60, on_repeat="refuse")[0] == "answer 1"


def test_serve_stays_the_default(tmp_path: Path) -> None:
    wallet = Wallet(Ledger(tmp_path))
    runs, heavy = _counter()
    wallet.call("llm", {"prompt": "p"}, heavy, ttl=60)
    assert wallet.call("llm", {"prompt": "p"}, heavy, ttl=60) == ("answer 1", True)
    assert runs["n"] == 1


def test_concurrent_repeat_is_refused_too(tmp_path: Path) -> None:
    wallet = Wallet(Ledger(tmp_path))
    started, release = threading.Event(), threading.Event()

    def slow() -> str:
        started.set()
        release.wait(2)
        return "paid once"

    outcome: dict = {}

    def second() -> None:
        started.wait(2)
        try:
            outcome["value"] = wallet.call("llm", {"prompt": "p"}, slow, ttl=60, on_repeat="refuse")
        except AlreadyPaid as e:
            outcome["refused"] = e

    t = threading.Thread(target=second)
    t.start()
    first = threading.Thread(target=lambda: wallet.call("llm", {"prompt": "p"}, slow, ttl=60, on_repeat="refuse"))
    first.start()
    time.sleep(0.1)
    release.set()
    first.join(3)
    t.join(3)
    assert "refused" in outcome and "value" not in outcome


def test_decorator_and_async(tmp_path: Path) -> None:
    wallet = Wallet(Ledger(tmp_path))

    @memoize(wallet=wallet, ttl=60, on_repeat="refuse")
    def ask(prompt: str) -> str:
        return prompt.upper()

    assert ask("p") == "P"
    with pytest.raises(AlreadyPaid):
        ask("p")

    @wallet.paid("async-llm", ttl=60, on_repeat="refuse")
    async def aask(prompt: str) -> str:
        return prompt * 2

    assert asyncio.run(aask("p")) == "pp"
    with pytest.raises(AlreadyPaid):
        asyncio.run(aask("p"))


def test_bad_on_repeat_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        Wallet(Ledger(tmp_path)).call("llm", {}, lambda: 1, on_repeat="skip")


@pytest.mark.parametrize("backend", ["json", "sqlite"])
def test_a_call_recorded_after_the_fact_keeps_its_real_date(tmp_path: Path, backend: str) -> None:
    from wallet_helper.ledger import make_key

    ledger = Ledger(tmp_path) if backend == "json" else SqliteLedger(tmp_path / "ledger.db")
    wallet = Wallet(ledger)
    paid = time.time() - 3600  # paid an hour ago, recorded now
    ledger.put(make_key("llm", {"prompt": "p"}), "old answer", ttl=7200, created_at=paid)
    with pytest.raises(AlreadyPaid) as caught:
        wallet.call("llm", {"prompt": "p"}, lambda: "new", ttl=7200, on_repeat="refuse")
    assert caught.value.paid_at == pytest.approx(paid)
    assert caught.value.allowed_after == pytest.approx(paid + 7200)

    ledger.put(make_key("llm", {"prompt": "q"}), "old answer", ttl=60, created_at=time.time() - 120)
    assert wallet.call("llm", {"prompt": "q"}, lambda: "new", ttl=60, on_repeat="refuse") == ("new", False)

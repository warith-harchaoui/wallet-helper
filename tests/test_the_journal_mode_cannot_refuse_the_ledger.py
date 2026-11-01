"""
A journal mode is an optimisation. It was a reason the ledger would not open.

The defect, measured
--------------------
``SqliteLedger.__init__`` ran ``PRAGMA journal_mode=WAL`` and let the statement
speak for the whole constructor. Going into WAL needs exclusive access to the
database file, and SQLite answers a journal-mode change with ``SQLITE_BUSY``
**without consulting the busy handler** — so the thirty-second timeout that
``_connect`` sets, the one whose docstring says "the timeout makes writers
wait, not fail", is true of every other statement and false of that one.

Three processes opening a cold ledger in the same instant is exactly that case,
and it is the case this library exists for: the cross-process single-flight.
Found from the outside, in ``sprezzature-accessibility``, whose test about
three callers sharing one model call died with
``sqlite3.OperationalError: database is locked`` on that line in roughly one
run in three — measured, 5 out of 15 before this change. The ledger meant to
stop three processes duplicating work was the reason one of them crashed.

Why the race is injected and not raced
--------------------------------------
Three shapes of real contention were tried first and none reproduced it: three
simultaneous constructors, a writer holding ``BEGIN EXCLUSIVE``, and a reader
holding a shared lock. All three waited politely, because the busy handler
*does* apply to ordinary lock waits. Whatever window the real failure lands in
is narrower than a test can aim at, so the error is injected at the one place
it was observed — which also makes the test deterministic, and a race test
that passes by luck is worth less than no test.

``tests/test_multiprocess.py`` still covers the real concurrency; this file
covers the one statement that did not honour it.

Author
------
Warith HARCHAOUI <warithmetics@deraison.ai>
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from wallet_helper.sqlite_ledger import SqliteLedger


class _BusyOnJournalMode:
    """A connection whose journal-mode *change* is always busy.

    Reads of ``PRAGMA journal_mode`` pass through, because the fix depends on
    being able to ask; only the assignment is refused. That is the real
    asymmetry: the query takes no lock, the change needs the file to itself.
    """

    def __init__(self, conn: sqlite3.Connection, refusals: int | None = None) -> None:
        self._conn = conn
        self._left = refusals  # None = refuse for ever
        self.attempts = 0

    def execute(self, sql: str, *args, **kwargs):
        if sql.strip().lower().startswith("pragma journal_mode=") or sql.strip().lower().startswith(
            "pragma journal_mode ="
        ):
            self.attempts += 1
            if self._left is None or self._left > 0:
                if self._left is not None:
                    self._left -= 1
                raise sqlite3.OperationalError("database is locked")
        return self._conn.execute(sql, *args, **kwargs)

    def __getattr__(self, name: str):
        return getattr(self._conn, name)


def _wrap(monkeypatch: pytest.MonkeyPatch, refusals: int | None):
    """Make every connection this ledger opens refuse the journal-mode change."""
    real = SqliteLedger._connect
    made: list[_BusyOnJournalMode] = []

    def _connect(self):
        wrapper = _BusyOnJournalMode(real(self), refusals)
        made.append(wrapper)
        return wrapper

    monkeypatch.setattr(SqliteLedger, "_connect", _connect)
    return made


def test_a_refused_journal_mode_still_opens_a_working_ledger(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The constructor survives, and the ledger it hands back works.

    This is the assertion the defect needed. Before the change the constructor
    propagated the ``OperationalError`` and the caller got no ledger at all —
    which, in the package that found this, meant a crashed subprocess rather
    than a slower one.
    """
    made = _wrap(monkeypatch, refusals=None)

    ledger = SqliteLedger(tmp_path / "ledger.db", max_entries=8)

    assert made and made[0].attempts == len(SqliteLedger._WAL_BACKOFF), (
        f"the change was attempted {made[0].attempts if made else 0} times, and the "
        f"backoff ladder has {len(SqliteLedger._WAL_BACKOFF)} rungs — a fix that gives "
        f"up on the first refusal loses the race it was written to win"
    )
    assert getattr(ledger, "journal_mode", "wal") != "wal", (
        "the ledger reports WAL after every attempt was refused, so it is reporting an intention rather than a fact"
    )

    # And it is a *ledger*, not a husk: the whole contract still holds.
    ledger.put("demo", {"ok": True})
    assert ledger.get("demo") == {"ok": True}
    assert ledger.has("demo")
    assert ledger.get_record("demo")["result"] == {"ok": True}


def test_a_transient_refusal_still_reaches_wal(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """One loss of the race is not a loss of WAL.

    The real shape: the winner is mid-change, this process is refused, and a
    moment later the mode has taken. Retrying has to actually reach it, or the
    fix trades a crash for a permanent downgrade to the rollback journal — and
    nothing would ever report that.
    """
    made = _wrap(monkeypatch, refusals=2)

    ledger = SqliteLedger(tmp_path / "ledger.db", max_entries=8)

    assert made[0].attempts == 3, f"expected two refusals then a success, got {made[0].attempts}"
    with sqlite3.connect(ledger.path) as conn:
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    assert str(mode).lower() == "wal", f"the ledger settled for {mode!r} after a transient refusal"
    assert not hasattr(ledger, "journal_mode"), (
        "the fallback attribute is set even though WAL was reached, so a caller "
        "reading it would think the optimisation is off"
    )


def test_an_already_wal_database_is_not_asked_to_change(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The half of the fix that removes the race rather than surviving it.

    The mode is persistent in the file, so every process after the first reads
    ``wal`` and must not attempt the change at all. Without this the ladder
    above would be load-bearing on every single open; with it, the contended
    statement runs once in the life of the database.
    """
    db = tmp_path / "ledger.db"
    SqliteLedger(db, max_entries=8)  # the first arrival sets WAL for good

    made = _wrap(monkeypatch, refusals=None)
    second = SqliteLedger(db, max_entries=8)

    assert made[0].attempts == 0, (
        f"the second open attempted the journal-mode change {made[0].attempts} time(s) "
        f"on a database already in WAL — the read-first branch is not being taken, so "
        f"every process pays for the contended statement"
    )
    second.put("k", 1)
    assert second.get("k") == 1

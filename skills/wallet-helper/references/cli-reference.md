# wallet-helper CLI reference

One CLI, `wallet-helper`, built with click and shipped with the core package,
over four commands.

The CLI's job is **inspecting and pruning** the store. Memoization itself
happens in the library.

Two group options choose the store, and go **before** the subcommand:
`--dir PATH` for a JSON ledger directory (default: `$WALLET_HELPER_DIR`, else
`~/.cache/wallet-helper`), or `--sqlite FILE` for a SQLite ledger. `-V`
prints the version.

## `path` — where the store lives

```bash
wallet-helper [--dir PATH | --sqlite FILE] path
```

Prints the resolved store location. Run it before anything destructive, so
you and the user are talking about the same directory.

## `stats` — what is in it

```bash
wallet-helper [--dir PATH | --sqlite FILE] stats
```

The ledger's location, its entry count and the calls saved (cache hits). This is the call that
answers "is the cache even being used" and "is it worth evicting".

## `clear` — drop everything

```bash
wallet-helper [--dir PATH | --sqlite FILE] clear [--yes]
```

Asks for confirmation unless `--yes`. **Destructive and total.** Run `stats`
first, tell the user how many entries will go, and get a yes — especially for a store you did not
create in this session.

## `evict` — prune by policy

```bash
wallet-helper [--dir PATH | --sqlite FILE] evict [--older-than SECONDS] [--max-entries N]
```

Removes the entries a policy selects and keeps the rest. Prefer it to `clear`
whenever the goal is "reclaim space", not "start over".

`max_entries` also exists as an automatic cap configured on the ledger
(`Ledger(max_entries=…)`, `SqliteLedger(path, max_entries=…)`), so a
long-running process prunes as it goes.

## The key model

An entry's key is a hash of:

- the **namespace** (the logical function), plus
- the **inputs** — arguments, a file's content, or raw bytes.

Consequences worth knowing:

- Renaming an input file does **not** miss: the content is what is hashed.
- Two different inputs never collide.
- Changing the function's implementation does **not** invalidate the key —
  bump the namespace when the semantics change, or the old results stay valid
  forever.

## Lease mechanics (cross-process single-flight)

With `SqliteLedger` or the HTTP server, the first caller takes a **lease** on
a key and the others wait:

- **Fencing token** — each lease carries a unique random value. If a leader
  stalls and a new one takes over, the old token no longer matches, so a late
  write from the stale leader is rejected rather than overwriting the fresh
  result.
- **Lease timeout** — a dead leader never blocks waiters forever.
- **Heartbeat** — a long job keeps its lease alive while it runs.

Duplicates coalesce as long as the leader finishes within its lease or keeps
heart-beating. A leader that dies silently costs one lease timeout, not a
deadlock.

## Output contract

- `path` prints a single path.
- `stats` prints three human-readable lines (ledger, entries, cache hits).
- `clear` prints `cleared <location>`; `evict` prints how many entries it
  removed.
- A failure prints `Error: …` on stderr and exits non-zero.

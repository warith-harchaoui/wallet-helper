# wallet-helper as an agent skill

`skills/wallet-helper/` packages `wallet-helper` as a **Claude Skill** *and* an **OpenCode
skill** — both ecosystems read the same `SKILL.md` (YAML frontmatter + Markdown
body + progressive-disclosure `references/`). Installing it lets an agent
discover wallet-helper and memoize expensive work, inspect the cache, and coordinate workers on the user's behalf, without the user opening a
terminal.

## Layout

```
skills/wallet-helper/
├── SKILL.md                  # name + trigger-rich description + instructions
└── references/
    ├── cli-reference.md      # full subcommand + flag matrix, output contract
    ├── surfaces.md           # library, two CLIs, HTTP API, MCP
    └── triggers.md           # exhaustive, auditable trigger catalogue
```

Progressive disclosure, as the published skill standard prescribes: the YAML
frontmatter is always in the host model's context, `SKILL.md`'s body loads only
when the skill looks relevant, and `references/*.md` load only when a task
actually needs that depth. The `description` stays under the 1024-character cap;
the exhaustive trigger list lives in `references/triggers.md`.

## Install for Claude Code / Claude Desktop

Skills live under `~/.claude/skills/` (user) or `.claude/skills/` (project). To
track this repo's copy rather than duplicate it, symlink it:

```bash
ln -sfn "$PWD/skills/wallet-helper" ~/.claude/skills/wallet-helper
# per-project instead:
mkdir -p /path/to/project/.claude/skills
ln -sfn "$PWD/skills/wallet-helper" /path/to/project/.claude/skills/wallet-helper
```

## Install for OpenCode

OpenCode reads skills from `~/.opencode/skills/` (or `~/.config/opencode/skills/`):

```bash
mkdir -p ~/.opencode/skills
ln -sfn "$PWD/skills/wallet-helper" ~/.opencode/skills/wallet-helper
```

## Keeping triggers enforced

The host model only sees `SKILL.md`'s `description` before deciding to load the
skill, so every real trigger must be represented there — compressed into the
1024-character budget. `references/triggers.md` is the human-reviewable
superset. When one changes, change the other.

No secrets live in this skill. wallet-helper is a local SQLite ledger under the
user's cache directory; nothing is uploaded. The optional `RemoteLedger` talks
only to the HTTP endpoint the user points it at.

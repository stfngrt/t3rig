# Development

Requires [uv](https://docs.astral.sh/uv/).

```sh
uv run t3rig --version
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

## Building these docs

The docs dependencies are in the `docs` dependency group, which `uv run` installs by default.

```sh
uv run sphinx-build -W -b html docs docs/_build/html
```

Warnings fail the build. The CLI reference is generated from `t3rig.cli.build_parser`, so it needs
no manual updates. The site is deployed to GitHub Pages from `main`.

## The self rig

`rigs/self` develops t3rig with t3rig, as four seats. The {term}`project manager` (`dev.pm`) works
with the {term}`operator` and writes specs and {term}`tickets <ticket>` as GitHub issues, labelled
{term}`needs-approval`. When the operator adds {term}`rig-queue`, `dev.lead` takes the issue and
hands it to `dev.impl` and `dev.review`. The issue tracker is the interface between `dev.pm` and
`dev.lead`, so there is no {term}`edge` between them. That also means {term}`watch` pings nobody
about `dev.pm`, and its stuck or approval alerts print only on the `watch` console.

The seats use skills from [Matt Pocock's set](https://github.com/mattpocock/skills) (MIT), vendored
under `rigs/self/agents/*/skills/` with a `CHANGES.md` listing each change. `docs/agents/` holds the
tracker and label docs they read.

- **Shared install:** until per-seat skills land (#7), the skills install into the shared checkout.
  Every seat, and the operator's own Claude sessions in this checkout, sees all of them. Where a skill
  had `disable-model-invocation: true`, it was removed so that seats can call it, so those skills can
  also be invoked automatically.
- **Not taken, `implement-spec`:** it works on an integration branch, with a worktree per ticket and
  a PR. That conflicts with the shared checkout, with "`dev.impl` doesn't commit", and with the rig
  committing to `main` until pull requests land (#9).
- **Not taken, `triage`:** its state machine would add labels (`needs-triage`, `ready-for-agent`,
  `wontfix`) and an `.out-of-scope/` folder that this rig doesn't use. The labels are mapped in
  `docs/agents/triage-labels.md` instead; `wontfix` is used only when closing an issue.

### Seat memory

The seats run Claude Code in the same project path as the operator's own session, so they share
one auto memory folder (`~/.claude/projects/<project>/memory/`) and load the operator's notes at
startup. The folder is derived from the git repository, so "all worktrees and subdirectories within
the same repo share one auto memory directory", and it is machine-local
([memory](https://code.claude.com/docs/en/memory)).

What the Claude Code docs offer for turning it off or moving it:

- `autoMemoryEnabled: false` in settings, or the `/memory` toggle, which saves it to user settings.
  The memory page shows it in a project's settings too, and the settings reference lists
  `autoMemoryEnabled` and `autoMemoryDirectory` as settable in any settings file (user, project,
  local or managed) ([memory](https://code.claude.com/docs/en/memory),
  [settings](https://code.claude.com/docs/en/settings-reference)).
- `CLAUDE_CODE_DISABLE_AUTO_MEMORY=1` in the environment ([memory](https://code.claude.com/docs/en/memory)).
- `autoMemoryDirectory` to store it elsewhere, read from any settings scope "or `--settings`"
  ([memory](https://code.claude.com/docs/en/memory)). `--settings` is "a path to a settings JSON file or an
  inline JSON string" whose values "override the same keys in your `settings.json` files for this
  session" ([CLI reference](https://code.claude.com/docs/en/cli-reference)); it is the per-session
  route, and T3 can't pass it.
- `--bare` and `--safe-mode` also skip auto memory, but with CLAUDE.md, skills and more, which seats
  need ([CLI reference](https://code.claude.com/docs/en/cli-reference)).
- `CLAUDE_CONFIG_DIR` moves the configuration directory, and with `CLAUDE_CODE_PROJECT_DIR_NAME`
  chooses where transcripts and auto memory go ([env vars](https://code.claude.com/docs/en/env-vars)).

The per-session switches are an environment variable and command-line flags. T3 can set neither per
thread (`t3 thread start` and `t3_thread_launch` take no env, settings or extra arguments; see
{doc}`design/per-seat-skills`), so a per-session switch isn't reachable. A project or local settings
file would turn auto memory off for the operator's own sessions in this project too, so the rig doesn't
set one. Instead `rigs/self/culture.md` tells seats not to write to auto memory: their durable record
is the issues and {doc}`lessons`. Seats still read the operator's memory at startup; only writing is
ruled out. If T3 gains a per-thread environment (the same ask as option F in
{doc}`design/per-seat-skills`), seats could run with `CLAUDE_CODE_DISABLE_AUTO_MEMORY=1`.

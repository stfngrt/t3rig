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

## Releasing

t3rig is published to PyPI as [`t3rig`](https://pypi.org/p/t3rig) by
`.github/workflows/release.yml`, with [trusted
publishing](https://docs.pypi.org/trusted-publishers/): no token is stored anywhere.

1. In the release pull request, set `version` in `pyproject.toml` to the new `X.Y.Z`, and move the
   "Unreleased" entries in `CHANGELOG.md` under a heading for that version.

   For the **first** release only, the same pull request switches the install path to PyPI, since
   the docs site deploys from `main` and would otherwise point readers at a package that isn't
   there yet:
   - `README.md` and `docs/getting-started.md` lead with `uv tool install 't3rig[serve]'` (it needs
     Python 3.13: add `--python 3.13` if uv picks an older one), and keep the checkout as the way
     to work on t3rig;
   - `docs/serve.md`, the `run` and `serve` help in `src/t3rig/cli.py`, and its "needs the serve
     extra" error (and the test for it in `tests/test_cli.py`) name `uv tool install
     't3rig[serve]'` before `uv sync --extra serve`;
   - drop "(not yet released)" from the version's heading in `CHANGELOG.md`.
2. After it's merged, tag the merge commit and push the tag:

   ```sh
   git tag vX.Y.Z
   git push origin vX.Y.Z
   ```

   The workflow runs the checks (ruff, pytest and the `-W` docs build), fails if the tag isn't `v`
   plus the version in `pyproject.toml`, builds with `uv build`, and publishes from the GitHub
   environment `pypi`.

To try a build first, run the workflow by hand (**Actions → Release → Run workflow**). It runs the
same checks and build, skips the tag check, and publishes to
[TestPyPI](https://test.pypi.org/p/t3rig) from the environment `testpypi`. TestPyPI refuses a
version it already has, so a second run of the same version fails; bump the version for each
trial. Check it with:

```sh
uv tool install --index-url https://test.pypi.org/simple/ \
  --extra-index-url https://pypi.org/simple/ 't3rig==X.Y.Z'
t3rig --version
```

The extra index supplies the dependencies TestPyPI doesn't have. uv searches the extra index
before the main one, so without the pin it could install a release from PyPI instead; pinning the
trial version makes sure the TestPyPI build is the one tested.

**Once, before the first publish**, the operator sets up PyPI and TestPyPI:

- Create an account on each, with two-factor authentication.
- On each, add a pending trusted publisher (PyPI: **Account settings → Publishing**) with:
  - PyPI project name: `t3rig`
  - Owner: `stfngrt`
  - Repository name: `t3rig`
  - Workflow name: `release.yml`
  - Environment name: `pypi` on PyPI, `testpypi` on TestPyPI
- In the GitHub repository, create the environments `pypi` and `testpypi` (**Settings →
  Environments**), and restrict `pypi`'s deployment to tags matching `v*`, so that only a release
  tag can publish to PyPI.

## The self rig

`rigs/self` develops t3rig with t3rig, as four seats. The {term}`project manager` (`dev.pm`) works
with the {term}`operator` and writes specs and {term}`tickets <ticket>` as GitHub issues, labelled
{term}`needs-approval`. When the operator adds {term}`rig-queue`, `dev.lead` takes the issue and
hands it to `dev.impl` and `dev.review`. Each issue is worked in its own git worktree,
`.worktrees/<n>` on the branch `issue-<n>`, and lands as one squash-merged pull request that
`dev.review` reviews; the main checkout stays on `main` ({doc}`adr/0007-worktree-and-pr-per-issue`).
The issue tracker is the interface between `dev.pm` and `dev.lead`, so there is no {term}`edge`
between them. That also means {term}`watch` pings nobody about `dev.pm`'s runs, and its stuck or
approval alerts print only on the `watch` console. With the tracker set in
`rigs/self/rig.t3rig.yaml`, `watch` pings `dev.lead` when an issue gets `rig-queue`, and the seat
that asked when `needs-answer` is removed (see {doc}`design/planning`). `dev.pm` is the
notify seat, so it gets a {term}`notice` for new questions, `ALERT`s and closed issues (see
{doc}`watch`).

The seats use skills from [Matt Pocock's set](https://github.com/mattpocock/skills) (MIT), vendored
under `rigs/self/agents/*/skills/` with a `CHANGES.md` listing each change. `docs/agents/` holds the
tracker and label docs they read.

- **Shared install:** until per-seat skills land (#7), the skills install into the shared checkout.
  Every seat, and the operator's own Claude sessions in this checkout, sees all of them. Where a skill
  had `disable-model-invocation: true`, it was removed so that seats can call it, so those skills can
  also be invoked automatically.
- **Not taken, `implement-spec`:** it works on an integration branch, with a worktree per ticket and
  a PR. The rig now has a worktree and a pull request per issue too, but without an integration
  branch, and `dev.impl` still doesn't commit: the lead does.
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

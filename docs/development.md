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

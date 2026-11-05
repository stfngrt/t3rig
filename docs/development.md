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

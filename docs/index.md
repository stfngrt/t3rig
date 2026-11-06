---
description: Run OpenRig-compatible rig.yaml files on T3 Code, with every seat as a T3 thread.
---

# t3rig

```{raw} html
<div class="hero">
  <img src="_static/icon.svg" alt="">
  <h1>t3rig</h1>
  <p class="tagline">Run OpenRig-compatible <code>rig.yaml</code> files on T3 Code, with every seat as a T3 thread. No tmux, no daemon.</p>
</div>
```

```{button-link} getting-started.html
:color: primary
:class: sd-mr-2
Get started
```

```{button-link} https://github.com/stfngrt/t3rig
:outline:
:color: primary
View on GitHub
```

Status: early, simple version. It has been run on a two-seat Claude rig.

::::{grid} 1 1 2 3
:gutter: 3
:margin: 4 0 0 0

:::{grid-item-card} OpenRig specs
:link: rig-specs
:link-type: doc
{term}`Pods <pod>`, {term}`members <member>`, {term}`edges <edge>`, culture and startup files,
{term}`agent specs <agent spec>` with skills and imports.
:::

:::{grid-item-card} Every seat a thread
:link: getting-started
:link-type: doc
`up` starts a T3 {term}`thread` per {term}`seat`. `send`, `log` and `ps` talk to them. Safe to
re-run.
:::

:::{grid-item-card} Permissions and stopping
:link: permissions
:link-type: doc
Map `permission_policy` to T3 modes, set effort, and interrupt or archive seats.
:::

:::{grid-item-card} Dispatcher pings
:link: watch
:link-type: doc
`watch` tells a seat's {term}`dispatcher` when it finishes or needs input, so nothing depends on an
agent remembering.
:::

:::{grid-item-card} Status page
:link: serve
:link-type: doc
`serve` runs `watch` as a server, with a live, read-only page of seats, issues and pings.
:::

:::{grid-item-card} Skills
:link: skills
:link-type: doc
Declared skills are installed into each seat's working folder, with a plan you confirm first.
:::

:::{grid-item-card} A generated CLI reference
:link: cli
:link-type: doc
Built from the argument parser itself, so it can't drift from the tool.
:::
::::

```{toctree}
:hidden:
:caption: Guide

getting-started
rig-specs
permissions
watch
serve
skills
limits
openrig
```

```{toctree}
:hidden:
:caption: Reference

cli
glossary
adr/index
```

```{toctree}
:hidden:
:caption: Project

development
lessons
design/index
research/index
```

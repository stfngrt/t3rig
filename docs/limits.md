# Limits

- `delegates_to` {term}`edges <edge>` decide who {doc}`watch` pings. Otherwise edges are only described in each
  seat's {term}`brief`, so nothing enforces them. `delegates_to` cycles are refused.
- {term}`Threads <thread>` start in the T3 project's root, except {term}`task threads <task thread>`, which run in
  their issue's T3 worktree ({doc}`adr/0009-task-threads-in-t3-worktrees`). A seat's `cwd` must be inside a T3
  project, and a long-lived seat is told to change to it.
- Only `claude-code` and `codex` seats, and only the {doc}`rig spec features <rig-specs>` listed as
  supported.
- Custom {term}`permission policies <permission policy>` are refused; {term}`runtime modes <runtime mode>` are an approximation and
  {doc}`not a security boundary <permissions>`.
- Instructions are sent once in the {term}`brief`, so a long-running seat can lose them when its
  conversation is compacted.
- `watch` is a foreground command that polls, so pings can lag by the interval.
- Status: early, simple version. It has been run on a two-seat Claude rig.

# Limits

- `delegates_to` edges decide who {doc}`watch` pings. Otherwise edges are only described in each
  seat's first message, so nothing enforces them. `delegates_to` cycles are refused.
- Threads start in the T3 project's root. A seat's `cwd` must be inside a T3 project, and the seat
  is told to change to it.
- Only `claude-code` and `codex` seats, and only the {doc}`rig spec features <rig-specs>` listed as
  supported.
- Custom permission policies are refused; modes are an approximation and
  {doc}`not a security boundary <permissions>`.
- Instructions are sent in the first message, so a long-running seat can lose them when its
  conversation is compacted.
- `watch` is a foreground command that polls, so pings can lag by the interval.
- Status: early, simple version. It has been run on a two-seat Claude rig.

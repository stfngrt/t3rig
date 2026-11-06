# `watch` polls and pings at least once

**Status:** accepted

`watch` polls the seats' threads and messages the {term}`dispatcher` when a seat finishes a
{term}`run` or has a request pending, "so reporting back doesn't depend on an agent remembering to"
(`56c86b3`). It is a foreground command, not a daemon, and keeps what it has pinged in a state file,
so a restart neither repeats nor misses a {term}`ping`: a crash can repeat one but never lose one
(`src/t3rig/watch.py`, {doc}`/watch`).

`delegates_to` cycles are refused because they "would otherwise ping forever" (`56c86b3`). Why
polling rather than another mechanism: not recorded.

**Consequences:** a ping can lag by the polling interval (15 seconds by default), and nothing is
pinged while `watch` isn't running.

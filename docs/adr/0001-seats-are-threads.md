# A seat is a T3 thread, found by its title

**Status:** accepted

Each {term}`seat` is a T3 {term}`thread` titled with its {term}`session name` `pod-member@rig`, "so
no state is kept outside T3" (`8c4e2bf`). t3rig finds a seat by that title. When several threads
share it, the newest wins and `ps` warns about the duplicates (`4bf9b23`).

The cost is that renaming a thread disconnects it from its seat (README). Other ways to link seats
to threads: not recorded.

The "no state outside T3" aim no longer holds in full: `watch` keeps a state file and `up` keeps a
skills record under `~/.local/state/t3rig/` ({doc}`0003-watch-polls`,
{doc}`0005-skills-copied-with-record`).

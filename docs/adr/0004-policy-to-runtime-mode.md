# Map OpenRig permission policies onto T3 runtime modes

**Status:** accepted

t3rig maps OpenRig's built-in {term}`permission policies <permission policy>` onto T3's four
{term}`runtime modes <runtime mode>` (plus `builtin:auto`), launches those seats idle, and sends the
{term}`brief` only after T3 confirms their settings (`2582fdf`). It signs in to T3's `/mcp` with a
one-time pairing code and "no extra dependency" (`2582fdf`); this is where the {term}`credential`
and {term}`access level` come from. Why the sign-in is capped by an access level and kept for 30
days: not recorded. A seat whose settings don't match is archived.

The mapping is an approximation: OpenRig's policies are finer-grained than T3's four modes, so
custom policy files are refused (README). Modes make a seat ask before acting; they are not a
security boundary. Alternatives: not recorded.

# Permissions and stopping

Seats with a {term}`permission policy` or `effort`, and `t3rig down`, use T3's `/mcp` tools, which need a
sign-in (the {term}`credential`). Other seats use the `t3` CLI and need none, but run in T3's default mode, which may be full
access.

```sh
uv run t3rig login --access auto                    # seats can't launch above this level
uv run t3rig up examples/restricted/rig.yaml        # lead at auto, review at approval-required
uv run t3rig stop examples/restricted/rig.yaml dev.review   # interrupt a run; the thread stays
uv run t3rig down examples/restricted/rig.yaml      # interrupt and archive; add --seat pod.member
```

## Policy to mode

A {term}`permission policy` becomes a {term}`runtime mode`, never above the {term}`access level` you signed in with. See also {term}`stop` and {term}`down`.

| `permission_policy` | T3 mode | Roughly |
|---|---|---|
| `builtin:locked` | `approval-required` | Anything that changes something waits for a person |
| `builtin:standard` | `auto-accept-edits` | File edits run; other commands can wait |
| `builtin:open`, `builtin:auto` | `auto` | Runs on its own, with T3's own checks |
| `builtin:yolo` | `full-access` | Runs anything |

This is an approximation: OpenRig's policies are finer-grained rules and T3 has four modes, so custom
policy files are refused. A member's policy overrides the rig's. Each seat launches idle, and its first
message is sent only after T3 confirms its mode, provider, model and effort. A mismatch is archived.

## Credential

The credential is kept in `~/.config/t3rig/credentials.json`, readable only by you, for 30 days. Stop
{doc}`watch` before `down`, or its pings to the archived dispatcher will fail.

## Not a security boundary

Modes aren't a security boundary. They make a seat ask before acting, but `locked` seats still run
read-only commands, and a seat allowed to run shell commands could use your `t3` CLI or credential.
Restricted seats also have to ask before running `t3rig send`, so `watch` is how they report back.
They can also stop for approval on shell commands that read files outside the repo, so have a
dispatcher pass along what they need.

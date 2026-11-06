# Status page

`t3rig serve` runs one rig's orchestration as a long-running server: the {term}`watch` loop, and a
live, read-only status page in the browser.

```sh
uv sync --extra serve       # in the t3rig checkout; plain `uv sync` includes it for development
t3rig serve rigs/self/rig.yaml
```

It prints the page's address, `http://127.0.0.1:8765/` by default (`--port`). By default it listens
on localhost only. It has no login. It answers only requests addressed to `127.0.0.1`, `localhost`
or the `--host` address, so another website can't reach it by pointing its own domain name at your
machine (DNS rebinding).

## On the local network

To open the page from another device, serve it on one of this machine's addresses with `--host`:

```sh
t3rig serve --host 192.168.5.10 rigs/self/rig.yaml   # then open http://192.168.5.10:8765/
```

```{warning}
**Anyone who can reach that address can read the page.** There is no login and no token. The page
shows each seat's latest message, which can hold private code, issue text or anything else a seat
wrote. Use `--host` only on a network you trust.
```

`--host` takes one concrete address or name. A wildcard such as `0.0.0.0` or `::` is refused,
because the Host check needs the one address the page is reached at.

## What it runs

The same loop as `t3rig watch`, as a task inside the server, with the same `--interval` and
`--tracker-interval`: it pings {term}`dispatchers <dispatcher>` and, with a tracker, the issue
pings (see {doc}`watch`). It takes the same lock, so `serve` and `watch` can't run for one rig at
the same time. An unexpected error in a round is printed as an `ALERT` and shown in the stream,
and the next round retries. `t3rig watch`, and `watch --once` from cron, still work without the
server.

## The page

- **Seats:** one card per {term}`seat`, with its status, model, mode, when it last changed, its
  latest message (what `t3rig log --messages 1` shows) and a link to its T3 {term}`thread`.
- **Needs you:** open issues labelled {term}`needs-answer`, or {term}`needs-approval` without
  {term}`rig-queue`.
- **Queue:** open issues labelled {term}`rig-queue` or {term}`in-progress`.
- **Stream:** what `watch` printed (pings, alerts and errors) and each seat's status changes, newest
  first.

Every issue is shown with its full URL. The page has no actions: it doesn't approve, message or stop
anything. Talk to the rig through `dev.pm`, or with `t3rig send`.

The page updates itself with server-sent events (htmx), after every check, without a reload. The
data comes from the same sources as `ps`, `log` and `watch`, and nothing is stored apart from the
last 200 stream entries, in memory.

## JSON API

The page's fragments are rendered from a JSON API on the same server:

| Path | Returns |
|---|---|
| `/api/seats` | `{"rig", "seats", "watch_last_check"}`: the rows of `t3rig ps --json`, each with `last_activity` (`role` and `text` of the latest message) |
| `/api/issues` | `{"rig", "tracker", "needs_you", "queue"}`: issues with `number`, `title`, `url` and `labels` |
| `/api/events` | `{"rig", "events"}`: stream entries with `time`, `kind` (`watch`, `seat` or `error`) and `text` |
| `/api/stream` | Server-sent events named `seats`, `issues` and `events`, carrying HTML fragments |

The data is as fresh as the last check, so up to `--interval` seconds old (`--tracker-interval` for
issues).

## Limits

- One rig per server. The page wraps the rig in its own section, so a later multi-rig view can list
  several.
- htmx 2.0.4 and its SSE extension 2.2.2 are vendored in the package (0BSD), so the page needs no
  CDN.

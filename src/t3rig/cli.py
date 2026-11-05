"""Run OpenRig-compatible rig specs as T3 Code threads."""

import argparse
import json
import sys
from collections.abc import Sequence
from datetime import UTC, datetime

from t3rig import __version__
from t3rig.mcp import ACCESS_LEVELS, login
from t3rig.rig import RigError, down, log, seat_rows, select_seats, send, stop, up
from t3rig.skills import apply_skills, plan_skills
from t3rig.spec import Rig, SpecError, load_rig
from t3rig.t3 import T3Cli, T3Error
from t3rig.watch import dispatchers, last_check, watch


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="t3rig", description=__doc__)
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)

    validate_parser = commands.add_parser("validate", help="Check that t3rig can run a rig spec.")
    validate_parser.add_argument("rig", help="path to rig.yaml")

    up_parser = commands.add_parser(
        "up", help="Install the rig's skills and start a T3 thread for each seat without one."
    )
    up_parser.add_argument("rig", help="path to rig.yaml")
    up_parser.add_argument(
        "--yes", action="store_true", help="apply the skill changes shown, then start the seats"
    )

    login_parser = commands.add_parser(
        "login",
        help="Sign in to T3's /mcp, for permission modes, effort and down. "
        "Seats can't be launched above this level.",
    )
    login_parser.add_argument("--access", required=True, choices=ACCESS_LEVELS)

    down_parser = commands.add_parser(
        "down", help="Interrupt and archive seats' threads, keeping their transcripts."
    )
    down_parser.add_argument("rig", help="path to rig.yaml")
    down_parser.add_argument("--seat", help="only this seat, as pod.member")

    stop_parser = commands.add_parser(
        "stop", help="Interrupt a seat's current run, keeping its thread so it can be messaged."
    )
    stop_parser.add_argument("rig", help="path to rig.yaml")
    stop_parser.add_argument("seat", help="seat as pod.member")

    ps_parser = commands.add_parser("ps", help="Show each seat's T3 thread and status.")
    ps_parser.add_argument("rig", help="path to rig.yaml")
    ps_parser.add_argument("--json", action="store_true", help="print JSON")

    send_parser = commands.add_parser("send", help="Message seats through their T3 threads.")
    send_parser.add_argument("rig", help="path to rig.yaml")
    send_parser.add_argument(
        "args",
        nargs="+",
        metavar="[seat] message",
        help="seat as pod.member, then the message or - to read it from stdin; "
        "leave out the seat with --pod or --all",
    )
    target = send_parser.add_mutually_exclusive_group()
    target.add_argument("--pod", help="send to every seat in this pod")
    target.add_argument("--all", action="store_true", help="send to every seat in the rig")
    send_parser.add_argument("--from", dest="sender", metavar="SEAT", help="the sending seat")
    send_parser.add_argument("--raw", action="store_true", help="leave out the From/To header")
    send_parser.add_argument("--wait", action="store_true", help="wait for the seat's reply")

    log_parser = commands.add_parser("log", help="Show a seat's latest messages.")
    log_parser.add_argument("rig", help="path to rig.yaml")
    log_parser.add_argument("seat", help="seat as pod.member")
    log_parser.add_argument(
        "--messages", type=int, default=10, help="how many messages to show (default: 10)"
    )

    watch_parser = commands.add_parser(
        "watch", help="Ping each dispatcher when a seat it delegates to finishes or needs input."
    )
    watch_parser.add_argument("rig", help="path to rig.yaml")
    watch_parser.add_argument(
        "--interval", type=float, default=15, help="seconds between checks (default: 15)"
    )
    watch_parser.add_argument("--once", action="store_true", help="check once and exit")
    return parser


def _validate(rig: Rig) -> None:
    print(f"{rig.name}: OK ({len(rig.seats)} seats, {len(rig.edges)} edges)")


def _up(rig: Rig, t3: T3Cli, yes: bool) -> int:
    plan = plan_skills(rig)  # Before anything starts, so a refusal leaves nothing half done.
    for problem in plan.errors:
        print(f"error: {problem}", file=sys.stderr)
    if plan.errors:
        return 1
    if plan.has_changes:
        for line in plan.lines():
            print(line)
        if not yes:
            print(
                "No changes made. Re-run with --yes to apply the skill changes and start the seats."
            )
            return 1
        apply_skills(plan)
    else:
        for line in plan.note_lines():
            print(line)
        apply_skills(plan)  # Only re-records files that already match; the project isn't touched.
    for line in up(rig, t3):
        print(line)
    return 0


def _ago(timestamp: str | None) -> str:
    if not timestamp:
        return "-"
    seconds = int((datetime.now(UTC) - datetime.fromisoformat(timestamp)).total_seconds())
    for size, unit in ((86400, "d"), (3600, "h"), (60, "m")):
        if seconds >= size:
            return f"{seconds // size}{unit} ago"
    return f"{max(seconds, 0)}s ago"


def _status_text(row: dict) -> str:
    pending = row["pending_requests"]
    return f"needs input ({pending})" if pending else row["status"]


def _ps(rig: Rig, t3: T3Cli, as_json: bool) -> None:
    rows = seat_rows(rig, t3)
    checked = last_check(rig)
    if as_json:
        print(json.dumps({"seats": rows, "watch_last_check": checked}, indent=2))
        return
    table = [("SEAT", "RUNTIME", "MODEL", "MODE", "STATUS", "UPDATED", "THREAD")]
    for row in rows:
        table.append(
            (
                row["seat"],
                row["runtime"],
                row["model"] or "-",
                row["mode"] or "-",
                _status_text(row),
                _ago(row["updated_at"]),
                row["link"] or "-",
            )
        )
    widths = [max(len(line[i]) for line in table) for i in range(len(table[0]))]
    for line in table:
        print(
            "  ".join(cell.ljust(width) for cell, width in zip(line, widths, strict=True)).rstrip()
        )
    for row in rows:
        if row["extra_threads"]:
            print(
                f"warning: {row['seat']} has {row['extra_threads']} older thread(s) titled "
                f"{row['session_name']}; using the newest",
                file=sys.stderr,
            )
    if dispatchers(rig):
        print(f"watch: last check {_ago(checked)}" if checked else "watch: has never run")


def _send(rig: Rig, t3: T3Cli, args: argparse.Namespace) -> int:
    fan_out = args.pod is not None or args.all
    expected = 1 if fan_out else 2
    if len(args.args) != expected:
        usage = "a message" if fan_out else "a seat and a message"
        raise RigError(f"send needs {usage}")
    if fan_out and args.wait:
        raise RigError("--wait only works with one seat")
    seat = None if fan_out else args.args[0]
    seats = select_seats(rig, seat, args.pod, args.all, args.sender)
    text = args.args[-1]
    message = sys.stdin.read() if text == "-" else text
    results = send(rig, t3, seats, message, args.sender, args.raw, args.wait)
    for result in results:
        if result.error:
            print(f"error: {result.seat.qualified_id}: {result.error}", file=sys.stderr)
        elif fan_out:
            print(f"{result.seat.qualified_id}: {result.output.strip()}")
        else:
            print(result.output, end="")
    return 1 if any(result.error for result in results) else 0


def _login(access: str) -> None:
    info = login(access)
    expires = datetime.fromtimestamp(info["expires_at"], UTC).date()
    print(f"Signed in to {info['origin']} at {info['access']}, until {expires}.")
    print("Revoke it with `t3 auth session revoke` (find it with `t3 auth session list`).")


def _down(rig: Rig, t3: T3Cli, seat: str | None) -> int:
    lines, ok = down(rig, t3, seat)
    for line in lines:
        print(line)
    return 0 if ok else 1


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    t3 = T3Cli()
    try:
        if args.command == "login":
            _login(args.access)
            return 0
        rig = load_rig(args.rig)
        if args.command == "validate":
            _validate(rig)
        elif args.command == "up":
            return _up(rig, t3, args.yes)
        elif args.command == "down":
            return _down(rig, t3, args.seat)
        elif args.command == "stop":
            print(stop(rig, t3, args.seat))
        elif args.command == "ps":
            _ps(rig, t3, args.json)
        elif args.command == "send":
            return _send(rig, t3, args)
        elif args.command == "log":
            print(log(rig, t3, args.seat, args.messages), end="")
        elif args.command == "watch":
            watch(rig, t3, args.interval, once=args.once, out=lambda line: print(line, flush=True))
    except KeyboardInterrupt:
        return 0
    except SpecError as error:
        for problem in error.errors:
            print(f"error: {problem}", file=sys.stderr)
        return 1
    except (RigError, T3Error) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0

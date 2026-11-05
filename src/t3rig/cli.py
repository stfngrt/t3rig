"""Run OpenRig-compatible rig specs as T3 Code threads."""

import argparse
import sys
from collections.abc import Sequence

from t3rig import __version__
from t3rig.rig import RigError, seat_statuses, send, up
from t3rig.spec import Rig, SpecError, load_rig
from t3rig.t3 import T3Cli, T3Error
from t3rig.watch import watch


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="t3rig", description=__doc__)
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)

    for name, description in (
        ("validate", "Check that t3rig can run a rig spec."),
        ("up", "Start a T3 thread for each seat that doesn't have one."),
        ("ps", "Show each seat's T3 thread and status."),
    ):
        commands.add_parser(name, help=description).add_argument("rig", help="path to rig.yaml")

    send_parser = commands.add_parser("send", help="Message a seat through its T3 thread.")
    send_parser.add_argument("rig", help="path to rig.yaml")
    send_parser.add_argument("seat", help="seat as pod.member")
    send_parser.add_argument("message", help="the message, or - to read it from stdin")
    send_parser.add_argument("--wait", action="store_true", help="wait for the seat's reply")

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


def _up(rig: Rig, t3: T3Cli) -> None:
    for line in up(rig, t3):
        print(line)


def _ps(rig: Rig, t3: T3Cli) -> None:
    rows = [("SEAT", "RUNTIME", "STATUS", "THREAD")]
    for status in seat_statuses(rig, t3):
        thread = status.thread or {}
        rows.append(
            (
                status.seat.qualified_id,
                status.seat.runtime,
                thread.get("status", "not started"),
                thread.get("link", "-"),
            )
        )
    widths = [max(len(row[i]) for row in rows) for i in range(3)]
    for row in rows:
        print(
            "  ".join(cell.ljust(width) for cell, width in zip(row, widths, strict=False))
            + "  "
            + row[3]
        )


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    t3 = T3Cli()
    try:
        rig = load_rig(args.rig)
        if args.command == "validate":
            _validate(rig)
        elif args.command == "up":
            _up(rig, t3)
        elif args.command == "ps":
            _ps(rig, t3)
        elif args.command == "send":
            message = sys.stdin.read() if args.message == "-" else args.message
            print(send(rig, t3, args.seat, message, wait=args.wait), end="")
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

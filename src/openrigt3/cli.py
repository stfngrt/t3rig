"""Run OpenRig-compatible rig specs as T3 Code threads."""

import argparse
import sys
from collections.abc import Sequence

from openrigt3 import __version__
from openrigt3.rig import RigError, seat_statuses, send, up
from openrigt3.spec import Rig, SpecError, load_rig
from openrigt3.t3 import T3Cli, T3Error


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="openrigt3", description=__doc__)
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)

    for name, description in (
        ("validate", "Check that openrigt3 can run a rig spec."),
        ("up", "Start a T3 thread for each seat that doesn't have one."),
        ("ps", "Show each seat's T3 thread and status."),
    ):
        commands.add_parser(name, help=description).add_argument("rig", help="path to rig.yaml")

    send_parser = commands.add_parser("send", help="Message a seat through its T3 thread.")
    send_parser.add_argument("rig", help="path to rig.yaml")
    send_parser.add_argument("seat", help="seat as pod.member")
    send_parser.add_argument("message", help="the message, or - to read it from stdin")
    send_parser.add_argument("--wait", action="store_true", help="wait for the seat's reply")
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
    except SpecError as error:
        for problem in error.errors:
            print(f"error: {problem}", file=sys.stderr)
        return 1
    except (RigError, T3Error) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0

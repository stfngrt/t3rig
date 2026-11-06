"""Ping delivery: one module that sends pings to seats' threads, retries and raises ALERTs.

Seat watching and issue watching decide what to ping about; this module owns how. A ping is
recorded as delivered only after its send succeeds, so a failed one is found again and retried on
the next round. After `ALERT_AFTER_FAILURES` failures in a row to the same seat, the failure is an
ALERT.
"""

from collections.abc import Callable
from dataclasses import dataclass

from t3rig.rig import envelope
from t3rig.spec import Rig
from t3rig.t3 import T3Error
from t3rig.threads import T3, RigError, seat_threads, thread_ids

ALERT_AFTER_FAILURES = 3
SENDER = "t3rig watch"


@dataclass
class Ping:
    """One line for a seat, and what to record once it's delivered."""

    about: str  # Who or what it's about, for the console: "dev.impl" or "#5".
    line: str
    delivered: Callable[[], None] = lambda: None


class Delivery:
    def __init__(self, rig: Rig, t3: T3, out: Callable[[str], None] = print) -> None:
        self.rig, self.t3, self.out = rig, t3, out
        self.failures: dict[tuple[str, str], int] = {}

    def alert(self, text: str) -> None:
        """Something a person has to hear about. Printed on the watch console."""
        self.out(f"ALERT: {text}")

    def send(
        self, seat: str, pings: list[Ping], closing: str, threads: dict[str, str] | None = None
    ) -> bool:
        """Send pings to a seat as one message. `threads` maps seat ids to thread ids, if known."""
        summary = ", ".join(ping.about for ping in pings)
        key = (seat, closing)  # Seat pings and issue pings to one seat fail and retry apart.
        try:
            if threads is None:
                threads = thread_ids(seat_threads(self.rig, self.t3))
            thread_id = threads.get(seat)
            if thread_id is None:
                raise RigError(f"{seat} has no thread")
            lines = "\n".join(ping.line for ping in pings)
            self.t3.send(thread_id, envelope(SENDER, seat, f"{lines}\n\n{closing}"))
        except (RigError, T3Error) as error:
            count = self.failures.get(key, 0) + 1
            self.failures[key] = count
            text = f"can't ping {seat} about {summary} (try {count}): {error}"
            if count >= ALERT_AFTER_FAILURES:
                self.alert(text)
            else:
                self.out(text)
            return False
        self.failures.pop(key, None)
        for ping in pings:
            ping.delivered()
        self.out(f"pinged {seat}: {summary}")
        return True

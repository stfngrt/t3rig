"""Ping delivery: one module that sends pings to seats' threads, retries and raises ALERTs.

Seat watching and issue watching decide what to ping about; this module owns how. A ping is
recorded as delivered only after its send succeeds, so a failed one is found again and retried on
the next round. After `ALERT_AFTER_FAILURES` failures in a row to the same seat, the failure is an
ALERT.

With a `notify_seat` in `rig.t3rig.yaml`, notices go to that seat too: every ALERT, and what
issue watching reports. Each is sent once. Pending notices and the keys of sent ones are kept under
"notices" in the watch state, so a restart neither repeats nor loses one.
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from t3rig.rig import envelope
from t3rig.spec import Rig
from t3rig.t3 import T3Error
from t3rig.threads import T3, RigError, seat_threads, thread_ids

ALERT_AFTER_FAILURES = 3
SENDER = "t3rig watch"
NOTICE_CLOSING = "These are notices for you. Follow up on each as your role says."
SENT_KEYS_KEPT = 500  # Enough to cover every alert that can still repeat.


@dataclass
class Ping:
    """One line for a seat, and what to record once it's delivered."""

    about: str  # Who or what it's about, for the console: "dev.impl" or "#5".
    line: str
    delivered: Callable[[], None] = lambda: None


class Delivery:
    def __init__(
        self,
        rig: Rig,
        t3: T3,
        out: Callable[[str], None] = print,
        state: dict[str, Any] | None = None,
    ) -> None:
        self.rig, self.t3, self.out = rig, t3, out
        self.failures: dict[tuple[str, str], int] = {}
        self.notices: dict[str, list[Any]] | None = None
        if rig.notify_seat is not None:
            notices = (state if state is not None else {}).setdefault("notices", {})
            notices.setdefault("sent", [])
            notices.setdefault("pending", [])
            self.notices = notices

    def alert(self, text: str, key: str | None = None) -> None:
        """Something a person has to hear about: printed on the watch console, and with a `key`,
        sent once to the notify seat as a notice."""
        self.out(f"ALERT: {text}")
        if key is not None:
            self.notify(f"ALERT: {text}", key)

    def notify(self, text: str, key: str | None = None) -> None:
        """Queue a notice for the notify seat. One with a `key` is sent only once."""
        if self.notices is None:
            return
        pending, sent = self.notices["pending"], self.notices["sent"]
        if key is not None and (key in sent or any(n["key"] == key for n in pending)):
            return
        pending.append({"key": key, "text": text})

    def send_notices(self, threads: dict[str, str] | None = None) -> None:
        """Send the pending notices. Ones that fail stay pending for the next round."""
        if not self.notices or not self.notices["pending"] or self.rig.notify_seat is None:
            return
        pending, sent = self.notices["pending"], self.notices["sent"]

        def delivered(notice: dict[str, Any]) -> None:
            pending.remove(notice)
            if notice["key"] is not None:
                sent.append(notice["key"])
                del sent[:-SENT_KEYS_KEPT]

        pings = [Ping("notice", f"- {n['text']}", lambda n=n: delivered(n)) for n in list(pending)]
        # A notice that can't be sent is printed, but never becomes a notice itself.
        self.send(self.rig.notify_seat, pings, NOTICE_CLOSING, threads, notice_on_alert=False)

    def send(
        self,
        seat: str,
        pings: list[Ping],
        closing: str,
        threads: dict[str, str] | None = None,
        notice_on_alert: bool = True,
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
                noticed = notice_on_alert and seat != self.rig.notify_seat
                notice_key = f"ping:{seat}:{closing}:{summary}" if noticed else None
                self.alert(text, notice_key)
            else:
                self.out(text)
            return False
        self.failures.pop(key, None)
        for ping in pings:
            ping.delivered()
        self.out(f"pinged {seat}: {summary}")
        return True

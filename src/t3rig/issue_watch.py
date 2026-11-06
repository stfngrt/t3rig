"""Issue watching: ping a seat when an open issue is queued or a question on it is answered.

What it has seen is kept under "issues" in the watch state, by issue number.
"""

import re
from typing import Any

from t3rig.delivery import Delivery, Ping
from t3rig.spec import Rig
from t3rig.threads import T3
from t3rig.tracker import Issue, Tracker

QUEUE_LABEL = "rig-queue"
ANSWER_LABEL = "needs-answer"
IN_PROGRESS_LABEL = "in-progress"
SIGNATURE = re.compile(r"^\s*🤖\s*([\w.-]+)", re.M)
ISSUE_CLOSING = "Read each issue above and its comments before you act on it."


class IssueWatch:
    """Open issues' labels, compared with the ones the state remembers."""

    def __init__(
        self, rig: Rig, t3: T3, tracker: Tracker, state: dict[str, Any], delivery: Delivery
    ) -> None:
        assert rig.tracker is not None
        self.rig, self.t3, self.tracker, self.delivery = rig, t3, tracker, delivery
        self.state = state
        self.issues: list[Issue] = []

    def open_issues(self) -> list[Issue]:
        """Open issues as of the last poll."""
        return self.issues

    def _apply_issue(self, key: str, updates: dict[str, Any]) -> None:
        issues = self.state.setdefault("issues", {})
        entry = issues.setdefault(key, {QUEUE_LABEL: False, ANSWER_LABEL: False, "asker": None})
        entry.update(updates)

    def _asker(self, number: int) -> str | None:
        """The seat that signed the newest signed comment, which asked the question."""
        for body in reversed(self.tracker.comments(number)):
            if found := SIGNATURE.search(body):
                return found[1] if self.rig.seat(found[1]) else None
        return None

    def _issue_pings(self, issue: Issue, entry: dict[str, Any] | None) -> list[tuple[str, Ping]]:
        """Pings for one open issue's label changes, by seat; other changes are kept at once."""
        assert self.rig.tracker is not None
        key, queue_seat = str(issue.number), self.rig.tracker.queue_seat
        queued = entry is not None and entry[QUEUE_LABEL]
        waiting = entry is not None and entry[ANSWER_LABEL]
        pings: list[tuple[str, Ping]] = []
        updates: dict[str, Any] = {}

        def ping(seat: str, text: str, change: dict[str, Any]) -> None:
            line = f"- {text}: {issue.url}"
            pings.append((seat, Ping(f"#{key}", line, lambda: self._apply_issue(key, change))))

        under_way = entry is None and IN_PROGRESS_LABEL in issue.labels
        if QUEUE_LABEL in issue.labels and not queued and under_way:
            updates[QUEUE_LABEL] = True  # First seen with work already under way: no ping.
        elif QUEUE_LABEL in issue.labels and not queued:
            ping(queue_seat, f"An issue was queued with `{QUEUE_LABEL}`", {QUEUE_LABEL: True})
        elif QUEUE_LABEL not in issue.labels and queued:
            updates[QUEUE_LABEL] = False
        if ANSWER_LABEL in issue.labels and not waiting:
            # Read now, before the answer adds signed comments of its own.
            updates |= {ANSWER_LABEL: True, "asker": self._asker(issue.number)}
        elif ANSWER_LABEL not in issue.labels and waiting:
            seat = (entry or {}).get("asker") or queue_seat
            text = f"The operator answered, and `{ANSWER_LABEL}` was removed"
            ping(seat, text, {ANSWER_LABEL: False, "asker": None})
        self._apply_issue(key, updates)  # Even with none, so the issue counts as seen.
        return pings

    def poll(self) -> None:
        """One round: ping when an open issue gains `rig-queue` or loses `needs-answer`."""
        issues = self.tracker.open_issues()
        self.issues = issues
        known = self.state.setdefault("issues", {})
        open_keys = {str(issue.number) for issue in issues}
        for key in [key for key in known if key not in open_keys]:
            del known[key]  # Closed: a reopened issue starts afresh.
        by_seat: dict[str, list[Ping]] = {}
        for issue in issues:
            for seat, ping in self._issue_pings(issue, known.get(str(issue.number))):
                by_seat.setdefault(seat, []).append(ping)
        for seat, pings in by_seat.items():
            self.delivery.send(seat, pings, ISSUE_CLOSING)

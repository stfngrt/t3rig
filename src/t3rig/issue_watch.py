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

    def _issue_pings(
        self, issue: Issue, entry: dict[str, Any] | None, first_poll: bool
    ) -> list[tuple[str, Ping]]:
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
            asker = self._asker(issue.number)
            updates |= {ANSWER_LABEL: True, "asker": asker}
            # Not on a rig's first poll: those labels were set before anyone was watching.
            if not first_poll and (asker is None or asker != self.rig.notify_seat):
                who = f"questions from {asker}" if asker else "questions"
                self.delivery.notify(f"#{key} needs you: {who} {issue.url}")
        elif ANSWER_LABEL not in issue.labels and waiting:
            seat = (entry or {}).get("asker") or queue_seat
            text = f"The operator answered, and `{ANSWER_LABEL}` was removed"
            ping(seat, text, {ANSWER_LABEL: False, "asker": None})
        # Always, so the issue counts as seen; title and URL word its notice if it closes.
        self._apply_issue(key, updates | {"title": issue.title, "url": issue.url})
        return pings

    def poll(self) -> None:
        """One round: ping when an open issue gains `rig-queue` or loses `needs-answer`."""
        issues = self.tracker.open_issues()
        self.issues = issues
        first_poll = "issues" not in self.state
        known = self.state.setdefault("issues", {})
        open_keys = {str(issue.number) for issue in issues}
        gone = [key for key in known if key not in open_keys]
        if gone and len(issues) >= self.tracker.limit:
            # The list may have been cut off, so a missing issue needn't be closed. Keep it.
            self.delivery.out(
                f"the tracker's list stopped at its limit of {self.tracker.limit} open issues, "
                "so issues missing from it aren't taken as closed"
            )
            gone = []
        for key in gone:
            # Closed, by the rig or the operator: they share one account, so every close counts.
            gone = known.pop(key)  # A reopened issue starts afresh.
            title = f": {gone['title']} {gone['url']}" if gone.get("url") else ""
            self.delivery.notify(f"#{key} closed{title}")
        by_seat: dict[str, list[Ping]] = {}
        for issue in issues:
            entry = known.get(str(issue.number))
            for seat, ping in self._issue_pings(issue, entry, first_poll):
                by_seat.setdefault(seat, []).append(ping)
        for seat, pings in by_seat.items():
            self.delivery.send(seat, pings, ISSUE_CLOSING)

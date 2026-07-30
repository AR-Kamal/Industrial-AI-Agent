"""Deterministic safety controls around untrusted model content."""

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol


class SafetyDisposition(StrEnum):
    ALLOW = "allow"
    STOP_AND_ESCALATE = "stop_and_escalate"


@dataclass(frozen=True)
class SafetyResult:
    disposition: SafetyDisposition
    reason: str = ""


class SafetyControl(Protocol):
    def evaluate(self, content: str) -> SafetyResult:
        """Evaluate untrusted content before it can be shown to a user."""

        ...


PROHIBITED_SYSTEMS = (
    r"emergency\s+stop|e-?stop|guard|interlock|safety\s+relay|"
    r"lockout|tagout|loto|safety\s+system"
)
PROHIBITED_ACTIONS = r"bypass|defeat|bridge|override|disable|remove|short"

UNSAFE_REQUEST_PATTERNS = (
    re.compile(
        rf"\b(?:{PROHIBITED_ACTIONS})\b.{{0,100}}\b(?:{PROHIBITED_SYSTEMS})\b",
        re.IGNORECASE,
    ),
    re.compile(
        rf"\b(?:{PROHIBITED_SYSTEMS})\b.{{0,100}}\b(?:{PROHIBITED_ACTIONS})\b",
        re.IGNORECASE,
    ),
)

HAZARDOUS_REQUEST_PATTERNS = (
    re.compile(
        r"\b(?:energize|power\s+on|work\s+live)\b.{0,100}"
        r"\b(?:exposed|bare|live)\b.{0,30}"
        r"\b(?:wire|wiring|conductor|terminal|electrical)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:start|move|jog|run)\b.{0,80}\b(?:robot|machine|axis)\b"
        r".{0,80}\b(?:person|someone|worker|inside|guard\s+open)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:disconnect|remove|open|loosen)\b.{0,80}"
        r"\b(?:hose|fitting|valve|line)\b.{0,80}"
        r"\b(?:pressurized|under\s+pressure|pressure)\b",
        re.IGNORECASE,
    ),
)

UNSAFE_OUTPUT_PATTERNS = (
    re.compile(
        rf"\b(?:you\s+can|you\s+should|try|steps?\s+to)\b.{{0,80}}"
        rf"\b(?:{PROHIBITED_ACTIONS})\b.{{0,100}}"
        rf"\b(?:{PROHIBITED_SYSTEMS})\b",
        re.IGNORECASE,
    ),
    re.compile(
        rf"\b(?:{PROHIBITED_ACTIONS})\b.{{0,60}}\b(?:{PROHIBITED_SYSTEMS})\b"
        r".{0,80}\b(?:by|using|with)\b",
        re.IGNORECASE,
    ),
)

LIVE_MACHINE_PATTERNS = (
    re.compile(
        r"\b(?:check|read|see|inspect|tell me)\b.{0,50}"
        r"\b(?:my|the|this)\b.{0,20}\b(?:machine|robot|equipment)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:is|what is|what's)\b.{0,40}"
        r"\b(?:machine|robot|equipment)\b.{0,30}"
        r"\b(?:running|stopped|status|condition|alarm|fault)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:current|live|right now)\b.{0,40}"
        r"\b(?:status|condition|alarm|fault|machine|robot)\b",
        re.IGNORECASE,
    ),
)


class ManufacturingSafetyControl:
    """Fail closed for prohibited safety-system bypass guidance."""

    def evaluate_request(self, content: str) -> SafetyResult:
        if any(pattern.search(content) for pattern in UNSAFE_REQUEST_PATTERNS):
            return SafetyResult(
                SafetyDisposition.STOP_AND_ESCALATE,
                "The request involves bypassing or defeating a safety system.",
            )
        if any(pattern.search(content) for pattern in HAZARDOUS_REQUEST_PATTERNS):
            return SafetyResult(
                SafetyDisposition.STOP_AND_ESCALATE,
                "The request involves a hazardous action requiring escalation.",
            )
        return SafetyResult(SafetyDisposition.ALLOW)

    def evaluate(self, content: str) -> SafetyResult:
        if any(pattern.search(content) for pattern in UNSAFE_OUTPUT_PATTERNS):
            return SafetyResult(
                SafetyDisposition.STOP_AND_ESCALATE,
                "The generated response may contain unsafe bypass guidance.",
            )
        return SafetyResult(SafetyDisposition.ALLOW)


def implies_live_machine_access(content: str) -> bool:
    return any(pattern.search(content) for pattern in LIVE_MACHINE_PATTERNS)

"""Shape and limits of a message the gateway accepts."""

import re
from dataclasses import dataclass
from typing import Any

CHANNELS = ("EMAIL", "SMS")
EMAIL_ADDRESS = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")
PHONE_NUMBER = re.compile(r"\+?[0-9 /-]{6,20}")
MAX_SUBJECT, MAX_BODY = 200, 2000


@dataclass(frozen=True)
class Message:
    channel: str
    recipient: str
    subject: str
    body: str


def parse(payload: Any) -> Message:
    if not isinstance(payload, dict):
        raise ValueError("payload must be an object")
    fields = {name: payload.get(name) for name in ("channel", "recipient", "subject", "body")}
    if not all(isinstance(value, str) for value in fields.values()):
        raise ValueError("all fields must be strings")
    message = Message(**fields)  # type: ignore[arg-type]
    if message.channel not in CHANNELS:
        raise ValueError("unknown channel")
    pattern = EMAIL_ADDRESS if message.channel == "EMAIL" else PHONE_NUMBER
    if not pattern.fullmatch(message.recipient):
        raise ValueError("recipient does not fit the channel")
    # No line breaks in the subject: they would let a caller inject mail headers
    if (
        not message.subject
        or len(message.subject) > MAX_SUBJECT
        or "\r" in message.subject
        or "\n" in message.subject
    ):
        raise ValueError("invalid subject")
    if not message.body or len(message.body) > MAX_BODY:
        raise ValueError("invalid body")
    return message

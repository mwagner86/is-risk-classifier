"""Hand a message on: e-mail by SMTP (Mailpit in the local stack), SMS only to the log."""

import logging
import smtplib
from email.message import EmailMessage

from notify_gateway.messages import Message

logger = logging.getLogger("notify_gateway")


class DeliveryError(Exception):
    """The downstream (SMTP) failed; the gateway answers 502."""


class SmtpDelivery:
    def __init__(self, host: str, port: int, sender: str) -> None:
        self.host, self.port, self.sender = host, port, sender

    def __call__(self, message: Message) -> None:
        if message.channel == "SMS":
            logger.info("SMS to %s: %s", message.recipient, message.subject)
            return
        mail = EmailMessage()
        mail["From"] = self.sender
        mail["To"] = message.recipient
        mail["Subject"] = message.subject
        mail.set_content(message.body)
        try:
            with smtplib.SMTP(self.host, self.port, timeout=10) as smtp:
                smtp.send_message(mail)
        except (OSError, smtplib.SMTPException) as exc:
            raise DeliveryError(str(exc)) from exc
        logger.info("e-mail to %s: %s", message.recipient, message.subject)

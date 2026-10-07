"""HTTP front of the gateway: POST /messages (Bearer token, JSON), GET /healthz."""

import hmac
import json
import logging
import os
import signal
import threading
import time
import uuid
from collections.abc import Callable
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import FrameType

from notify_gateway.delivery import DeliveryError, SmtpDelivery
from notify_gateway.messages import Message, parse

MAX_BODY_BYTES = 16 * 1024
FAILURE_MODES = ("none", "timeout", "5xx")
logger = logging.getLogger("notify_gateway")


class Handler(BaseHTTPRequestHandler):
    server_version = "notify-gateway"
    sys_version = ""

    def __init__(
        self,
        *args: object,
        token: str,
        deliver: Callable[[Message], None],
        failure_mode: Callable[[], str],
        timeout_delay: float,
    ) -> None:
        self.token, self.deliver = token, deliver
        self.failure_mode, self.timeout_delay = failure_mode, timeout_delay
        super().__init__(*args)  # type: ignore[arg-type]

    def _reply(self, status: int, body: dict[str, str]) -> None:
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(data)
        self.close_connection = True

    def do_GET(self) -> None:
        if self.path == "/healthz":
            self._reply(200, {"status": "ok", "failure_mode": self.failure_mode()})
        else:
            self._reply(404, {"error": "not found"})

    def do_POST(self) -> None:
        if self.path != "/messages":
            self._reply(404, {"error": "not found"})
            return
        supplied = self.headers.get("Authorization", "").removeprefix("Bearer ")
        if not hmac.compare_digest(supplied.encode(), self.token.encode()):
            self._reply(401, {"error": "unauthorized"})
            return
        try:
            length = int(self.headers.get("Content-Length", ""))
        except ValueError:
            self._reply(411, {"error": "length required"})
            return
        if length > MAX_BODY_BYTES:
            self._reply(413, {"error": "payload too large"})
            return
        mode = self.failure_mode()
        if mode == "5xx":
            self._reply(503, {"error": "service unavailable (forced)"})
            return
        if mode == "timeout":
            # Hold the connection longer than any sensible client timeout
            time.sleep(self.timeout_delay)
            self._reply(504, {"error": "timeout (forced)"})
            return
        try:
            message = parse(json.loads(self.rfile.read(length)))
        except ValueError as exc:  # includes JSONDecodeError
            self._reply(400, {"error": str(exc)})
            return
        try:
            self.deliver(message)
        except DeliveryError as exc:
            logger.warning("delivery failed: %s", exc)
            self._reply(502, {"error": "downstream delivery failed"})
            return
        self._reply(202, {"id": str(uuid.uuid4())})

    def log_message(self, format: str, *args: object) -> None:
        logger.info("%s %s", self.address_string(), format % args)


def make_server(
    host: str,
    port: int,
    *,
    token: str,
    deliver: Callable[[Message], None],
    failure_mode: Callable[[], str],
    timeout_delay: float = 30.0,
) -> ThreadingHTTPServer:
    if not token:
        raise ValueError("a token is required")
    handler = partial(
        Handler,
        token=token,
        deliver=deliver,
        failure_mode=failure_mode,
        timeout_delay=timeout_delay,
    )
    return ThreadingHTTPServer((host, port), handler)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    mode = os.environ.get("NOTIFY_FAILURE_MODE", "none")
    if mode not in FAILURE_MODES:
        raise SystemExit(f"NOTIFY_FAILURE_MODE must be one of {', '.join(FAILURE_MODES)}")
    server = make_server(
        "0.0.0.0",  # noqa: S104 - container-internal network only
        int(os.environ.get("NOTIFY_GATEWAY_PORT", "8002")),
        token=os.environ["NOTIFY_GATEWAY_TOKEN"],
        deliver=SmtpDelivery(
            os.environ.get("SMTP_HOST", "mailpit"),
            int(os.environ.get("SMTP_PORT", "1025")),
            os.environ.get("MAIL_FROM", "eskalation@is-risk.example"),
        ),
        failure_mode=lambda: mode,
    )

    def stop(signum: int, frame: FrameType | None) -> None:
        threading.Thread(target=server.shutdown, daemon=True).start()

    signal.signal(signal.SIGTERM, stop)
    logger.info("notify gateway on port %s, failure mode %s", server.server_address[1], mode)
    server.serve_forever()
    server.server_close()


if __name__ == "__main__":
    main()

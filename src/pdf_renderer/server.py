"""Minimal HTTP front for the renderer: POST /render (JSON in, PDF out), GET /healthz.

Standard library only. Reachable solely from the web container over the internal network "pdf".
"""

import json
import logging
import os
import signal
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import FrameType

from pdf_renderer.render import PayloadError, render

MAX_BODY_BYTES = 5 * 1024 * 1024
logger = logging.getLogger("pdf_renderer")


class Handler(BaseHTTPRequestHandler):
    server_version = "pdf-renderer"
    sys_version = ""

    def _reply(
        self, status: int, body: bytes, content_type: str = "text/plain; charset=utf-8"
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)
        self.close_connection = True

    def do_GET(self) -> None:
        if self.path == "/healthz":
            self._reply(200, b"ok")
        else:
            self._reply(404, b"not found")

    def do_POST(self) -> None:
        if self.path != "/render":
            self._reply(404, b"not found")
            return
        try:
            length = int(self.headers.get("Content-Length", ""))
        except ValueError:
            self._reply(411, b"length required")
            return
        if length > MAX_BODY_BYTES:
            # Refuse before reading anything
            self._reply(413, b"payload too large")
            return
        try:
            pdf = render(json.loads(self.rfile.read(length)))
        except (ValueError, PayloadError) as exc:  # JSONDecodeError is a ValueError
            logger.warning("rejected request: %s", exc)
            self._reply(400, b"bad request")
            return
        except Exception:
            logger.exception("rendering failed")
            self._reply(500, b"rendering failed")
            return
        self._reply(200, pdf, "application/pdf")

    def log_message(self, format: str, *args: object) -> None:
        logger.info("%s %s", self.address_string(), format % args)


def make_server(host: str, port: int) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), Handler)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    server = make_server("0.0.0.0", int(os.environ.get("PDF_RENDERER_PORT", "8001")))  # noqa: S104 - container-internal network only

    def stop(signum: int, frame: FrameType | None) -> None:
        threading.Thread(target=server.shutdown, daemon=True).start()

    signal.signal(signal.SIGTERM, stop)
    logger.info("pdf renderer listening on port %s", server.server_address[1])
    server.serve_forever()
    server.server_close()


if __name__ == "__main__":
    main()

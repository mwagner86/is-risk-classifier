"""Call the pdf-renderer service (M-03). The web container keeps the database; the renderer only
ever sees the rows it has to print."""

import json
import urllib.error
import urllib.request
from typing import Any

from django.conf import settings


class PdfRenderError(Exception):
    pass


def render_pdf(payload: dict[str, Any]) -> bytes:
    request = urllib.request.Request(  # noqa: S310 - fixed http URL from settings
        settings.PDF_RENDERER_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=settings.PDF_RENDERER_TIMEOUT) as response:  # noqa: S310
            body: bytes = response.read()
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise PdfRenderError(str(exc)) from exc
    if not body.startswith(b"%PDF-"):
        raise PdfRenderError("renderer returned no PDF")
    return body

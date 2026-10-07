"""Response headers that Django does not set itself (M-05)."""

from collections.abc import Callable

from django.conf import settings
from django.http import HttpRequest, HttpResponse
from django.utils.cache import add_never_cache_headers


class SecurityHeadersMiddleware:
    """Content-Security-Policy and Permissions-Policy on every response; authenticated pages
    are never cached, so risk data does not stay in browser or proxy caches."""

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        response = self.get_response(request)
        response.headers.setdefault("Content-Security-Policy", settings.CONTENT_SECURITY_POLICY)
        response.headers.setdefault("Permissions-Policy", settings.PERMISSIONS_POLICY)
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated:
            add_never_cache_headers(response)
        return response

from django.db import connection
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render

from apps.core.access import public


@public
def healthz(request: HttpRequest) -> HttpResponse:
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
    return HttpResponse("ok", content_type="text/plain")


@public
def login_failed(request: HttpRequest) -> HttpResponse:
    return render(request, "core/login_failed.html", status=403)

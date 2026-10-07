from django.urls import path

from apps.audit import views

urlpatterns = [path("audit-log/", views.audit_log, name="audit_log")]

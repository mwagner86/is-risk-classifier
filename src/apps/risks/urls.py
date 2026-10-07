from django.urls import path

from apps.risks import views

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("eskalationen/", views.escalation_list, name="escalation_list"),
    path(
        "eskalationen/<uuid:pk>/erneut-senden/",
        views.escalation_resend,
        name="escalation_resend",
    ),
    path("risiken/", views.risk_list, name="risk_list"),
    path("risiken/neu/", views.risk_create, name="risk_create"),
    path(
        "risiken/kategorie-vorschau/", views.classification_preview, name="classification_preview"
    ),
    path("risiken/score-vorschau/", views.score_preview, name="score_preview"),
    path("risiken/<uuid:pk>/", views.risk_detail, name="risk_detail"),
    path("risiken/<uuid:pk>/bearbeiten/", views.risk_edit, name="risk_edit"),
    path("risiken/<uuid:pk>/klassifizierung/", views.risk_reclassify, name="risk_reclassify"),
    path("risiken/<uuid:pk>/bewertung/", views.risk_score, name="risk_score"),
    path("risiken/<uuid:pk>/status/", views.risk_change_status, name="risk_change_status"),
    path(
        "risiken/<uuid:pk>/incident-response/",
        views.risk_incident_response,
        name="risk_incident_response",
    ),
    path("freigaben/", views.approval_list, name="approval_list"),
    path("freigaben/<uuid:pk>/", views.approval_decide, name="approval_decide"),
]

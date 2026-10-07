from django.urls import path

from apps.exports import views

urlpatterns = [
    path("export/", views.export_page, name="export_page"),
    path("export/csv/", views.export_csv, name="export_csv"),
    path("export/pdf/", views.export_pdf, name="export_pdf"),
]

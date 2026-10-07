from django.urls import path

from apps.cmdb import views

urlpatterns = [path("assets/", views.asset_list, name="asset_list")]

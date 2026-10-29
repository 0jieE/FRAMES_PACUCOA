from django.urls import path

from . import views

app_name = "compliance"

urlpatterns = [
    path("matrix/", views.matrix, name="matrix"),
    path("expiring/", views.expiring, name="expiring"),
]

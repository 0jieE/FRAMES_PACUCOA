from django.urls import path

from . import views

app_name = "documents"

urlpatterns = [
    path("", views.document_list, name="list"),
    path("upload/", views.upload, name="upload"),
    path("queue/", views.validation_queue, name="validation_queue"),
    path("<int:pk>/", views.document_detail, name="detail"),
    path("<int:pk>/preview/", views.document_preview, name="preview"),
    path("<int:pk>/download/", views.document_download, name="download"),
    path("<int:pk>/validate/", views.validate, name="validate"),
]

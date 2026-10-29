from django.urls import path

from . import views

app_name = "requirements"

urlpatterns = [
    path("", views.RuleListView.as_view(), name="list"),
    path("subareas/new/", views.SubAreaCreateView.as_view(), name="subarea_create"),
    path("subareas/<int:pk>/edit/", views.SubAreaUpdateView.as_view(), name="subarea_edit"),
    path("subareas/<int:pk>/delete/", views.SubAreaDeleteView.as_view(), name="subarea_delete"),
    path("new/", views.RequirementCreateView.as_view(), name="requirement_create"),
    path("<int:pk>/edit/", views.RequirementUpdateView.as_view(), name="requirement_edit"),
    path("<int:pk>/delete/", views.RequirementDeleteView.as_view(), name="requirement_delete"),
    path("<int:pk>/toggle/", views.RequirementToggleView.as_view(), name="requirement_toggle"),
]

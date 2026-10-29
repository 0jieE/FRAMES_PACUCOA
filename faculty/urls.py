from django.urls import path

from . import views

app_name = "faculty"

urlpatterns = [
    path("", views.faculty_list, name="list"),
    path("me/", views.my_profile, name="my_profile"),
    path("new/", views.faculty_create, name="create"),
    path("<int:pk>/", views.faculty_detail, name="detail"),
    path("<int:pk>/edit/", views.faculty_edit, name="edit"),
    path("departments/", views.department_list, name="department_list"),
    path("departments/new/", views.department_form, name="department_create"),
    path("departments/<int:pk>/edit/", views.department_form, name="department_edit"),
]

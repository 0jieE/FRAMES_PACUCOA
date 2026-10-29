from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("", views.home, name="home"),
    path("login/", views.FramesLoginView.as_view(), name="login"),
    path("logout/", views.FramesLogoutView.as_view(), name="logout"),
    path("password/change/", views.FramesPasswordChangeView.as_view(), name="password_change"),
    path("users/", views.user_list, name="user_list"),
    path("users/new/", views.user_create, name="user_create"),
    path("users/<int:pk>/edit/", views.user_edit, name="user_edit"),
    path("users/<int:pk>/toggle-active/", views.user_toggle_active, name="user_toggle_active"),
    path("users/<int:pk>/reset-password/", views.user_reset_password, name="user_reset_password"),
]

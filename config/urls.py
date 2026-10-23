from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path, reverse_lazy

from tasks.auth_forms import EmployeeAuthenticationForm

urlpatterns = [
    path("admin/", admin.site.urls),
    path(
        "accounts/login/",
        auth_views.LoginView.as_view(
            template_name="registration/login.html",
            authentication_form=EmployeeAuthenticationForm,
        ),
        name="login",
    ),
    path(
        "accounts/password/change/",
        auth_views.PasswordChangeView.as_view(
            template_name="registration/password_change_form.html",
            success_url=reverse_lazy("password_change_done"),
        ),
        name="password_change",
    ),
    path(
        "accounts/password/change/done/",
        auth_views.PasswordChangeDoneView.as_view(
            template_name="registration/password_change_done.html",
        ),
        name="password_change_done",
    ),
    path("accounts/logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("", include("tasks.urls")),
]

from django import forms
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.models import User


class EmployeeChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        return f"{obj.last_name} {obj.first_name}".strip()


class EmployeeAuthenticationForm(AuthenticationForm):
    """Authenticate using an employee selected by surname and first name."""

    employee = EmployeeChoiceField(
        queryset=User.objects.none(),
        label="Фамилия и имя",
        empty_label="Выберите сотрудника…",
        widget=forms.Select(
            attrs={
                "class": "employee-native-select",
                "autocomplete": "off",
            }
        ),
    )

    error_messages = {
        "invalid_login": "Неверный пароль для выбранного сотрудника.",
        "inactive": "Эта учётная запись отключена.",
    }

    def __init__(self, request=None, *args, **kwargs):
        super().__init__(request=request, *args, **kwargs)

        # Django still authenticates by username internally, but it is resolved
        # only from the selected User object and never typed by the employee.
        self.fields["username"].required = False
        self.fields["username"].widget = forms.HiddenInput()

        self.fields["employee"].queryset = (
            User.objects.filter(is_active=True)
            .exclude(first_name="")
            .exclude(last_name="")
            .order_by("last_name", "first_name", "pk")
        )

        self.fields["password"].widget.attrs.update(
            {
                "autocomplete": "current-password",
                "placeholder": "Введите пароль",
                "class": "employee-login-password",
            }
        )

    def clean(self):
        employee = self.cleaned_data.get("employee")
        self.cleaned_data["username"] = employee.get_username() if employee else ""
        return super().clean()

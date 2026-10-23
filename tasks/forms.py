from django import forms
from django.contrib.auth.models import User
from django.db.models import Case, IntegerField, When
from django.utils import timezone

from .models import (
    EmployeeAbsence,
    SavedTaskFilter,
    Task,
    TaskComment,
    TaskImage,
    TaskTemplate,
)
from .permissions import assignable_users, manager_users
from .services import get_workload_ranking


class FullNameUserChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        name = f"{obj.last_name} {obj.first_name}".strip()
        return name or obj.username


class FullNameUserMultipleChoiceField(forms.ModelMultipleChoiceField):
    def label_from_instance(self, obj):
        return obj.get_full_name() or obj.username


class ISODateInput(forms.DateInput):
    """HTML5 date input that always renders ISO YYYY-MM-DD."""

    input_type = "date"

    def __init__(self, attrs=None):
        super().__init__(attrs=attrs, format="%Y-%m-%d")


class WorkloadUserChoiceField(forms.ModelChoiceField):
    def __init__(self, *args, **kwargs):
        self.workload_map = {}
        self.absence_map = {}
        super().__init__(*args, **kwargs)

    def label_from_instance(self, obj):
        row = self.workload_map.get(obj.pk)
        absence = self.absence_map.get(obj.pk)
        name = obj.get_full_name().strip() or obj.username
        absence_text = ""
        if absence is not None:
            absence_text = f" — ОТСУТСТВУЕТ до {absence.end_date:%d.%m}"
        if row is None:
            return name + absence_text
        return (
            f"{name} — загрузка {row.score}; активных {row.active_count}; "
            f"срочных {row.urgent_count}; до 3 дней {row.due_soon_count}; "
            f"просрочено {row.overdue_count}{absence_text}"
        )


class TaskForm(forms.ModelForm):
    responsible_manager = FullNameUserChoiceField(
        queryset=User.objects.none(),
        label="Ответственный руководитель",
        required=False,
        empty_label=None,
    )
    assigned_to = WorkloadUserChoiceField(
        queryset=User.objects.none(),
        label="Основной исполнитель",
    )
    additional_assignees = FullNameUserMultipleChoiceField(
        queryset=User.objects.none(),
        label="Дополнительные исполнители",
        required=False,
        widget=forms.CheckboxSelectMultiple(attrs={"class": "assignee-options"}),
        help_text="Можно выбрать нескольких сотрудников. Статус и проверка у задачи общие.",
    )

    class Meta:
        model = Task
        fields = [
            "title",
            "description",
            "responsible_manager",
            "assigned_to",
            "additional_assignees",
            "status",
            "priority",
            "effort",
            "start_date",
            "due_date",
        ]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 5}),
            "start_date": ISODateInput(),
            "due_date": ISODateInput(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["start_date"].input_formats = ["%Y-%m-%d"]
        self.fields["due_date"].input_formats = ["%Y-%m-%d"]
        self.fields["responsible_manager"].queryset = manager_users()

        ranking = get_workload_ranking()
        self.workload_ranking = ranking
        ids = [row.user.pk for row in ranking]
        if ids:
            order = Case(
                *[
                    When(pk=pk, then=position)
                    for position, pk in enumerate(ids)
                ],
                output_field=IntegerField(),
            )
            self.fields["assigned_to"].queryset = User.objects.filter(
                pk__in=ids
            ).order_by(order)
        else:
            self.fields["assigned_to"].queryset = User.objects.none()
        # Eliminate the primary worker *before rendering* and validate it on the
        # server too. JavaScript also reacts instantly when the select changes.
        if self.is_bound:
            lead_id = self.data.get(self.add_prefix("assigned_to"))
        elif self.instance and self.instance.pk:
            lead_id = self.instance.assigned_to_id
        else:
            lead_id = self.initial.get("assigned_to")
            lead_id = getattr(lead_id, "pk", lead_id)
        extras = assignable_users()
        if lead_id and str(lead_id).isdigit():
            extras = extras.exclude(pk=int(lead_id))
        self.fields["additional_assignees"].queryset = extras
        if self.instance and self.instance.pk:
            # Changing the primary worker requires a documented handover.
            # A disabled field retains its initial value even for forged POST data.
            self.fields["assigned_to"].disabled = True
            self.fields["assigned_to"].help_text = (
                "Для смены основного исполнителя используйте «Передать задачу» в карточке — причина будет сохранена."
            )
        self.fields["assigned_to"].workload_map = {
            row.user.pk: row for row in ranking
        }

        today = timezone.localdate()
        active_absences = EmployeeAbsence.objects.filter(
            start_date__lte=today,
            end_date__gte=today,
        ).select_related("user")
        self.fields["assigned_to"].absence_map = {
            absence.user_id: absence for absence in active_absences
        }

        if "status" in self.fields:
            current_status = (
                self.instance.status
                if self.instance and self.instance.pk
                else Task.Status.NEW
            )
            if current_status == Task.Status.REVIEW:
                normal_manager_statuses = [
                    Task.Status.REVIEW,
                    Task.Status.DONE,
                    Task.Status.CANCELLED,
                ]
            elif current_status == Task.Status.REVISION:
                normal_manager_statuses = [
                    Task.Status.REVISION,
                    Task.Status.DONE,
                    Task.Status.CANCELLED,
                ]
            else:
                normal_manager_statuses = [
                    Task.Status.NEW,
                    Task.Status.IN_PROGRESS,
                    Task.Status.DONE,
                    Task.Status.CANCELLED,
                ]
            self.fields["status"].choices = [
                (value, Task.Status(value).label)
                for value in normal_manager_statuses
            ]


    def clean(self):
        cleaned = super().clean()
        lead = cleaned.get("assigned_to")
        extras = cleaned.get("additional_assignees")
        if lead is not None and extras is not None:
            # A promoted co-worker cannot also remain listed among extras.
            cleaned["additional_assignees"] = extras.exclude(pk=lead.pk)
        return cleaned


class TaskCreateForm(TaskForm):
    class Meta(TaskForm.Meta):
        fields = [
            "title",
            "description",
            "responsible_manager",
            "assigned_to",
            "additional_assignees",
            "priority",
            "effort",
            "start_date",
            "due_date",
        ]


class EmployeeTaskStatusForm(forms.ModelForm):
    class Meta:
        model = Task
        fields = ["status"]

    TRANSITIONS = {
        Task.Status.NEW: [Task.Status.NEW, Task.Status.IN_PROGRESS],
        Task.Status.IN_PROGRESS: [Task.Status.IN_PROGRESS, Task.Status.REVIEW],
        Task.Status.REVISION: [Task.Status.REVISION, Task.Status.IN_PROGRESS],
    }

    LABELS = {
        Task.Status.NEW: "Новая",
        Task.Status.IN_PROGRESS: "В работе",
        Task.Status.REVIEW: "Выполнено — отправить на проверку",
        Task.Status.REVISION: "На доработке",
    }

    def __init__(self, *args, **kwargs):
        instance = kwargs.get("instance")
        self.original_status = instance.status if instance else None
        super().__init__(*args, **kwargs)
        allowed = self.TRANSITIONS.get(self.original_status, [])
        self.fields["status"].choices = [
            (status, self.LABELS[status]) for status in allowed
        ]

    def clean_status(self):
        status = self.cleaned_data["status"]
        allowed = self.TRANSITIONS.get(self.original_status, [])
        if status not in allowed:
            raise forms.ValidationError("Недопустимый переход статуса.")
        return status


class TaskHandoverForm(forms.Form):
    to_employee = WorkloadUserChoiceField(
        queryset=User.objects.none(), label="Новый основной исполнитель"
    )
    reason = forms.CharField(
        label="Причина передачи", max_length=500,
        widget=forms.Textarea(attrs={"rows": 3, "placeholder": "Например: больничный, отпуск или перераспределение нагрузки"}),
    )
    keep_previous = forms.BooleanField(
        required=False, label="Оставить прежнего сотрудника соисполнителем",
        help_text="При больничном оставьте выключенным: задача исчезнет из его текущей загрузки.",
    )

    def __init__(self, *args, task=None, **kwargs):
        super().__init__(*args, **kwargs)
        ranking = get_workload_ranking()
        employees = [row.user.pk for row in ranking]
        self.fields["to_employee"].queryset = assignable_users().filter(pk__in=employees)
        self.fields["to_employee"].workload_map = {row.user.pk: row for row in ranking}
        self.fields["to_employee"].absence_map = {
            row.user.pk: row.absence for row in ranking if row.absence is not None
        }
        self.task = task

    def clean_to_employee(self):
        employee = self.cleaned_data["to_employee"]
        if self.task is not None and employee.pk == self.task.assigned_to_id:
            raise forms.ValidationError("Этот сотрудник уже является основным исполнителем.")
        return employee


class BulkTaskUpdateForm(forms.Form):
    class Action:
        ASSIGNEE = "assignee"
        MANAGER = "manager"
        PRIORITY = "priority"
        DUE_DATE = "due_date"

    action = forms.ChoiceField(
        label="Что изменить",
        choices=[
            (Action.ASSIGNEE, "Исполнитель"),
            (Action.MANAGER, "Ответственный руководитель"),
            (Action.PRIORITY, "Приоритет"),
            (Action.DUE_DATE, "Срок"),
        ],
    )
    assigned_to = FullNameUserChoiceField(
        queryset=User.objects.none(),
        required=False,
        label="Новый исполнитель",
    )
    responsible_manager = FullNameUserChoiceField(
        queryset=User.objects.none(),
        required=False,
        label="Новый руководитель",
    )
    priority = forms.ChoiceField(
        choices=[("", "Выберите приоритет"), *Task.Priority.choices],
        required=False,
        label="Новый приоритет",
    )
    due_date = forms.DateField(
        required=False,
        input_formats=["%Y-%m-%d"],
        widget=ISODateInput(),
        label="Новый срок",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["assigned_to"].queryset = assignable_users()
        self.fields["responsible_manager"].queryset = manager_users()

    def clean(self):
        cleaned = super().clean()
        action = cleaned.get("action")
        required_field = {
            self.Action.ASSIGNEE: "assigned_to",
            self.Action.MANAGER: "responsible_manager",
            self.Action.PRIORITY: "priority",
            self.Action.DUE_DATE: "due_date",
        }.get(action)
        if required_field and not cleaned.get(required_field):
            self.add_error(required_field, "Укажите новое значение.")
        return cleaned


class SavedTaskFilterForm(forms.ModelForm):
    class Meta:
        model = SavedTaskFilter
        fields = ["name"]
        widgets = {
            "name": forms.TextInput(
                attrs={
                    "placeholder": "Например: Срочные мои",
                    "maxlength": 80,
                }
            )
        }


class RevisionReasonForm(forms.Form):
    revision_reason = forms.CharField(
        label="Причина доработки",
        max_length=1000,
        widget=forms.Textarea(
            attrs={
                "rows": 4,
                "placeholder": "Что именно нужно исправить или дополнить?",
            }
        ),
    )


class TaskCommentForm(forms.ModelForm):
    class Meta:
        model = TaskComment
        fields = ["text"]
        widgets = {
            "text": forms.Textarea(
                attrs={
                    "rows": 3,
                    "placeholder": "Напишите комментарий по задаче…",
                }
            )
        }
        labels = {"text": "Комментарий"}


class TaskImageForm(forms.ModelForm):
    MAX_IMAGE_SIZE = 8 * 1024 * 1024
    ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}

    class Meta:
        model = TaskImage
        fields = ["image"]
        widgets = {
            "image": forms.ClearableFileInput(
                attrs={
                    "accept": "image/jpeg,image/png,image/webp",
                    "capture": "environment",
                }
            )
        }
        labels = {"image": "Фото или скриншот"}

    def clean_image(self):
        image = self.cleaned_data["image"]
        if image.size > self.MAX_IMAGE_SIZE:
            raise forms.ValidationError(
                "Максимальный размер изображения — 8 МБ."
            )
        content_type = getattr(image, "content_type", "")
        if content_type not in self.ALLOWED_CONTENT_TYPES:
            raise forms.ValidationError("Разрешены только JPG, PNG и WebP.")
        return image


class EmployeeAbsenceForm(forms.ModelForm):
    user = FullNameUserChoiceField(
        queryset=User.objects.none(),
        label="Сотрудник",
    )

    class Meta:
        model = EmployeeAbsence
        fields = ["user", "start_date", "end_date", "reason"]
        widgets = {
            "start_date": ISODateInput(),
            "end_date": ISODateInput(),
            "reason": forms.TextInput(
                attrs={"placeholder": "Отпуск, командировка, больничный…"}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["start_date"].input_formats = ["%Y-%m-%d"]
        self.fields["end_date"].input_formats = ["%Y-%m-%d"]
        self.fields["user"].queryset = assignable_users()


class TaskTemplateForm(forms.ModelForm):
    class Meta:
        model = TaskTemplate
        fields = [
            "name",
            "title",
            "description",
            "priority",
            "effort",
            "default_due_days",
            "is_active",
        ]
        widgets = {"description": forms.Textarea(attrs={"rows": 5})}

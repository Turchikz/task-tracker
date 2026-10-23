from datetime import timedelta
from io import BytesIO

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from tasks.forms import TaskCreateForm
from tasks.models import EmployeeAbsence, Notification, Task, TaskEvent, TaskImage


def png_upload(name="screen.png"):
    buffer = BytesIO()
    Image.new("RGB", (24, 24), "white").save(buffer, format="PNG")
    return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/png")


@pytest.mark.django_db
def test_employee_can_upload_and_view_protected_task_image(client, manager, employee, second_employee, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    task = Task.objects.create(title="Фото", created_by=manager, assigned_to=employee)
    client.force_login(employee)

    response = client.post(reverse("task_image_upload", args=[task.pk]), {"image": png_upload()})
    assert response.status_code == 302
    image = TaskImage.objects.get(task=task)
    assert image.content_type == "image/png"
    assert TaskEvent.objects.filter(task=task, kind=TaskEvent.Kind.IMAGE).exists()

    response = client.get(reverse("task_image_file", args=[task.pk, image.pk]))
    assert response.status_code == 200
    assert response["Content-Type"] == "image/png"

    client.force_login(second_employee)
    assert client.get(reverse("task_image_file", args=[task.pk, image.pk])).status_code == 404


@pytest.mark.django_db
def test_task_image_rejects_non_image(client, manager, employee, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    task = Task.objects.create(title="Не файл", created_by=manager, assigned_to=employee)
    client.force_login(employee)
    upload = SimpleUploadedFile("notes.txt", b"not an image", content_type="text/plain")
    response = client.post(reverse("task_image_upload", args=[task.pk]), {"image": upload})
    assert response.status_code == 400
    assert TaskImage.objects.count() == 0


@pytest.mark.django_db
def test_absence_is_visible_in_assignee_choice_and_sorted_last(manager, employee, second_employee):
    today = timezone.localdate()
    EmployeeAbsence.objects.create(
        user=employee,
        start_date=today,
        end_date=today + timedelta(days=4),
        reason="Отпуск",
        created_by=manager,
    )
    form = TaskCreateForm()
    choices = list(form.fields["assigned_to"].queryset)
    assert choices[-1] == employee
    assert "ОТСУТСТВУЕТ" in form.fields["assigned_to"].label_from_instance(employee)


@pytest.mark.django_db
def test_absence_overlap_is_rejected(client, manager, employee):
    today = timezone.localdate()
    EmployeeAbsence.objects.create(user=employee, start_date=today, end_date=today + timedelta(days=3), created_by=manager)
    client.force_login(manager)
    response = client.post(
        reverse("absences"),
        {
            "user": employee.pk,
            "start_date": (today + timedelta(days=2)).isoformat(),
            "end_date": (today + timedelta(days=5)).isoformat(),
            "reason": "Командировка",
        },
    )
    assert response.status_code == 200
    assert EmployeeAbsence.objects.filter(user=employee).count() == 1
    assert "пересекающийся" in response.content.decode()


@pytest.mark.django_db
def test_notifications_are_split_by_action_required(client, manager, employee):
    task = Task.objects.create(title="Уведомления", created_by=manager, assigned_to=employee, due_date=timezone.localdate() - timedelta(days=1))
    Notification.objects.all().delete()
    Notification.objects.create(user=employee, task=task, kind=Notification.Kind.OVERDUE, message="Просрочено")
    Notification.objects.create(user=employee, task=task, kind=Notification.Kind.DUE_CHANGED, message="Срок изменён")
    client.force_login(employee)
    response = client.get(reverse("notifications"))
    content = response.content.decode()
    assert "Требует действия" in content
    assert "Информация" in content
    assert "Просрочено" in content
    assert "Срок изменён" in content


@pytest.mark.django_db
def test_manager_analytics_contains_completed_task(client, manager, employee):
    today = timezone.localdate()
    task = Task.objects.create(
        title="Аналитика",
        created_by=manager,
        assigned_to=employee,
        status=Task.Status.IN_PROGRESS,
        due_date=today + timedelta(days=1),
    )
    task.status = Task.Status.DONE
    task._change_actor = manager
    task.save()

    client.force_login(manager)
    response = client.get(reverse("analytics"), {"from": today.isoformat(), "to": today.isoformat()})
    assert response.status_code == 200
    assert response.context["analytics"]["completed"] == 1
    assert response.context["analytics"]["on_time"] == 1


@pytest.mark.django_db
def test_employee_cannot_open_manager_analytics(client, employee):
    client.force_login(employee)
    assert client.get(reverse("analytics")).status_code == 403
    assert client.get(reverse("activity_feed")).status_code == 403
    assert client.get(reverse("absences")).status_code == 403


@pytest.mark.django_db
def test_comment_appears_in_activity_feed(client, manager, employee):
    task = Task.objects.create(title="Лента", created_by=manager, assigned_to=employee)
    client.force_login(employee)
    response = client.post(reverse("task_comment_add", args=[task.pk]), {"text": "Готовлю результат"})
    assert response.status_code == 302
    assert TaskEvent.objects.filter(task=task, kind=TaskEvent.Kind.COMMENT, actor=employee).exists()
    assert Notification.objects.filter(user=manager, task=task, kind=Notification.Kind.COMMENT).exists()

    client.force_login(manager)
    response = client.get(reverse("activity_feed"))
    assert response.status_code == 200
    assert "Добавлен комментарий" in response.content.decode()

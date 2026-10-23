from datetime import date

import pytest
from django.urls import reverse

from tasks.forms import EmployeeAbsenceForm
from tasks.holidays import get_rt_holiday_name
from tasks.models import EmployeeAbsence
from tasks.services import get_workload_timeline


def test_rt_2026_calendar_contains_regional_holidays_and_transfers():
    assert get_rt_holiday_name(date(2026, 3, 20)) == "Ураза-байрам"
    assert get_rt_holiday_name(date(2026, 5, 27)) == "Курбан-байрам"
    assert get_rt_holiday_name(date(2026, 11, 6)) == "День Конституции Республики Татарстан"
    assert get_rt_holiday_name(date(2026, 12, 31)) == "Перенесённый выходной"


@pytest.mark.django_db
def test_absence_form_uses_last_name_first_name(employee):
    form = EmployeeAbsenceForm()
    label = form.fields["user"].label_from_instance(employee)
    assert label == "Иванов Иван"


@pytest.mark.django_db
def test_workload_timeline_has_visual_absence_row(manager, employee):
    EmployeeAbsence.objects.create(
        user=employee,
        start_date=date(2026, 10, 12),
        end_date=date(2026, 10, 16),
        reason="Отпуск",
        created_by=manager,
    )

    rows = get_workload_timeline(date(2026, 10, 1), date(2026, 10, 31))
    row = next(item for item in rows if item.workload.user.id == employee.id)

    assert row.has_absences is True
    absence_cells = [cell for cell in row.absence_cells if cell.kind == "absence"]
    assert len(absence_cells) == 1
    assert absence_cells[0].absence.reason == "Отпуск"
    assert absence_cells[0].colspan == 5


@pytest.mark.django_db
def test_workload_page_marks_rt_holiday(client, manager):
    client.force_login(manager)
    response = client.get(reverse("workload_timeline"), {"year": 2026, "month": 3})
    content = response.content.decode()
    assert response.status_code == 200
    assert "Ураза-байрам" in content
    assert "Праздник / дополнительный выходной РТ" in content


@pytest.mark.django_db
def test_absence_page_displays_surname_then_name(client, manager, employee):
    EmployeeAbsence.objects.create(
        user=employee,
        start_date=date(2026, 10, 21),
        end_date=date(2026, 10, 22),
        created_by=manager,
    )
    client.force_login(manager)
    response = client.get(reverse("absences"))
    assert response.status_code == 200
    assert "Иванов Иван" in response.content.decode()


@pytest.mark.django_db
def test_employee_can_change_own_password(client, employee):
    client.force_login(employee)
    response = client.post(
        reverse("password_change"),
        {
            "old_password": "pass12345",
            "new_password1": "NewStrongPassword-2026!",
            "new_password2": "NewStrongPassword-2026!",
        },
    )
    assert response.status_code == 302
    employee.refresh_from_db()
    assert employee.check_password("NewStrongPassword-2026!")


@pytest.mark.django_db
def test_staff_user_sees_admin_link(client, manager):
    manager.is_staff = True
    manager.save(update_fields=["is_staff"])
    client.force_login(manager)

    response = client.get(reverse("home"), follow=True)
    content = response.content.decode()
    assert "Администрирование" in content
    assert reverse("admin:index") in content

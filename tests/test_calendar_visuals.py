from datetime import date

import pytest
from django.urls import reverse

from tasks.models import WorkCalendarDay


@pytest.mark.django_db
def test_calendar_marks_admin_non_working_day(client, manager):
    WorkCalendarDay.objects.create(
        date=date(2027, 2, 10),
        is_working_day=False,
        name="Дополнительный выходной РТ",
    )
    client.force_login(manager)
    response = client.get(reverse("calendar"), {"year": 2027, "month": 2})
    content = response.content.decode()
    assert response.status_code == 200
    assert "production-holiday" in content
    assert "Дополнительный выходной РТ" in content


@pytest.mark.django_db
def test_workload_marks_rt_holiday_column(client, manager):
    client.force_login(manager)
    response = client.get(reverse("workload_timeline"), {"year": 2026, "month": 11})
    content = response.content.decode()
    assert response.status_code == 200
    assert "timeline-date-col holiday" in content
    assert "День Конституции Республики Татарстан" in content

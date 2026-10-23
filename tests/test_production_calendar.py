from datetime import date

import pytest
from django.contrib import admin

from tasks.holidays import get_rt_calendar_map
from tasks.models import WorkCalendarDay


@pytest.mark.django_db
def test_regular_weekend_is_non_working_and_highlighted():
    day = date(2027, 1, 16)  # Saturday
    info = get_rt_calendar_map(day, day)[day]
    assert info.is_weekend is True
    assert info.is_non_working is True
    assert info.is_working_override is False


@pytest.mark.django_db
def test_admin_override_can_make_weekend_working():
    day = date(2027, 1, 16)
    WorkCalendarDay.objects.create(
        date=day,
        is_working_day=True,
        name="Рабочий день по переносу",
    )
    info = get_rt_calendar_map(day, day)[day]
    assert info.is_weekend is False
    assert info.is_holiday is False
    assert info.is_non_working is False
    assert info.is_working_override is True
    assert info.name == "Рабочий день по переносу"


@pytest.mark.django_db
def test_admin_override_adds_rt_non_working_day():
    day = date(2027, 3, 10)
    WorkCalendarDay.objects.create(
        date=day,
        is_working_day=False,
        name="Ураза-байрам",
    )
    info = get_rt_calendar_map(day, day)[day]
    assert info.is_holiday is True
    assert info.is_non_working is True
    assert info.name == "Ураза-байрам"
    assert info.source == "admin"


@pytest.mark.django_db
def test_work_calendar_is_registered_in_admin():
    assert WorkCalendarDay in admin.site._registry

from dataclasses import dataclass
from datetime import date, timedelta

from .models import WorkCalendarDay

# Official Republic of Tatarstan production calendar for 2026.
# This remains a fallback for the already verified year. For later years,
# transferred days off, religious holidays and working weekends are maintained
# through WorkCalendarDay in Django Admin.
RT_HOLIDAYS_2026 = {
    date(2026, 1, 1): "Новогодние каникулы",
    date(2026, 1, 2): "Новогодние каникулы",
    date(2026, 1, 3): "Новогодние каникулы",
    date(2026, 1, 4): "Новогодние каникулы",
    date(2026, 1, 5): "Новогодние каникулы",
    date(2026, 1, 6): "Новогодние каникулы",
    date(2026, 1, 7): "Рождество Христово",
    date(2026, 1, 8): "Новогодние каникулы",
    date(2026, 1, 9): "Перенесённый выходной",
    date(2026, 2, 23): "День защитника Отечества",
    date(2026, 3, 8): "Международный женский день",
    date(2026, 3, 9): "Перенос выходного за 8 марта",
    date(2026, 3, 20): "Ураза-байрам",
    date(2026, 5, 1): "Праздник Весны и Труда",
    date(2026, 5, 9): "День Победы",
    date(2026, 5, 11): "Перенос выходного за 9 мая",
    date(2026, 5, 27): "Курбан-байрам",
    date(2026, 6, 12): "День России",
    date(2026, 8, 30): "День Республики Татарстан",
    date(2026, 11, 4): "День народного единства",
    date(2026, 11, 6): "День Конституции Республики Татарстан",
    date(2026, 12, 31): "Перенесённый выходной",
}

# Fixed-date public holidays are useful as a safe fallback for future years.
# Year-specific transfers/religious holidays are explicit WorkCalendarDay records.
RECURRING_HOLIDAYS = {
    (1, 1): "Новогодние каникулы",
    (1, 2): "Новогодние каникулы",
    (1, 3): "Новогодние каникулы",
    (1, 4): "Новогодние каникулы",
    (1, 5): "Новогодние каникулы",
    (1, 6): "Новогодние каникулы",
    (1, 7): "Рождество Христово",
    (1, 8): "Новогодние каникулы",
    (2, 23): "День защитника Отечества",
    (3, 8): "Международный женский день",
    (5, 1): "Праздник Весны и Труда",
    (5, 9): "День Победы",
    (6, 12): "День России",
    (8, 30): "День Республики Татарстан",
    (11, 4): "День народного единства",
    (11, 6): "День Конституции Республики Татарстан",
}


@dataclass(frozen=True)
class CalendarDayInfo:
    date: date
    is_weekend: bool
    is_holiday: bool
    is_non_working: bool
    is_working_override: bool
    name: str | None
    source: str


def get_rt_holiday_name(day: date) -> str | None:
    if day.year == 2026:
        return RT_HOLIDAYS_2026.get(day)
    return RECURRING_HOLIDAYS.get((day.month, day.day))


def get_rt_calendar_map(range_start: date, range_end: date) -> dict[date, CalendarDayInfo]:
    """Return effective production-calendar data for every date in a range.

    Priority: explicit admin override -> verified/fixed holiday fallback -> weekend -> working day.
    An explicit working-day record can therefore turn a Saturday/Sunday into a working day.
    """
    overrides = {
        item.date: item
        for item in WorkCalendarDay.objects.filter(date__range=(range_start, range_end))
    }
    result = {}
    current = range_start
    while current <= range_end:
        override = overrides.get(current)
        natural_weekend = current.weekday() >= 5
        fallback_name = get_rt_holiday_name(current)

        if override is not None:
            if override.is_working_day:
                result[current] = CalendarDayInfo(
                    date=current,
                    is_weekend=False,
                    is_holiday=False,
                    is_non_working=False,
                    is_working_override=natural_weekend or fallback_name is not None,
                    name=override.name or "Рабочий день по производственному календарю",
                    source="admin",
                )
            else:
                result[current] = CalendarDayInfo(
                    date=current,
                    is_weekend=natural_weekend,
                    is_holiday=True,
                    is_non_working=True,
                    is_working_override=False,
                    name=override.name or fallback_name or "Нерабочий день по производственному календарю",
                    source="admin",
                )
        elif fallback_name is not None:
            result[current] = CalendarDayInfo(
                date=current,
                is_weekend=natural_weekend,
                is_holiday=True,
                is_non_working=True,
                is_working_override=False,
                name=fallback_name,
                source="fallback",
            )
        elif natural_weekend:
            result[current] = CalendarDayInfo(
                date=current,
                is_weekend=True,
                is_holiday=False,
                is_non_working=True,
                is_working_override=False,
                name="Выходной день",
                source="weekend",
            )
        else:
            result[current] = CalendarDayInfo(
                date=current,
                is_weekend=False,
                is_holiday=False,
                is_non_working=False,
                is_working_override=False,
                name=None,
                source="default",
            )
        current += timedelta(days=1)
    return result

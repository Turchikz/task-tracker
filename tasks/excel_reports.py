"""Human-readable Excel management reports generated from trusted server data."""
from io import BytesIO
import xlsxwriter

from django.db.models import Q
from django.utils import timezone

from .models import Task
from .services import get_manager_analytics, get_workload_ranking


def build_manager_excel(date_from, date_to):
    """Return an .xlsx document; users' strings are written as text, never formulas."""
    output = BytesIO()
    book = xlsxwriter.Workbook(output, {"in_memory": True, "strings_to_formulas": False, "strings_to_urls": False})
    title = book.add_format({"bold": True, "font_size": 17, "font_color": "#1E3A5F"})
    header = book.add_format({"bold": True, "bg_color": "#E9F1F9", "font_color": "#243449", "border": 0, "bottom": 1, "bottom_color": "#9EB5CE"})
    date_format = book.add_format({"num_format": "dd.mm.yyyy"})
    wrap = book.add_format({"text_wrap": True, "valign": "top"})
    analytics = get_manager_analytics(date_from, date_to)
    ranks = get_workload_ranking()

    def header_row(sheet, labels, widths):
        for col, (label, width) in enumerate(zip(labels, widths)):
            sheet.write_string(0, col, label, header)
            sheet.set_column(col, col, width)
        sheet.freeze_panes(1, 0)
        sheet.autofilter(0, 0, 0, len(labels) - 1)

    overview = book.add_worksheet("Обзор")
    overview.set_column("A:A", 34)
    overview.set_column("B:B", 18)
    overview.write_string("A1", "RaTracker · отчёт отдела", title)
    overview.write_string("A3", "Период")
    overview.write_string("B3", f"{date_from:%d.%m.%Y} — {date_to:%d.%m.%Y}")
    metrics = [
        ("Создано", analytics["created"]),
        ("Выполнено", analytics["completed"]),
        ("Выполнено в срок", analytics["on_time"]),
        ("Процент в срок", analytics["on_time_rate"]),
        ("С опозданием", analytics["late"]),
        ("Возвратов на доработку", analytics["revisions"]),
        ("Просрочено сейчас", analytics["current_overdue"]),
    ]
    for index, (name, value) in enumerate(metrics, 4):
        overview.write_string(index, 0, name)
        if value is None: overview.write_string(index, 1, "—")
        else: overview.write_number(index, 1, value)
    overview.write_string(13, 0, "Время выполнения, среднее (ч)")
    if analytics["avg_cycle_hours"] is not None:
        overview.write_number(13, 1, analytics["avg_cycle_hours"])

    employees = book.add_worksheet("Сотрудники")
    header_row(employees, ["Сотрудник", "Выполнено", "В срок", "В срок, %", "Доработки", "Цикл, ч"], [34, 16, 14, 16, 16, 16])
    for i, row in enumerate(analytics["employees"], 1):
        employees.write_string(i, 0, row["user"].get_full_name() or row["user"].username)
        for j, key in enumerate(["completed", "on_time", "on_time_rate", "revisions", "avg_cycle_hours"], 1):
            value = row[key]
            if value is not None: employees.write_number(i, j, value)
    employees.autofilter(0, 0, max(1, len(analytics["employees"])), 5)

    tasks_ws = book.add_worksheet("Задачи")
    labels = ["ID", "Задача", "Статус", "Приоритет", "Основной", "Все исполнители", "Ответственный", "Начало", "Срок", "Создана", "Завершена"]
    header_row(tasks_ws, labels, [9, 55, 19, 18, 30, 60, 30, 16, 16, 16, 16])
    tasks = Task.objects.filter(
        Q(created_at__date__range=(date_from, date_to))
        | Q(completed_at__date__range=(date_from, date_to))
        | Q(due_date__range=(date_from, date_to))
    ).distinct().select_related("assigned_to", "responsible_manager", "created_by").prefetch_related("additional_assignees")
    count = 0
    for i, task in enumerate(tasks.order_by("pk").iterator(chunk_size=200), 1):
        count += 1
        manager = task.responsible_manager or task.created_by
        tasks_ws.write_number(i, 0, task.pk)
        for col, value in [(1, task.title), (2, task.get_status_display()), (3, task.get_priority_display()),
                           (4, task.assigned_to.get_full_name() or task.assigned_to.username),
                           (5, task.team_names), (6, manager.get_full_name() or manager.username)]:
            tasks_ws.write_string(i, col, value, wrap if col in (1,5) else None)
        for col, value in [(7, task.start_date), (8, task.due_date),
                           (9, timezone.localtime(task.created_at).date()),
                           (10, timezone.localtime(task.completed_at).date() if task.completed_at else None)]:
            if value: tasks_ws.write_datetime(i, col, value, date_format)
    tasks_ws.autofilter(0, 0, max(1, count), len(labels) - 1)

    load = book.add_worksheet("Текущая загрузка")
    header_row(load, ["Сотрудник", "Балл", "Активных", "Срочных", "До 3 дней", "Просрочено", "Отсутствует до"], [36, 14, 14, 14, 17, 17, 21])
    for i, row in enumerate(ranks, 1):
        load.write_string(i, 0, row.user.get_full_name() or row.user.username)
        for col, value in enumerate([row.score, row.active_count, row.urgent_count, row.due_soon_count, row.overdue_count], 1):
            load.write_number(i, col, value)
        if row.absence: load.write_datetime(i, 6, row.absence.end_date, date_format)
    load.autofilter(0, 0, max(1, len(ranks)), 6)
    book.close()
    return output.getvalue()

"""Styled workload export using the application's existing XLSX engine."""
import calendar
from copy import copy
from datetime import timedelta
from io import BytesIO

import xlsxwriter
from django.utils import timezone

from .holidays import get_rt_calendar_map
from .models import EmployeeAbsence, Task
from .services import (WorkloadRow, WorkloadTimelineRow, build_absence_cells,
                       build_timeline_lanes, get_workload_ranking, task_planned_span)


def local_date(value):
    return timezone.localtime(value).date() if value else None


def export_rows(tasks, ranking, start, end):
    """Include former employees, and actual completions outside planned dates."""
    by_user = {w.user.pk: [] for w in ranking}
    users = {w.user.pk: w.user for w in ranking}
    for task in tasks:
        for member in task.team_members:
            users[member.pk] = member
            by_user.setdefault(member.pk, []).append(task)
    ranks = list(ranking) + [WorkloadRow(user=u, score=0, active_count=0,
        urgent_count=0, due_soon_count=0, overdue_count=0)
        for pk, u in users.items() if pk not in {w.user.pk for w in ranking}]
    absence_map = {}
    for absence in EmployeeAbsence.objects.filter(start_date__lte=end, end_date__gte=start):
        absence_map.setdefault(absence.user_id, []).append(absence)
    for workload in ranks:
        user_tasks = by_user[workload.user.pk]
        visual_tasks = []
        for task in user_tasks:
            span = task_planned_span(task)
            if span and span[0] <= end and span[1] >= start:
                visual_tasks.append(task)
            elif task.status == Task.Status.DONE and task.completed_at and start <= local_date(task.completed_at) <= end:
                marker = copy(task)
                marker.start_date = marker.due_date = local_date(task.completed_at)
                marker.title = f"Завершена: {task.title}"
                visual_tasks.append(marker)
        lanes = build_timeline_lanes(visual_tasks, start, end)
        absences = absence_map.get(workload.user.pk, [])
        yield WorkloadTimelineRow(workload, lanes, sum(t.due_date is None for t in user_tasks),
            build_absence_cells(absences, start, end), bool(absences), len(lanes) + bool(absences))


def build_workload_excel(start, end, base_url=""):
    output = BytesIO()
    book = xlsxwriter.Workbook(output, {
        "in_memory": True, "strings_to_formulas": False, "strings_to_urls": False,
    })
    common = {"font_name": "Calibri", "font_size": 11, "valign": "vcenter",
              "border": 1, "border_color": "#D1D5DB"}
    cache = {}

    def fmt(**props):
        key = tuple(sorted(props.items()))
        if key not in cache:
            cache[key] = book.add_format({**common, **props})
        return cache[key]

    header = fmt(bg_color="#172033", font_color="#FFFFFF", bold=True, text_wrap=True)
    text = fmt(text_wrap=True)
    dates = fmt(num_format="dd.mm.yyyy")
    muted = fmt(bg_color="#F3F4F6", font_color="#6B7280", text_wrap=True)
    title = fmt(bg_color="#172033", font_color="#FFFFFF", bold=True, font_size=18)

    def merge(sheet, r1, c1, r2, c2, value, style):
        if r1 == r2 and c1 == c2:
            sheet.write(r1, c1, value, style)
        else:
            sheet.merge_range(r1, c1, r2, c2, value, style)

    def setup(sheet):
        sheet.hide_gridlines(2)
        sheet.set_landscape()
        sheet.set_paper(8)
        sheet.fit_to_pages(1, 0)
        sheet.set_margins(.25, .25, .35, .35)
        sheet.set_footer("&CRaTracker — &P / &N")

    # Use the same planned intervals as the site; undated tasks cannot be
    # assigned to a period, so keep them explicitly marked in the register.
    tasks = []
    for task in Task.objects.select_related(
        "assigned_to", "responsible_manager", "created_by"
    ).prefetch_related("additional_assignees").order_by("pk"):
        span = task_planned_span(task)
        created = start <= local_date(task.created_at) <= end
        completed = task.status == Task.Status.DONE and task.completed_at and start <= local_date(task.completed_at) <= end
        if span is None or created or completed or (span[0] <= end and span[1] >= start):
            tasks.append(task)

    summary = book.add_worksheet("Итоги отдела")
    setup(summary)
    summary.set_column(0, 0, 38)
    summary.set_column(1, 6, 19)
    summary.merge_range(0, 0, 0, 6, "RaTracker — результаты работы отдела", title)
    summary.set_row(0, 36)
    summary.merge_range(1, 0, 1, 6, f"Отчётный период: {start:%d.%m.%Y} — {end:%d.%m.%Y}", text)
    summary.merge_range(2, 0, 2, 6, "Завершение учитывается по фактической дате. Исполнители и статусы — на момент выгрузки; история состава команды не восстанавливается.", muted)
    summary.set_row(2, 32)
    done = [t for t in tasks if t.status == Task.Status.DONE and t.completed_at and start <= local_date(t.completed_at) <= end]
    def on_time(t):
        return t.due_date is not None and local_date(t.completed_at) <= t.due_date
    with_due = [t for t in done if t.due_date]
    ontime = sum(on_time(t) for t in done)
    metrics = [
        ("Создано за период", sum(start <= local_date(t.created_at) <= end for t in tasks)),
        ("Выполнено за период", len(done)),
        ("Выполнено в срок", ontime),
        ("Выполнено с опозданием", len(with_due) - ontime),
        ("Выполнено без срока", len(done) - len(with_due)),
        ("Доля в срок (из выполненных со сроком)", ontime / len(with_due) if with_due else None),
    ]
    for r, (label, value) in enumerate(metrics, 4):
        summary.write_string(r, 0, label, text)
        summary.write(r, 1, value if value is not None else "Нет задач со сроком", fmt(bold=True, num_format="0.0%" if r == 9 else "0", text_wrap=True))
        summary.set_row(r, 30)
    summary.merge_range(11, 0, 11, 6, "Совместная задача считается один раз в итоге отдела и у каждого её исполнителя в таблице ниже. Сумма по сотрудникам может быть больше итога отдела.", muted)
    summary.set_row(11, 32)
    labels_summary = ["Сотрудник", "Выполнено", "В срок", "С опозданием", "Без срока", "Доля в срок", "Статус сотрудника"]
    for c, label in enumerate(labels_summary):
        summary.write_string(13, c, label, header)
    summary.set_row(13, 32)
    ranking = get_workload_ranking()
    users = {w.user.pk: w.user for w in ranking}
    done_by_user = {}
    for task in tasks:
        for member in task.team_members:
            users[member.pk] = member
    for task in done:
        for member in task.team_members:
            done_by_user.setdefault(member.pk, []).append(task)
    sorted_users = sorted(users.values(), key=lambda u: (-len(done_by_user.get(u.pk, [])), u.get_full_name() or u.username))
    for r, user in enumerate(sorted_users, 14):
        personal = done_by_user.get(user.pk, [])
        dated = sum(t.due_date is not None for t in personal)
        timely = sum(on_time(t) for t in personal)
        values = [user.get_full_name() or user.username, len(personal), timely,
                  dated - timely, len(personal) - dated, timely / dated if dated else None,
                  "Активен" if user.is_active else "Неактивен"]
        for c, value in enumerate(values):
            summary.write(r, c, value if value is not None else "—", fmt(num_format="0.0%" if c == 5 else "General", text_wrap=True))
        summary.set_row(r, 30)
    summary.autofilter(13, 0, max(13, len(sorted_users) + 13), 6)
    summary.freeze_panes(14, 1)

    register = book.add_worksheet("Все задачи")
    setup(register)
    labels = ["ID", "Задача", "Статус", "Приоритет", "Основной исполнитель",
              "Все исполнители", "Руководитель", "Начало", "Срок", "Трудоёмкость", "Период", "Создана", "Выполнена"]
    widths = [9, 55, 20, 16, 30, 48, 30, 15, 15, 20, 45, 15, 15]
    register.merge_range(0, 0, 0, 12, "RaTracker — загрузка сотрудников", title)
    register.set_row(0, 34)
    register.merge_range(1, 0, 1, 12, f"{start:%d.%m.%Y} — {end:%d.%m.%Y}. Все статусы; одна строка на задачу.", text)
    register.merge_range(2, 0, 2, 12, "Отбор: пересечение плана, создание или выполнение в периоде. Без срока: включены независимо от периода; на сетке отмечается фактическое завершение, если оно есть.", muted)
    register.set_row(2, 32)
    for c, (label, width) in enumerate(zip(labels, widths)):
        register.set_column(c, c, width)
        register.write_string(4, c, label, header)
    register.set_row(4, 30)
    for r, task in enumerate(tasks, 5):
        manager = task.responsible_manager or task.created_by
        values = [task.pk, task.title, task.get_status_display(), task.get_priority_display(),
                  task.assigned_to.get_full_name() or task.assigned_to.username,
                  task.team_names, manager.get_full_name() or manager.username,
                  task.start_date, task.due_date, task.get_effort_display(),
                  "Без срока — вне привязки к периоду" if not task.due_date else "План / создание / выполнение в периоде",
                  local_date(task.created_at), local_date(task.completed_at)]
        register.set_row(r, 42)
        for c, value in enumerate(values):
            if value is not None:
                register.write(r, c, value, dates if c in (7, 8, 11, 12) else text)
        if base_url:
            register.write_url(r, 0, f"{base_url}/tasks/{task.pk}/", text, str(task.pk))
    register.freeze_panes(5, 2)
    register.autofilter(4, 0, max(4, len(tasks) + 4), 12)
    register.repeat_rows(4)

    cursor = start
    while cursor <= end:
        stop = min(end, cursor.replace(day=calendar.monthrange(cursor.year, cursor.month)[1]))
        days = (stop - cursor).days + 1
        sheet = book.add_worksheet(f"План {cursor:%Y-%m}")
        setup(sheet)
        sheet.set_column(0, 0, 5)
        sheet.set_column(1, 1, 36)
        sheet.set_column(2, 2, 9)
        sheet.set_column(3, days + 2, 7)
        sheet.merge_range(0, 0, 0, days + 2, "RaTracker — загрузка сотрудников", title)
        sheet.set_row(0, 34)
        sheet.merge_range(1, 0, 1, days + 2, f"{cursor:%d.%m.%Y} — {stop:%d.%m.%Y}. Все задачи. Балл и счётчики — текущие, на {timezone.localdate():%d.%m.%Y}.", text)
        sheet.set_row(1, 48 if days < 7 else 30)
        sheet.merge_range(2, 0, 2, days + 2, "Серый — выходной; оранжевый — праздник / отсутствие; зелёный — рабочий выходной. Завершённые задачи — серые. Короткие полосы: ID задачи; полное название — на листе «Все задачи». Отметка «Завершена» вне плана — фактическая дата.", muted)
        sheet.set_row(2, 80 if days < 7 else 44)
        for c, label in enumerate(["#", "Сотрудник", "Балл"]):
            sheet.write(4, c, label, header)
        cal = get_rt_calendar_map(cursor, stop)
        backgrounds = []
        for i in range(days):
            day = cursor + timedelta(days=i)
            info = cal[day]
            bg = "#FFEDD5" if info.is_holiday else "#DCFCE7" if info.is_working_override else "#E5EBF2" if info.is_weekend else "#FFFFFF"
            backgrounds.append(fmt(bg_color=bg))
            label = f"{day:%d.%m}\n{['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс'][day.weekday()]}"
            sheet.write_string(4, i + 3, label, fmt(bg_color=bg, bold=True, align="center", text_wrap=True))
        sheet.set_row(4, 34)
        row_number = 5
        for rank, row in enumerate(export_rows(tasks, ranking, cursor, stop), 1):
            first = row_number
            lanes = ([row.absence_cells] if row.has_absences else []) + row.lanes
            for lane in lanes:
                height = 54
                for i, style in enumerate(backgrounds):
                    sheet.write_blank(row_number, i + 3, None, style)
                col = 3
                for cell in lane:
                    if cell.kind == "absence":
                        a = cell.absence
                        label = f"{a.reason or 'Отсутствие'} {a.start_date:%d.%m}–{a.end_date:%d.%m}"
                        height = max(height, ((len(label) + cell.colspan * 6 - 1) // (cell.colspan * 6)) * 15 + 8)
                        style = fmt(bg_color="#FFEDD5", font_color="#9A3412", text_wrap=True, align="center")
                        merge(sheet, row_number, col, row_number, col + cell.colspan - 1, label, style)
                    elif cell.kind == "task":
                        task = cell.task
                        label = f"#{task.pk}" if cell.colspan < 3 else f"#{task.pk} {task.title}"
                        height = max(height, ((len(label) + cell.colspan * 6 - 1) // (cell.colspan * 6)) * 15 + 8)
                        bg = {"low": "#E0F2FE", "normal": "#E5E7EB", "high": "#FEF3C7", "urgent": "#FEE2E2"}.get(task.priority, "#E5E7EB")
                        history = task.status in (Task.Status.DONE, Task.Status.CANCELLED)
                        if task.status == Task.Status.REVIEW:
                            bg = "#EDE9FE"
                        style = fmt(bg_color="#F3F4F6" if history else bg,
                                    font_color="#6B7280" if history else "#1F2937",
                                    border=3 if task.status == Task.Status.NEW else 1,
                                    border_color="#B91C1C" if task.deadline_state == "overdue" else "#9CA3AF",
                                    text_wrap=True, align="center", font_strikeout=task.status == Task.Status.CANCELLED)
                        merge(sheet, row_number, col, row_number, col + cell.colspan - 1, label, style)
                        if base_url:
                            sheet.write_url(row_number, col, f"{base_url}/tasks/{task.pk}/", style, label)
                    col += cell.colspan
                sheet.set_row(row_number, min(409, height))
                row_number += 1
            w = row.workload
            last = row_number - 1
            merge(sheet, first, 0, last, 0, rank, fmt(bold=True, align="center"))
            name = w.user.get_full_name() or w.user.username
            label = f"{name}\n{w.active_count} активных · {w.due_soon_count} до 3 дней · {w.overdue_count} просрочено"
            if row.no_due_count:
                label += f"\n{row.no_due_count} без срока"
            merge(sheet, first, 1, last, 1, label, text)
            bg = {"low": "#DCFCE7", "moderate": "#FEF3C7", "high": "#FEE2E2", "absent": "#FFEDD5"}[w.load_level]
            merge(sheet, first, 2, last, 2, w.score, fmt(bg_color=bg, bold=True, align="center"))
        if row_number == 5:
            sheet.write_string(5, 1, "Нет активных сотрудников", text)
        sheet.freeze_panes(5, 3)
        sheet.repeat_rows(0, 4)
        sheet.repeat_columns(0, 2)
        sheet.print_area(0, 0, max(5, row_number - 1), days + 2)
        cursor = stop + timedelta(days=1)
    # Management summary first, then calendars, then searchable details.
    sheets = book.worksheets_objs
    sheets.append(sheets.pop(1))
    sheets[0].activate()
    book.close()
    return output.getvalue()

from datetime import date, datetime
from io import BytesIO
from zipfile import ZipFile
from xml.etree import ElementTree as ET

import pytest
from django.urls import reverse
from django.utils import timezone

from tasks.models import EmployeeAbsence, Task
from tasks.workload_export import build_workload_excel


def read_book(content):
    z = ZipFile(BytesIO(content))
    ns = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    strings = ["".join(e.itertext()) for e in ET.fromstring(z.read("xl/sharedStrings.xml")).findall("m:si", ns)]
    workbook = ET.fromstring(z.read("xl/workbook.xml"))
    names = [e.attrib["name"] for e in workbook.findall("m:sheets/m:sheet", ns)]
    sheets = []
    for i, name in enumerate(names, 1):
        root = ET.fromstring(z.read(f"xl/worksheets/sheet{i}.xml"))
        values = {}
        for cell in root.findall(".//m:sheetData/m:row/m:c", ns):
            value = cell.find("m:v", ns)
            if value is not None:
                values[cell.attrib["r"]] = strings[int(value.text)] if cell.attrib.get("t") == "s" else value.text
        sheets.append((name, values, root))
    return sheets, z, ns


@pytest.mark.django_db
def test_export_completed_tasks_actual_dates_and_team(manager, employee, second_employee):
    task = Task.objects.create(title='=HYPERLINK("bad")', created_by=manager, assigned_to=employee,
        start_date=date(2026, 8, 1), due_date=date(2026, 8, 10), status=Task.Status.DONE)
    task.additional_assignees.add(second_employee)
    Task.objects.filter(pk=task.pk).update(completed_at=timezone.make_aware(datetime(2026, 10, 3, 12)),
        created_at=timezone.make_aware(datetime(2026, 8, 1, 12)))
    second_employee.is_active = False
    second_employee.save()
    EmployeeAbsence.objects.create(user=employee, start_date=date(2026, 10, 2), end_date=date(2026, 10, 4), reason="Отпуск")
    undated = Task.objects.create(title="Без срока", created_by=manager, assigned_to=employee)
    Task.objects.create(title="Вне периода", created_by=manager, assigned_to=employee,
        due_date=date(2026, 12, 1))
    content = build_workload_excel(date(2026, 9, 30), date(2026, 10, 5), "https://example.test")
    sheets, z, ns = read_book(content)
    assert [s[0] for s in sheets] == ["Итоги отдела", "План 2026-09", "План 2026-10", "Все задачи"]
    summary = sheets[0][1]
    assert summary["B6"] == "1"  # Unique department total.
    assert summary["B8"] == "1"  # Late completion in report period.
    assert summary["B15"] == summary["B16"] == "1"  # Both team members.
    register = sheets[-1][1]
    assert task.title in register.values()
    assert undated.title in register.values()
    assert "Вне периода" not in register.values()
    assert f"#{task.pk}" in sheets[2][1].values()  # Actual completion outside plan.
    assert "Отпуск 02.10–04.10" in sheets[2][1].values()
    assert sheets[2][2].find("m:sheetViews/m:sheetView/m:pane", ns).attrib["topLeftCell"] == "D6"
    assert all(not s[2].findall(".//m:f", ns) for s in sheets)  # User titles are literal text.
    assert z.testzip() is None


@pytest.mark.django_db
def test_export_permissions_and_validation(client, manager, employee):
    url = reverse("workload_export")
    assert client.get(url).status_code == 302
    client.force_login(employee)
    assert client.get(url, {"from": "2026-10-01", "to": "2026-10-31"}).status_code == 403
    client.force_login(manager)
    for query in [{}, {"from": "bad", "to": "2026-10-31"}, {"from": "2026-11-01", "to": "2026-10-31"}]:
        assert client.get(url, query).status_code == 302
    response = client.get(url, {"from": "2026-10-01", "to": "2026-10-01"})
    assert response.status_code == 200
    assert response["Content-Type"].endswith("spreadsheetml.sheet")
    assert response["Cache-Control"] == "private, no-store"
    assert read_book(response.content)[0][0][0] == "Итоги отдела"
    page = client.get(reverse("workload_timeline"))
    assert b'workload/export/' in page.content

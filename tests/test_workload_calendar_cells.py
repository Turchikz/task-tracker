from datetime import date

from tasks.models import EmployeeAbsence
from tasks.services import _timeline_cells, build_absence_cells, build_timeline_lanes


def test_blank_timeline_uses_one_cell_per_day():
    cells = _timeline_cells([], date(2027, 1, 1), date(2027, 1, 31))

    assert len(cells) == 31
    assert all(cell.kind == "blank" for cell in cells)
    assert all(cell.colspan == 1 for cell in cells)


def test_empty_workload_lane_uses_one_cell_per_day():
    lanes = build_timeline_lanes([], date(2026, 11, 1), date(2026, 11, 30))

    assert len(lanes) == 1
    assert len(lanes[0]) == 30
    assert all(cell.colspan == 1 for cell in lanes[0])


def test_absence_blank_periods_do_not_span_multiple_calendar_columns():
    absence = EmployeeAbsence(
        start_date=date(2026, 10, 19),
        end_date=date(2026, 10, 21),
        reason="Отпуск",
    )

    cells = build_absence_cells(
        [absence],
        date(2026, 10, 1),
        date(2026, 10, 31),
    )

    blank_cells = [cell for cell in cells if cell.kind == "blank"]
    absence_cells = [cell for cell in cells if cell.kind == "absence"]

    assert len(blank_cells) == 28
    assert all(cell.colspan == 1 for cell in blank_cells)
    assert len(absence_cells) == 1
    assert absence_cells[0].colspan == 3

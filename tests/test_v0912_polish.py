from datetime import date

import pytest
from django.contrib.auth.models import Group, User
from django.urls import reverse

from tasks.constants import EMPLOYEES_GROUP
from tasks.models import EmployeeAbsence, FeatureIdea, FeatureVote


@pytest.mark.django_db
def test_split_vote_bar_and_separate_electorate_threshold(client, manager, employee, second_employee):
    idea = FeatureIdea.objects.create(title="Идея", description="Нужное улучшение", author=manager)
    group = Group.objects.get(name=EMPLOYEES_GROUP)
    others = [User.objects.create_user(username=f"voter{i}") for i in range(3)]
    for user in others:
        user.groups.add(group)
    FeatureVote.objects.create(idea=idea, user=employee, choice=True)
    FeatureVote.objects.create(idea=idea, user=second_employee, choice=False)
    FeatureVote.objects.create(idea=idea, user=others[0], choice=True)
    FeatureVote.objects.create(idea=idea, user=others[1], choice=False)
    assert idea.vote_ratio_percent == 50
    assert idea.approval_percent == 40
    client.force_login(employee)
    page = client.get(reverse("feature_ideas")).content.decode()
    assert 'class="idea-progress-yes" style="width:50.0%"' in page
    assert 'class="idea-progress-no"' in page
    assert "Среди голосов: 50" in page
    assert "Поддержка от всех сотрудников: 40" in page

    FeatureVote.objects.filter(idea=idea, user=second_employee).update(choice=True)
    assert idea.vote_ratio_percent == 75
    FeatureVote.objects.filter(idea=idea).delete()
    assert idea.vote_ratio_percent == 0
    assert 'пока нет голосов' in client.get(reverse("feature_ideas")).content.decode()


@pytest.mark.django_db
def test_employee_calendar_lists_every_absent_colleague_without_manager_link(client, employee, second_employee):
    EmployeeAbsence.objects.create(user=employee, start_date=date(2026, 10, 20), end_date=date(2026, 10, 21))
    EmployeeAbsence.objects.create(user=second_employee, start_date=date(2026, 10, 20), end_date=date(2026, 10, 20))
    client.force_login(employee)
    response = client.get(reverse("calendar"), {"year": 2026, "month": 10})
    assert response.status_code == 200
    day = next(day for week in response.context["weeks"] for day in week if day["date"] == date(2026, 10, 20))
    assert {a.user_id for a in day["absences"]} == {employee.pk, second_employee.pk}
    content = response.content.decode()
    assert "Иван Иванов" in content and "Пётр Петров" in content
    assert "calendar-absences-agenda" in content
    assert 'Отсутствует с 20.10.2026 по 20.10.2026' in content

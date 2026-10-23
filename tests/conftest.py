import pytest
from django.contrib.auth.models import Group, User

from tasks.constants import EMPLOYEES_GROUP, MANAGERS_GROUP


@pytest.fixture
def manager(db):
    group, _ = Group.objects.get_or_create(name=MANAGERS_GROUP)
    user = User.objects.create_user(username="manager", password="pass12345", first_name="Анна", last_name="Руководитель")
    user.groups.add(group)
    return user


@pytest.fixture
def employee(db):
    group, _ = Group.objects.get_or_create(name=EMPLOYEES_GROUP)
    user = User.objects.create_user(username="employee", password="pass12345", first_name="Иван", last_name="Иванов")
    user.groups.add(group)
    return user


@pytest.fixture
def second_employee(db):
    group, _ = Group.objects.get_or_create(name=EMPLOYEES_GROUP)
    user = User.objects.create_user(username="employee2", password="pass12345", first_name="Пётр", last_name="Петров")
    user.groups.add(group)
    return user

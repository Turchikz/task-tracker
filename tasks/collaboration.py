"""Member readiness without changing the global task workflow."""
from .models import TaskMemberProgress


def team_progress(task):
    """Return [(user, state)] in same order as the task team."""
    states = {row.user_id: row.state for row in task.member_progress.all()}
    return [(user, states.get(user.pk, TaskMemberProgress.State.PENDING)) for user in task.team_members]


def all_members_ready(task):
    member_ids = {user.pk for user in task.team_members}
    if len(member_ids) < 2:
        return True  # Backward compatible with single-user tasks.
    ready_ids = set(task.member_progress.filter(
        user_id__in=member_ids, state=TaskMemberProgress.State.READY,
    ).values_list("user_id", flat=True))
    return ready_ids == member_ids


def change_member_progress(task, user, state):
    if not task.has_assignee(user):
        raise ValueError("Not a task member")
    return TaskMemberProgress.objects.update_or_create(
        task=task, user=user, defaults={"state": state}
    )[0]

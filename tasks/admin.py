from django.contrib import admin

from .models import (
    EmployeeAbsence,
    Notification,
    SavedTaskFilter,
    Task,
    TaskComment,
    TaskEvent,
    TaskImage,
    TaskHandover,
    TaskMemberProgress,
    TaskTemplate,
    WorkCalendarDay,
)
from .permissions import assignable_users, manager_users


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "assigned_to",
        "responsible_manager",
        "status",
        "priority",
        "effort",
        "start_date",
        "due_date",
        "updated_at",
    )
    list_filter = (
        "status",
        "priority",
        "effort",
        "assigned_to",
        "additional_assignees",
        "responsible_manager",
    )
    search_fields = (
        "title",
        "description",
        "assigned_to__username",
        "assigned_to__first_name",
        "assigned_to__last_name",
        "additional_assignees__username",
        "additional_assignees__first_name",
        "additional_assignees__last_name",
        "responsible_manager__username",
        "responsible_manager__first_name",
        "responsible_manager__last_name",
    )
    readonly_fields = (
        "created_by",
        "created_at",
        "updated_at",
        "started_at",
        "submitted_at",
        "completed_at",
        "revision_reason",
    )
    list_select_related = ("assigned_to", "created_by", "responsible_manager")
    filter_horizontal = ("additional_assignees",)
    date_hierarchy = "due_date"

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "assigned_to":
            kwargs["queryset"] = assignable_users()
        elif db_field.name == "responsible_manager":
            kwargs["queryset"] = manager_users()
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def formfield_for_manytomany(self, db_field, request, **kwargs):
        if db_field.name == "additional_assignees":
            kwargs["queryset"] = assignable_users()
        return super().formfield_for_manytomany(db_field, request, **kwargs)

    def save_model(self, request, obj, form, change):
        if not obj.created_by_id:
            obj.created_by = request.user
        if not obj.responsible_manager_id:
            obj.responsible_manager = request.user
        obj._change_actor = request.user
        super().save_model(request, obj, form, change)


@admin.register(TaskHandover)
class TaskHandoverAdmin(admin.ModelAdmin):
    list_display = ("task", "from_employee", "to_employee", "changed_by", "created_at", "reason")
    list_select_related = ("task", "from_employee", "to_employee", "changed_by")
    readonly_fields = ("task", "from_employee", "to_employee", "changed_by", "reason", "keep_previous", "created_at")
    def has_add_permission(self, request):
        return False
    def has_change_permission(self, request, obj=None):
        return False
    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(TaskTemplate)
class TaskTemplateAdmin(admin.ModelAdmin):
    list_display = ("name", "priority", "effort", "default_due_days", "is_active")
    list_filter = ("is_active", "priority", "effort")
    search_fields = ("name", "title", "description")


@admin.register(SavedTaskFilter)
class SavedTaskFilterAdmin(admin.ModelAdmin):
    list_display = ("name", "user", "updated_at")
    search_fields = ("name", "user__username", "user__first_name", "user__last_name")
    readonly_fields = ("created_at", "updated_at")
    list_select_related = ("user",)


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("user", "kind", "task", "notification_date", "read_at", "created_at")
    list_filter = ("kind", "notification_date", "read_at")
    search_fields = ("user__username", "task__title", "message")
    readonly_fields = ("created_at",)
    list_select_related = ("user", "task")


@admin.register(TaskEvent)
class TaskEventAdmin(admin.ModelAdmin):
    list_display = ("task", "kind", "actor", "created_at")
    list_filter = ("kind", "created_at")
    search_fields = ("task__title", "actor__username", "message")
    readonly_fields = ("task", "actor", "kind", "message", "from_status", "to_status", "created_at")
    list_select_related = ("task", "actor")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(TaskComment)
class TaskCommentAdmin(admin.ModelAdmin):
    list_display = ("task", "author", "created_at")
    search_fields = ("task__title", "author__username", "text")
    readonly_fields = ("task", "author", "text", "created_at")
    list_select_related = ("task", "author")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(TaskImage)
class TaskImageAdmin(admin.ModelAdmin):
    list_display = ("task", "original_name", "uploaded_by", "created_at")
    search_fields = ("task__title", "original_name", "uploaded_by__username")
    readonly_fields = ("task", "uploaded_by", "image", "original_name", "content_type", "created_at")
    list_select_related = ("task", "uploaded_by")

    def has_add_permission(self, request):
        return False


@admin.register(EmployeeAbsence)
class EmployeeAbsenceAdmin(admin.ModelAdmin):
    list_display = ("user", "start_date", "end_date", "reason", "created_by")
    list_filter = ("start_date", "end_date")
    search_fields = ("user__username", "user__first_name", "user__last_name", "reason")
    list_select_related = ("user", "created_by")


@admin.register(WorkCalendarDay)
class WorkCalendarDayAdmin(admin.ModelAdmin):
    list_display = ("date", "day_state", "name", "updated_at")
    list_filter = ("is_working_day", "date")
    search_fields = ("name",)
    date_hierarchy = "date"
    ordering = ("date",)
    actions = ("mark_as_working", "mark_as_non_working")

    @admin.display(description="Тип дня", ordering="is_working_day")
    def day_state(self, obj):
        return "Рабочий" if obj.is_working_day else "Нерабочий"

    @admin.action(description="Отметить выбранные дни рабочими")
    def mark_as_working(self, request, queryset):
        queryset.update(is_working_day=True)

    @admin.action(description="Отметить выбранные дни нерабочими")
    def mark_as_non_working(self, request, queryset):
        queryset.update(is_working_day=False)


@admin.register(TaskMemberProgress)
class TaskMemberProgressAdmin(admin.ModelAdmin):
    list_display = ("task", "user", "state", "updated_at")
    list_filter = ("state",)
    search_fields = ("task__title", "user__username", "user__first_name", "user__last_name")
    list_select_related = ("task", "user")

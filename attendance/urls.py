from django.urls import path
from django.views.generic.base import RedirectView
from . import views

# --- Core attendance ---
urlpatterns = [
    path('', views.home_redirect),
    path('dashboard/', RedirectView.as_view(pattern_name='employee_dashboard', permanent=False)),
    path('attendance/clock-in/', views.clock_in, name='clock_in'),
    path('attendance/clock-out/', views.clock_out, name='clock_out'),
    path('attendance/break-start/', views.break_start, name='break_start'),
    path('attendance/break-end/', views.break_end, name='break_end'),
    path('employee/dashboard/', views.employee_dashboard, name='employee_dashboard'),
    path('admin/dashboard/', views.admin_dashboard, name='admin_dashboard'),
    path('manager/dashboard/', views.manager_dashboard, name='manager_dashboard'),
    path('history/', views.attendance_history, name='attendance_history'),
    path('reports/', views.reports, name='reports'),
    path('export/csv/', views.export_csv, name='export_csv'),
    path('export/pdf/', views.export_pdf, name='export_pdf'),
    path('notifications/read/', views.mark_notifications_read, name='mark_notifications_read'),
    path('search/', views.global_search, name='global_search'),

    # --- Timer ---
    path('timer/start/<int:task_id>/', views.timer_start, name='timer_start'),
    path('timer/stop/', views.timer_stop, name='timer_stop'),
    path('timer/stop/<int:entry_id>/', views.timer_stop, name='timer_stop_entry'),

    # --- Clients ---
    path('clients/', views.client_list, name='client_list'),
    path('clients/add/', views.client_add, name='client_add'),
    path('clients/<int:client_id>/edit/', views.client_edit, name='client_edit'),
    path('clients/<int:client_id>/toggle/', views.client_toggle, name='client_toggle'),

    # --- Projects ---
    path('projects/', views.project_list, name='project_list'),
    path('projects/add/', views.project_add, name='project_add'),
    path('projects/<int:project_id>/edit/', views.project_edit, name='project_edit'),
    path('projects/<int:project_id>/delete/', views.project_delete, name='project_delete'),
    path('projects/<int:project_id>/', views.project_detail, name='project_detail'),

    # --- Tasks ---
    path('projects/<int:project_id>/tasks/add/', views.task_add, name='task_add'),
    path('tasks/<int:task_id>/edit/', views.task_edit, name='task_edit'),
    path('tasks/<int:task_id>/delete/', views.task_delete, name='task_delete'),
    path('tasks/<int:task_id>/status/', views.task_update_status, name='task_update_status'),
    path('tasks/<int:task_id>/status/ajax/', views.task_update_status_ajax, name='task_update_status_ajax'),
    path('tasks/<int:task_id>/', views.task_detail, name='task_detail'),
    path('tasks/<int:task_id>/claim/', views.claim_task, name='claim_task'),
    path('tasks/<int:task_id>/complete/', views.task_complete, name='task_complete'),

    # --- Task board / My tasks / Open tasks ---
    path('board/', views.task_board, name='task_board'),
    path('my-tasks/', views.my_tasks, name='my_tasks'),
    path('open-tasks/', views.open_tasks, name='open_tasks'),

    # --- Timesheet & Calendar ---
    path('timesheet/', views.timesheet, name='timesheet'),
    path('calendar/', views.calendar_view, name='calendar_view'),

    # --- Meetings ---
    path('meetings/', views.meeting_list, name='meeting_list'),
    path('meetings/archive/', views.meeting_archive, name='meeting_archive'),
    path('meetings/create/', views.meeting_create, name='meeting_create'),
    path('meetings/<int:meeting_id>/', views.meeting_detail, name='meeting_detail'),
    path('meetings/<int:meeting_id>/edit/', views.meeting_edit, name='meeting_edit'),
    path('meetings/<int:meeting_id>/delete/', views.meeting_delete, name='meeting_delete'),
    path('meetings/<int:meeting_id>/join/', views.meeting_join, name='meeting_join'),
    path('meetings/<int:meeting_id>/cancel/', views.meeting_cancel, name='meeting_cancel'),
    path('meetings/<int:meeting_id>/notes/', views.meeting_add_notes, name='meeting_add_notes'),
    path('meetings/<int:meeting_id>/important/', views.meeting_toggle_important, name='meeting_toggle_important'),

    # --- Analytics ---
    path('analytics/productivity/', views.analytics_productivity, name='analytics_productivity'),
    path('analytics/idle-time/', views.analytics_idle_time, name='analytics_idle_time'),
    path('analytics/focus-break/', views.analytics_focus_break, name='analytics_focus_break'),
    path('analytics/team-performance/', views.analytics_team_performance, name='analytics_team_performance'),

    # --- Trash / Soft-delete ---
    path('trash/', views.trash_list, name='trash_list'),
    path('projects/<int:project_id>/restore/', views.project_restore, name='project_restore'),
    path('projects/<int:project_id>/delete/permanent/', views.project_permanent_delete, name='project_permanent_delete'),
    path('projects/<int:project_id>/archive/', views.project_archive, name='project_archive'),
    path('projects/<int:project_id>/unarchive/', views.project_unarchive, name='project_unarchive'),
    path('tasks/<int:task_id>/restore/', views.task_restore, name='task_restore'),
    path('tasks/<int:task_id>/delete/permanent/', views.task_permanent_delete, name='task_permanent_delete'),
    path('meetings/<int:meeting_id>/restore/', views.meeting_restore, name='meeting_restore'),
    path('meetings/<int:meeting_id>/delete/permanent/', views.meeting_permanent_delete, name='meeting_permanent_delete'),
    path('meetings/<int:meeting_id>/archive-toggle/', views.meeting_archive_toggle, name='meeting_archive_toggle'),
    path('trash/empty/', views.empty_trash, name='empty_trash'),

    # --- Leaves ---
    path('leaves/', views.leave_list, name='leave_list'),
    path('leaves/create/', views.leave_create, name='leave_create'),
    path('leaves/<int:leave_id>/cancel/', views.leave_cancel, name='leave_cancel'),
    path('leaves/manage/', views.leave_manage, name='leave_manage'),
    path('leaves/<int:leave_id>/', views.leave_detail, name='leave_detail'),
    path('leaves/<int:leave_id>/approve/', views.leave_approve, name='leave_approve'),
    path('leaves/<int:leave_id>/reject/', views.leave_reject, name='leave_reject'),

    # --- Audit & Notifications ---
    path('audit/', views.audit_history, name='audit_history'),
    path('notifications/poll/', views.notifications_poll, name='notifications_poll'),
    path('notifications/mark-read/', views.notifications_mark_read, name='notifications_mark_read'),
    path('notifications/mark-read/<int:notification_id>/', views.notifications_mark_read, name='notifications_mark_read_one'),
    path('notifications/dismiss/<int:notification_id>/', views.notifications_dismiss, name='notifications_dismiss'),
]

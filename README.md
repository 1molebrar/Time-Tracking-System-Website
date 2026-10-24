# WorkPulse — Employee Time Tracking & Productivity Platform

WorkPulse is a role-based employee time tracking and productivity platform built for small to medium-sized businesses. It provides attendance tracking, time logging, task management, leave management, meeting scheduling, real-time dashboards, and reporting under a single system with three roles: Admin (full access), Manager (team scope), and Employee (self-service).

---

## Tech Stack

| Component | Technology |
|---|---|
| Backend | Django 6.0 (Python 3.13) |
| Database | SQLite (dev), PostgreSQL-ready |
| Real-Time | Django Channels 4 + Daphne 4 (WebSocket) |
| Frontend | Bootstrap 5.3, Chart.js 4, Bootstrap Icons |
| Server | ASGI (Daphne via custom management command) |
| Timezone | Europe/Istanbul |

---

## Role System

| Role | Scope | Key Permissions |
|---|---|---|
| **Admin** | Full system | User management, role assignment, all CRUD, override, all reports |
| **Manager** | Own team + self | View team data, manage projects/tasks/clients/meetings, approve leaves, reports |
| **Employee** | Self only | Clock in/out, time logging, claim open tasks, request leave, personal dashboard |

Authorization is handled via `accounts/permissions.py` using `get_visible_*` / `get_editable_*` functions.

---

## Modules & Features

### Attendance
- Clock In / Out with late detection and overtime calculation
- Break start/stop with duration tracking
- Daily session finalization (`is_completed`)
- Automatic clock-in block for users on approved leave (`is_active=False`)
- Weekly hours bar chart on dashboard

### Time Tracking
- Per-task start/stop timer with running indicator
- Billable time marking (`is_billable`)
- Daily/weekly/monthly timesheet view

### Project & Task Management
- Client-based projects with status tracking (active/completed/archived)
- 5 task statuses (todo/in_progress/in_review/done/blocked), priority levels, estimated hours
- Kanban board with drag-and-drop and real-time WebSocket updates
- Open task browsing, claiming, and completion notes

### Leave Management
- 6 leave types (annual, sick, maternity, paternity, marriage, other) — gender-filtered
- Request → Manager approve/reject workflow
- Auto deactivation on approved leave (`is_active=False`), auto reactivation on expiry
- File attachment support per request
- `reactivate_expired_leaves` management command for cron

### Dashboard (Admin/Manager)
- Stat cards: total employees, clocked in, late, absent
- Daily attendance doughnut chart (Active / Late / Absent)
- Weekly hours bar chart (per-day breakdown)
- 7-day late arrivals trend bar chart
- Today's attendance table with status badges
- Shift progress ring chart
- Upcoming meetings list
- Quick actions: clock in/out, add project, create meeting, leave requests
- Real-time WebSocket dashboard updates

### Meeting Management
- 8 meeting types: daily, weekly, sprint, planning, review, retrospective, one-on-one, other
- Status lifecycle: scheduled → ongoing → completed / cancelled
- Participants (active) and attendees (passive) M2M relationships
- Meeting notes with edit support
- Archive completed meetings

### Notifications & Real-Time
- 15 notification types (clock_in, clock_out, task_assigned, task_completed, leave_requested, etc.)
- Priority system: low / medium / high / urgent
- Real-time WebSocket push via UserNotificationConsumer
- Read/unread tracking, mark-all-as-read

### Reports & Analytics
- Attendance reports: Daily / Weekly / Monthly
- Project reports: time distribution by project
- User reports: productivity by user
- CSV and PDF export
- Analytics: productivity score, idle time, focus/break ratio, team performance

### Audit Trail
- Immutable logs for all create/update/delete operations
- 20+ action types (created, updated, deleted, clock_in, status_changed, override, etc.)
- Generic foreign key for any model
- IP address and JSON metadata support

### Additional Modules
- **Holiday Calendar**: static + religious holiday tracking, active/passive management
- **Global Search**: cross-entity search across projects, tasks, clients, users
- **Soft Delete & Archive**: trash with restore and permanent delete; archive for projects, tasks, meetings

---

## User Interface

### Sidebar (Admin/Manager)
- Brand logo (red gradient icon) + WorkPulse
- Menu: Dashboard, Projects, Task Board, Calendar, Timesheet, Meetings
- Management: Employees, Clients
- Attendance Reports: Daily / Weekly / Monthly
- Other Reports: Projects, Users
- Maintenance: Trash, Admin Panel
- ChatGPT-style toggle: button collapses/expands sidebar fully with smooth animation
- Color-coded nav icons with distinct backgrounds per section

### Theme
- Dark mode with blue accent (`#2563EB`) and red logo (`#EF4444` gradient)
- Glassmorphism: translucent cards with backdrop blur
- Skeleton loading states

---

## WebSocket Channels

| Channel | Consumer | Description |
|---|---|---|
| `ws/notifications/` | UserNotificationConsumer | Personal notification stream |
| `ws/task-board/<id>/` | TaskBoardConsumer | Real-time Kanban updates |
| `ws/dashboard/` | AttendanceDashboardConsumer | Live admin/manager dashboard |

---

## Security
- Session-based authentication
- Decorator-based authorization: `admin_required`, `manager_or_admin_required`, `employee_required`, `require_permission`
- Role-based data visibility scoping (employees see only their own data)
- Soft delete for data recovery

---

## Future Improvements
- Email notifications (SMTP integration)
- Password reset flow
- REST API (Django REST Framework)
- Docker containerization
- Test coverage improvement
- Leave balance tracking
- Shift scheduling management
- PWA support
- Mobile application

---

## Installation

```bash
python -m venv venv
venv\Scripts\activate
pip install django>=6.0 channels>=4.0 daphne>=4.0
python manage.py migrate
python manage.py collectstatic
python manage.py runserver_asgi
```

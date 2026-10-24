# WorkPulse — Project Report

## 1. Project Profile

| Field | Value |
|---|---|
| **Project Name** | WorkPulse — Employee Time Tracking & Productivity Platform |
| **Type** | Enterprise Time Tracking & Productivity Platform |
| **Architecture** | Monolithic Django (modular) |
| **Server** | ASGI (Daphne 4) — HTTP + WebSocket single process |
| **Language / Framework** | Python 3.13 / Django 6.0.5 |
| **Database** | SQLite (development), PostgreSQL-ready |
| **Real-Time** | Django Channels 4 (WebSocket — 3 channels) |
| **Frontend** | Bootstrap 5.3, Chart.js 4, Bootstrap Icons |
| **Timezone** | Europe/Istanbul |
| **Theme** | Dark mode, blue accent (#2563EB), red logo (#EF4444 gradient) |
| **Authentication** | Session-based, decorator-based authorization |
| **Git Status** | `git init` completed, no commits yet |
| **Environment** | Windows, venv, pip installation |

---

## 2. Project Structure

```
time_tracking/
├── accounts/                  # User management app
│   ├── decorators.py          # Authorization decorators
│   ├── middleware.py           # PermissionMiddleware
│   ├── models.py              # UserProfile (OneToOne User)
│   ├── permissions.py         # get_visible_* / get_editable_* functions
│   ├── urls.py                # 7 URLs (login, logout, employee CRUD)
│   └── views.py               # Login/logout, employee management
├── attendance/                # Main application
│   ├── audit.py               # Audit log helpers
│   ├── consumers.py           # 3 WebSocket consumers (233 lines)
│   ├── context_processors.py  # 5 context processors
│   ├── management/
│   │   └── commands/
│   │       ├── reactivate_expired_leaves.py  # Batch reactivate expired leaves
│   │       └── runserver_asgi.py             # Daphne launch command
│   ├── models.py              # 15 models (883 lines)
│   ├── notifications.py       # Notification helpers
│   ├── routing.py             # WebSocket URL routing
│   ├── urls.py                # 98 URL patterns
│   └── views.py               # 1821 lines — all CRUD views
├── templates/
│   ├── base.html              # Master template (1119 lines)
│   ├── admin/
│   │   └── dashboard.html     # Admin/manager dashboard
│   ├── employee/
│   │   └── dashboard.html     # Employee dashboard
│   └── attendance/
│       ├── *.html             # Leave, project, task, meeting, report templates
├── static/
│   ├── css/
│   └── js/
│       └── ws.js              # WebSocket client
├── timetracker/
│   ├── asgi.py                # ASGI configuration
│   ├── settings.py            # 143 lines — project settings
│   ├── urls.py                # Root URL configuration
│   └── wsgi.py                # WSGI (fallback)
├── manage.py
├── requirements.txt           # django, channels, daphne
├── README.md                  # English documentation
└── db.sqlite3                 # SQLite database
```

---

## 3. Technical Details

### 3.1. Models (16 total)

**accounts/models.py:**
- `UserProfile` — OneToOne to User; role (admin/manager/employee), gender, manager (self-ref FK), phone, department, deactivation_reason; auto-created via post_save signal

**attendance/models.py:**
- `SoftDeleteMixin` (abstract) — is_deleted, deleted_at, deleted_by, restored_at; soft_delete(), restore(), hard_delete()
- `ArchiveMixin` (abstract) — is_archived, archived_at; archive(), unarchive()
- `ProjectMembership` — User-Project junction, role (project_manager/member)
- `Client` — SoftDeleteMixin; name, email, company, phone, notes, created_by
- `Project` — SoftDeleteMixin + ArchiveMixin; name, client FK, status (active/completed/archived)
- `ProjectTask` — SoftDeleteMixin + ArchiveMixin; project FK, title, priority, status (5 states), assigned_to, estimated_hours, deadline, manager snapshot; VALID_TRANSITIONS, set_status()
- `TimeEntry` — SoftDeleteMixin; user, task FK, attendance FK (nullable), start/end_time, duration, is_running, is_billable, approved_by; stop(), approve()
- `Attendance` — user, date, check_in/out, total_hours, is_late, overtime_minutes, is_completed, manager; unique_together [user, date]; finalize()
- `Break` — attendance FK (CASCADE), break_start/end, duration_minutes, paused_entry FK (TimeEntry, nullable)
- `Task` — attendance FK (legacy), title, description, start/end_time
- `AuditLog` — actor FK (nullable), action (20+ choices), target GenericFK (ContentType + object_id), metadata JSON, ip_address, created_at
- `Notification` — user FK, message, type (15 choices), priority (4 levels), category, is_read, is_dismissed, expires_at, related_url
- `Holiday` — date, name, type (static/religious), year, is_active; unique_together [date, year]; is_holiday()
- `Meeting` — SoftDeleteMixin; title, meeting_type (8 types), date, start/end_time, status (5 states), created_by, participants/attendees M2M, is_important, notes; many properties
- `LeaveRequest` — employee FK, leave_type (6 types, gender-filtered), start/end_date, total_days, reason, attachment, status (pending/approved/rejected/cancelled), reviewed_by; save() override for auto deactivation

### 3.2. WebSocket Channels (3 total)

| Channel | Consumer | Usage |
|---|---|---|
| `ws/notifications/` | `UserNotificationConsumer` | Personal notification stream, timer/clock state |
| `ws/task-board/<id>/` | `TaskBoardConsumer` | Real-time Kanban board updates |
| `ws/dashboard/` | `AttendanceDashboardConsumer` | Admin/manager live dashboard |

Each consumer extends `BaseConsumer` with `send_json()` and overridden `receive()`. Uses `InMemoryChannelLayer`.

### 3.3. Authorization System

`accounts/permissions.py`:
- `get_visible_users()` — admin sees all, manager sees team, employee sees self
- `get_visible_projects()` — admin sees all, manager sees team projects, employee sees own
- `get_visible_tasks()` — same hierarchy
- `get_visible_attendances()` — admin sees all, manager sees team, employee sees self
- `get_editable_*()` — same hierarchy for edit permissions
- `can_override()` — admin only
- Decorators: `@admin_required`, `@manager_or_admin_required`, `@employee_required`, `@require_permission`

### 3.4. URL Structure (105+ patterns)

- `accounts/urls.py` (7): login, logout, employee CRUD
- `attendance/urls.py` (98): clock-in/out, break, dashboards (3 roles), history, reports, CSV/PDF export, timer CRUD, client/project/task CRUD, task board, timesheet, calendar, meeting CRUD, analytics (4 pages), trash/restore/archive, leave CRUD, audit log, notification polling
- `timetracker/urls.py` (3): include(accounts), include(attendance), admin

### 3.5. Dashboard

**Admin/Manager Dashboard:**
- Stat cards: total employees, clocked in, late, absent
- 3 charts: Daily Attendance (doughnut — Active/Late/Absent), Weekly Hours (bar), 7-Day Late Arrivals (bar)
- Today's Attendance table (with status badges)
- Shift progress ring chart
- Upcoming Meetings list
- Quick Actions (clock-in/out, add project, create meeting, leave requests)
- Real-time WebSocket updates

**Employee Dashboard:**
- Personal clock-in/out status
- Today's time entries
- Open tasks
- Personal statistics

### 3.6. Leave Management

- 6 leave types (annual, sick, maternity, paternity, marriage, other)
- Gender-based filtering (maternity for female only, paternity for male only)
- Workflow: Request → Manager approve/reject
- `save()` override: on approval sets `user.is_active=False` + deactivation_reason; on rejection or expiry auto-reactivates
- `reactivate_expired_leaves` management command (cron-ready)
- File attachment support
- Notification types: LEAVE_REQUESTED, LEAVE_APPROVED, LEAVE_REJECTED
- Audit log: leave requested, approved, rejected

### 3.7. Frontend Details

**Sidebar (base.html — 1119 lines):**
- ChatGPT-style toggle (`translateX(-100%)` animation)
- Mobile overlay, open by default on desktop
- Color-coded nav icon backgrounds per section
- Menu: Dashboard, Projects, Task Board, Calendar, Timesheet, Meetings, Employees, Clients, Attendance Reports (Daily/Weekly/Monthly split), Other Reports, Trash, Admin Panel
- Responsive breakpoint at 768px

**Theme:**
- CSS custom properties for dark theme (`--bg-primary: #0F172A`, `--accent: #2563EB`)
- Glassmorphism cards (`backdrop-filter: blur()`)
- Inter font family
- Skeleton loading states

**JavaScript:**
- Chart.js 4 with 3 charts (doughnut, bar x2)
- WebSocket client (`ws.js`) — notification polling + real-time events
- Sidebar toggle script
- Clock-in/out AJAX
- Task board drag-and-drop
- Timer start/stop
- Notification mark-read/dismiss

---

## 4. Feature Matrix

| Module | Status | Details |
|---|---|---|
| **Attendance** | Complete | Clock-in/out, late detection, overtime, break, finalization, leave block |
| **Time Tracking** | Complete | Per-task timer, billable marking, timesheet |
| **Project & Task Management** | Complete | Client-project CRUD, 5-status tasks, Kanban board, WS updates, claim/complete |
| **Leave Management** | Complete | 6 types, gender filter, approve/reject workflow, auto deactivation, file attach |
| **Dashboard (Admin/Manager)** | Complete | 3 charts, stat cards, today's attendance, shift ring, meetings, quick actions, WS live |
| **Dashboard (Employee)** | Complete | Personal clock status, time entries, open tasks |
| **Meeting Management** | Complete | 8 types, 5-status lifecycle, participants/attendees M2M, notes, archive |
| **Notifications** | Complete | 15 types, 4 priorities, WS push, read/unread, mark-all-read, dismiss |
| **Reports** | Complete | Daily/Weekly/Monthly attendance, project/user reports, CSV/PDF export |
| **Analytics** | Complete | Productivity, idle time, focus/break ratio, team performance |
| **Audit Trail** | Complete | GFK with 20+ actions, IP + JSON metadata, immutable logs |
| **Holiday Calendar** | Complete | Static/religious, active/passive, is_holiday() check |
| **Global Search** | Complete | Cross-entity search (projects, tasks, clients, users) |
| **Soft Delete & Archive** | Complete | Trash with restore/permanent delete, archive/unarchive |
| **Sidebar** | Complete | ChatGPT-style toggle, color-coded icons, responsive |
| **WebSocket Infrastructure** | Complete | 3 consumers, runserver_asgi command, Daphne 4 |
| **Authorization** | Complete | 3 roles, decorators, permission middleware, visible/editable scoping |
| **README** | Complete | English, all modules, installation, tech details |

---

## 5. Work Chronology

1. Project scaffold (Django 6.0 startproject + startapp accounts + attendance)
2. UserProfile model + permission middleware + decorators
3. Attendance model + clock-in/out views
4. Break management + TimeEntry model
5. Client/Project/Task CRUD + task board
6. Meeting management model + CRUD
7. Notification model + WebSocket consumer
8. AuditLog model + audit helpers
9. Holiday model + context processor
10. LeaveRequest model (gender filter, auto deactivation)
11. Dashboard cleanup (removed unused context)
12. Admin/manager dashboard rewrite (3 charts, stat cards, WS integration)
13. Chart stretching fix (maintainAspectRatio, container height)
14. Theme change (indigo → blue #2563EB, red logo #EF4444)
15. Sidebar ChatGPT-style toggle + color-coded icons + responsive
16. Sidebar task board active state bug fix
17. Attendance reports split (Daily/Weekly/Monthly links)
18. All code comments removed project-wide (18 files, tokenize-based)
19. WebSocket infrastructure (runserver_asgi command, routing fix)
20. Leave auto deactivation/reactivation + management command
21. Clock-in leave block + absent count fix
22. `.gitignore` and `README.md` created
23. All changes completed, awaiting git commit

---

## 6. Metrics

| Metric | Value |
|---|---|
| Python files (project) | ~25 |
| HTML templates | ~20 |
| URL patterns | 105+ |
| Models | 16 |
| WebSocket consumers | 3 |
| View lines (attendance) | 1821 |
| Template lines (base.html) | 1119 |
| requirements.txt dependencies | 3 (django, channels, daphne) |
| Dashboard charts | 3 (doughnut, bar, bar) |
| Roles | 3 (admin, manager, employee) |
| Permission types | 4 decorators + visible/editable functions |
| Notification types | 15 |
| Audit action types | 20+ |
| Leave types | 6 |
| Meeting types | 8 |
| Task statuses | 5 |
| Project statuses | 3 |
| Soft Delete | 3 models + Archive (2 models) |

---

## 7. Running the Project

```bash
# Activate virtual environment
venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Apply migrations
python manage.py migrate

# Collect static files
python manage.py collectstatic

# Start ASGI server (HTTP + WebSocket)
python manage.py runserver_asgi
```

Server runs at `http://localhost:8000`. WebSocket channels are served on the same port via Daphne 4.

---

## 8. Future Improvements

- Email notifications (SMTP integration)
- Password reset flow
- REST API (Django REST Framework)
- Docker containerization
- Test coverage improvement
- Leave balance tracking
- Shift scheduling management
- PWA support
- Mobile application
- PostgreSQL migration
- CI/CD pipeline

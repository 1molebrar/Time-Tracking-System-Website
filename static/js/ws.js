

/* WebSocket module - auto-executes */
;(function () {
  'use strict';

  /* Configuration */
  var WS_BASE = 'ws://' + window.location.host;
  var RECONNECT_DELAY = 3000;



  /* Opens notification WebSocket connection */
  function connectUserSocket() {
    var proto = window.location.protocol === 'https:' ? 'wss://' : 'ws://';
    var socket = new WebSocket(proto + window.location.host + '/ws/notifications/');

    // Handles socket open event
    socket.onopen = function () {
      console.debug('[WS] Notifications stream connected');
    };

    // Handles socket message event
    socket.onmessage = function (e) {
      try {
        // Step 1: parse JSON payload
        var data = JSON.parse(e.data);
        // Step 2: route to handler
        handleEvent(data);
      } catch (err) {
        console.warn('[WS] Parse error', err);
      }
    };

    // Handles socket close event
    socket.onclose = function () {
      console.debug('[WS] Disconnected, reconnecting in ' + RECONNECT_DELAY + 'ms');
      // Step 1: reconnect after delay
      setTimeout(connectUserSocket, RECONNECT_DELAY);
    };

    window.__ws_notification = socket;
  }



  /* Routes incoming events by type */
  function handleEvent(data) {
    switch (data.type) {
      case 'init':
        onInit(data);
        break;
      case 'notification_new':
        onNotificationNew(data);
        break;
      case 'notification_read':
        onNotificationRead(data);
        break;
      case 'clock_event':
        onClockEvent(data);
        break;
      case 'timer_event':
        onTimerEvent(data);
        break;
      case 'task_status_change':
        onTaskStatusChange(data);
        break;
      case 'meeting_event':
        onMeetingEvent(data);
        break;
      case 'dashboard_refresh':
        onDashboardRefresh(data);
        break;
    }
  }



  /* Handles initial state load */
  function onInit(data) {
    if (typeof renderNotifications === 'function') {
      renderNotifications(data, false);
      renderNotifications(data, true);
    }
    updateClockUI(data.clocked_in);
    updateTimerUI(data.active_timer);
  }



  /* Handles new notification event */
  function onNotificationNew(n) {
    if (typeof renderNotifications === 'function') {
      renderNotifications({ type: 'notification_new', notifications: [n] }, false);
      renderNotifications({ type: 'notification_new', notifications: [n] }, true);
    }
  }

  /* Handles notification read event */
  function onNotificationRead(data) {

    // Step 1: remove notification from lists
    [document.getElementById('notifList'), document.getElementById('notifList2')].forEach(function (list) {
      if (!list) return;
      var item = list.querySelector('[data-notif-id="' + data.notification_id + '"]');
      if (item) item.remove();
    });

    // Step 2: decrement badge counters
    [document.getElementById('notifBadge'), document.getElementById('notifBadge2')].forEach(function (badge) {
      if (badge) {
        var count = parseInt(badge.textContent, 10) || 0;
        if (count > 0) badge.textContent = count - 1;
      }
    });
  }



  /* Handles clock in/out event */
  function onClockEvent(data) {

    updateClockUI(data.user_clocked_in);

    // Step 1: toggle clock button UI
    var btn = document.getElementById('clockBtn');
    if (btn) {
      if (data.action === 'clock_in') {
        btn.innerHTML = '<i class="bi bi-box-arrow-right me-1"></i>Clock Out';
        btn.classList.remove('btn-primary');
        btn.classList.add('btn-danger');
      } else {
        btn.innerHTML = '<i class="bi bi-box-arrow-in-right me-1"></i>Clock In';
        btn.classList.remove('btn-danger');
        btn.classList.add('btn-primary');
      }
    }

    // Step 2: refresh admin dashboard if on admin page
    if (window.location.pathname.indexOf('/admin/') !== -1 && typeof refreshDashboard === 'function') {
      refreshDashboard();
    }
  }

  /* Updates clock status indicator */
  function updateClockUI(clockedIn) {
    var indicator = document.getElementById('clockStatus');
    if (indicator) {
      indicator.innerHTML = clockedIn
        ? '<span class="badge" style="background:rgba(52,211,153,0.15);color:#86EFAC;"><i class="bi bi-check-circle-fill me-1" style="font-size:0.6rem;"></i>Clocked In</span>'
        : '<span class="badge" style="background:rgba(239,68,68,0.15);color:#FCA5A5;"><i class="bi bi-x-circle-fill me-1" style="font-size:0.6rem;"></i>Not Clocked In</span>';
    }
  }



  /* Handles timer start/stop event */
  function onTimerEvent(data) {
    updateTimerUI(data);

    // Step 1: update timer button to stop state
    var btn = document.getElementById('timerBtn');
    if (btn && data.action === 'timer_start') {
      btn.innerHTML = '<i class="bi bi-stop-circle me-1"></i>Stop Timer';
      btn.classList.remove('btn-success');
      btn.classList.add('btn-danger');
    }
  }

  /* Updates running timer display */
  function updateTimerUI(data) {
    var el = document.getElementById('runningTimer');
    if (!el) return;
    if (data && data.action === 'timer_start') {
      el.style.display = 'flex';
      el.querySelector('.timer-task').textContent = data.task_title || '';
      el.querySelector('.timer-duration').textContent = formatMinutes(data.duration_minutes || 0);
    } else {
      el.style.display = 'none';
    }
  }

  /* Converts minutes to human-readable format */
  function formatMinutes(m) {
    var h = Math.floor(m / 60);
    var min = m % 60;
    return (h > 0 ? h + 'h ' : '') + min + 'm';
  }



  /* Handles task status change event */
  function onTaskStatusChange(data) {

    // Step 1: move card to new column
    var card = document.querySelector('.task-card[data-task-id="' + data.task_id + '"]');
    if (card) {
      var col = document.querySelector('.task-column[data-status="' + data.new_status + '"] .task-list');
      if (col && col !== card.parentNode) {
        col.appendChild(card);
        card.querySelector('.task-status-badge').textContent = data.new_status.replace('_', ' ');
      }
    }

    // Step 2: update dropdown selector
    var sel = document.getElementById('taskStatus_' + data.task_id);
    if (sel) sel.value = data.new_status;
  }



  /* Handles meeting cancelled event */
  function onMeetingEvent(data) {
    var list = document.getElementById('meetingList');
    if (!list) return;
    if (data.action === 'cancelled') {
      // Step 1: mark meeting as cancelled in the UI
      var el = list.querySelector('[data-meeting-id="' + data.meeting_id + '"]');
      if (el) {
        el.querySelector('.meeting-status').textContent = 'Cancelled';
        el.style.opacity = '0.5';
      }
    }
  }



  /* Handles dashboard refresh event */
  function onDashboardRefresh(data) {
    if (typeof refreshDashboard === 'function') {
      refreshDashboard(data.section);
    }
  }





  /* Public WebSocket API */
  window.WS = {
    connectNotifications: connectUserSocket,

    // Connects to task board WebSocket
    connectTaskBoard: function (projectId) {
      var proto = window.location.protocol === 'https:' ? 'wss://' : 'ws://';
      var socket = new WebSocket(proto + window.location.host + '/ws/task-board/' + projectId + '/');
      socket.onmessage = function (e) {
        try {
          var data = JSON.parse(e.data);
          handleEvent(data);
        } catch (err) {}
      };
      socket.onclose = function () {
        setTimeout(function () {
          if (window.WS) window.WS.connectTaskBoard(projectId);
        }, RECONNECT_DELAY);
      };
      window.__ws_taskboard = socket;
    },

    // Connects to dashboard WebSocket
    connectDashboard: function () {
      if (window.__ws_dashboard) return;
      var proto = window.location.protocol === 'https:' ? 'wss://' : 'ws://';
      var socket = new WebSocket(proto + window.location.host + '/ws/dashboard/');
      socket.onmessage = function (e) {
        try {
          var data = JSON.parse(e.data);
          handleEvent(data);
        } catch (err) {}
      };
      socket.onclose = function () {
        window.__ws_dashboard = null;
        setTimeout(function () {
          if (window.WS) window.WS.connectDashboard();
        }, RECONNECT_DELAY);
      };
      window.__ws_dashboard = socket;
    },

    // Disconnects all active WebSocket connections
    disconnectAll: function () {
      if (window.__ws_notification) { window.__ws_notification.close(); window.__ws_notification = null; }
      if (window.__ws_taskboard) { window.__ws_taskboard.close(); window.__ws_taskboard = null; }
      if (window.__ws_dashboard) { window.__ws_dashboard.close(); window.__ws_dashboard = null; }
    },
  };

  /* Auto-connect if user is logged in */
  if (document.querySelector('body[data-user-id]')) {
    connectUserSocket();
  }

})();

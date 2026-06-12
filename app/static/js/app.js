// Configure Chart.js global defaults for light/dark theme on startup
if (window.Chart) {
  const isDark = document.documentElement.classList.contains('dark');
  Chart.defaults.color = isDark ? '#94a3b8' : '#64748b';
  if (Chart.defaults.scale && Chart.defaults.scale.grid) {
    Chart.defaults.scale.grid.color = isDark ? '#243049' : '#e2e8f0';
  }
}

// Tiny helpers
function $(s, root = document) { return root.querySelector(s); }
function $$(s, root = document) { return Array.from(root.querySelectorAll(s)); }
function formatCurrency(value) {
  if (!value) return '₹ 0.00';
  const n = parseFloat(value);
  return '₹ ' + n.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

document.addEventListener('DOMContentLoaded', () => {
  if (window.lucide) lucide.createIcons();

  // Profile dropdown
  const pb = $('.profile-btn');
  const dd = $('.dropdown');
  const notifDropdown = document.getElementById('notificationsDropdown');
  if (pb && dd) {
    pb.addEventListener('click', e => { 
      e.stopPropagation(); 
      dd.classList.toggle('open'); 
      if (notifDropdown) notifDropdown.classList.remove('open');
    });
    document.addEventListener('click', () => dd.classList.remove('open'));
  }

  // Mobile sidebar
  const mt = $('.menu-toggle');
  const sb = $('.sidebar');
  if (mt && sb) mt.addEventListener('click', () => sb.classList.toggle('open'));

  // Auto-dismiss flashes
  $$('.flash').forEach(f => setTimeout(() => { f.style.opacity = 0; setTimeout(() => f.remove(), 300); }, 4500));

  // Confirm modals
  $$('[data-confirm]').forEach(form => {
    form.addEventListener('submit', e => {
      if (form.dataset.confirmed === '1') return;
      e.preventDefault();
      const msg = form.dataset.confirm || 'Are you sure?';
      openConfirm(msg, () => { form.dataset.confirmed = '1'; form.submit(); });
    });
  });

  // AJAX mark paid / undo
  function attachPaymentHandlers() {
    $$('form[data-ajax="payment"]').forEach(form => {
      if (form.dataset.handlerAttached) return;
      form.dataset.handlerAttached = '1';
      const handler = async e => {
        e.preventDefault();
        const btn = form.querySelector('button');
        if (!btn || btn.disabled) return;
        
        // Read notes input value before form submission
        const notesInput = form.querySelector('[name="notes"]');
        const notesVal = notesInput ? notesInput.value.trim() : '';

        const row = form.closest('tr');
        const orig = btn.innerHTML;
        btn.innerHTML = '<span class="spinner"></span>';
        btn.disabled = true;
        try {
          const res = await fetch(form.action, {
            method: 'POST',
            headers: { 'X-Requested-With': 'XMLHttpRequest' },
            body: new FormData(form),
          });
          const data = await res.json();
          if (data.ok && row) {
            const statusCell = row.querySelector('[data-status]');
            const actionCell = row.querySelector('td:last-child');
            let paidDateCell = row.querySelector('.paid-date-text')?.closest('td');
            if (!paidDateCell) paidDateCell = row.querySelectorAll('td')[7];
            const selectCell = row.querySelector('td');
            const csrf = form.querySelector('[name="csrf_token"]').value;
            const dateStr = data.paid_date;

            if (form.dataset.kind === 'paid') {
              statusCell.innerHTML = '<span class="badge Paid">Paid</span>';
              if (selectCell && selectCell.querySelector('input[type="checkbox"]')) {
                selectCell.innerHTML = '<i data-lucide="check-circle" style="width: 14px; height: 14px; color: var(--success)"></i>';
              }
              if (paidDateCell) {
                const dateSpan = paidDateCell.querySelector('.paid-date-text');
                if (dateSpan) {
                  dateSpan.textContent = dateStr;
                } else {
                  paidDateCell.innerHTML = `<span class="paid-date-text">${dateStr}</span>`;
                }
                let noteDiv = paidDateCell.querySelector('.note-text');
                if (notesVal) {
                  if (noteDiv) {
                    noteDiv.textContent = notesVal;
                    noteDiv.style.display = 'block';
                  } else {
                    paidDateCell.innerHTML += `<div class="note-text" style="font-size:10px; color:var(--slate-500); margin-top:2px;">${notesVal}</div>`;
                  }
                } else {
                  if (noteDiv) {
                    noteDiv.textContent = '';
                    noteDiv.style.display = 'none';
                  }
                }
              }
              actionCell.innerHTML = `<form method="post" action="${form.action.replace('/mark-paid/', '/undo-paid/')}" data-ajax="payment" data-schedule-id="${form.dataset.scheduleId}" data-kind="undo" style="display:inline">
                <input type="hidden" name="csrf_token" value="${csrf}">
                <button class="btn ghost sm" title="Undo paid"><i data-lucide="rotate-ccw"></i></button>
              </form>`;
            } else {
              statusCell.innerHTML = '<span class="badge Pending">Pending</span>';
              if (selectCell && selectCell.querySelector('[data-lucide="check-circle"]')) {
                const sId = form.dataset.scheduleId || '';
                const emi = row.querySelectorAll('td')[3].textContent.replace(/[^\d.-]/g, '');
                const principal = row.querySelectorAll('td')[4].textContent.replace(/[^\d.-]/g, '');
                const interest = row.querySelectorAll('td')[5].textContent.replace(/[^\d.-]/g, '');
                const month = row.querySelector('td strong')?.textContent?.trim() || '';
                selectCell.innerHTML = `<input type="checkbox" class="schedule-checkbox" data-id="${sId}" data-emi="${emi}" data-principal="${principal}" data-interest="${interest}" data-month="${month}">`;
                // Hook change listener
                const cb = selectCell.querySelector('input');
                if (cb) {
                  cb.addEventListener('change', function() {
                    if (window.updateFloatBar) window.updateFloatBar();
                  });
                }
              }
              const noteDiv = paidDateCell ? paidDateCell.querySelector('.note-text') : null;
              const oldNoteVal = noteDiv ? noteDiv.textContent.trim() : '';
              if (paidDateCell) {
                const dateSpan = paidDateCell.querySelector('.paid-date-text');
                if (dateSpan) dateSpan.textContent = '—';
                if (noteDiv) {
                  noteDiv.textContent = '';
                  noteDiv.style.display = 'none';
                }
              }
              actionCell.innerHTML = `<form method="post" action="${form.action.replace('/undo-paid/', '/mark-paid/')}" data-ajax="payment" data-schedule-id="${form.dataset.scheduleId}" data-kind="paid" style="display:inline-flex; gap:6px; align-items:center;">
                <input type="hidden" name="csrf_token" value="${csrf}">
                <div style="position: relative; display: inline-flex; align-items: center;">
                  <input type="text" name="notes" placeholder="Ref ID / Notes" class="ref-id-input" value="${oldNoteVal}" style="font-size:11px; padding:3px 24px 3px 6px; border:1px solid var(--slate-200); border-radius:6px; width:115px;">
                  <button type="button" class="gen-ref-btn" title="Generate Ref ID" style="position: absolute; right: 4px; background: transparent; border: none; cursor: pointer; color: var(--slate-400); padding: 2px; display: flex; align-items: center; justify-content: center;">
                    <i data-lucide="sparkles" style="width: 11px; height: 11px;"></i>
                  </button>
                </div>
                <button class="btn success sm"><i data-lucide="check"></i> Mark paid</button>
              </form>`;
            }
            if (window.lucide) lucide.createIcons();
            attachPaymentHandlers();
            if (window.updateFloatBar) window.updateFloatBar();

            const progressBar = document.querySelector('.progress-bar');
            const progressText = progressBar?.closest('.card')?.querySelector('[style*="justify-content:space-between"]');

            if (progressBar && data.completion_percentage !== undefined) {
              progressBar.style.width = data.completion_percentage + '%';
            }
            if (progressText && data.completion_percentage !== undefined) {
              const spans = progressText.querySelectorAll('span');
              if (spans[0]) spans[0].textContent = Math.round(data.completion_percentage) + '% complete';
              if (spans[1]) spans[1].textContent = 'Remaining ' + formatCurrency(data.remaining_balance);
            }
            refreshDashboard();
          }
        } finally {
          if (document.body.contains(btn)) { btn.innerHTML = orig; btn.disabled = false; }
        }
      };
      form.addEventListener('submit', handler);
    });
  }
  attachPaymentHandlers();

  // Password visibility toggle helper
  document.addEventListener('click', e => {
    const toggle = e.target.closest('.password-toggle');
    if (!toggle) return;
    
    e.preventDefault();
    const wrapper = toggle.closest('.password-input-wrapper');
    if (!wrapper) return;
    
    const input = wrapper.querySelector('input');
    if (!input) return;
    
    if (input.type === 'password') {
      input.type = 'text';
      wrapper.classList.add('show-password');
    } else {
      input.type = 'password';
      wrapper.classList.remove('show-password');
    }
  });

  // --- Dark Mode Theme Toggle ---
  const themeToggle = document.getElementById('themeToggle');
  if (themeToggle) {
    themeToggle.addEventListener('click', () => {
      const isDark = document.documentElement.classList.toggle('dark');
      localStorage.setItem('theme', isDark ? 'dark' : 'light');
      
      // Dynamically update all active chart colors
      if (window.Chart) {
        const textColor = isDark ? '#94a3b8' : '#64748b';
        const gridColor = isDark ? '#243049' : '#e2e8f0';
        
        Chart.defaults.color = textColor;
        if (Chart.defaults.scale && Chart.defaults.scale.grid) {
          Chart.defaults.scale.grid.color = gridColor;
        }
        
        if (Chart.instances) {
          Object.values(Chart.instances).forEach(chart => {
            if (chart.options.plugins && chart.options.plugins.legend && chart.options.plugins.legend.labels) {
              chart.options.plugins.legend.labels.color = textColor;
            }
            if (chart.options.scales) {
              Object.values(chart.options.scales).forEach(scale => {
                if (scale.grid) {
                  scale.grid.color = gridColor;
                }
                if (scale.ticks) {
                  scale.ticks.color = textColor;
                }
              });
            }
            chart.update();
          });
        }
      }
    });
  }

  // --- Notifications Hub ---
  const notifBtn = document.getElementById('notificationsBtn');
  const notifList = document.getElementById('notificationsList');
  const notifBadge = document.getElementById('notificationsBadge');
  const clearAllBtn = document.getElementById('clearAllNotifications');

  // Load seen/dismissed ids from localStorage
  let readIds = JSON.parse(localStorage.getItem('read_notifications') || '[]');
  let dismissedIds = JSON.parse(localStorage.getItem('dismissed_notifications') || '[]');

  async function fetchNotifications() {
    try {
      const res = await fetch('/api/notifications');
      const data = await res.json();
      const allNotifications = data.notifications || [];
      
      // Filter out dismissed ones
      const activeNotifications = allNotifications.filter(n => !dismissedIds.includes(n.id));
      
      // Calculate unread count
      const unreadCount = activeNotifications.filter(n => !readIds.includes(n.id)).length;
      
      // Update badge
      if (unreadCount > 0) {
        notifBadge.textContent = unreadCount;
        notifBadge.style.display = 'flex';
      } else {
        notifBadge.style.display = 'none';
      }
      
      // Render list
      renderNotificationsList(activeNotifications);
    } catch (err) {
      console.error('Failed to fetch notifications:', err);
    }
  }

  function renderNotificationsList(notifications) {
    if (!notifList) return;
    notifList.innerHTML = '';
    
    if (notifications.length === 0) {
      notifList.innerHTML = `
        <div class="notification-empty">
          <i data-lucide="bell-off"></i>
          <p>No notifications yet</p>
        </div>`;
      if (window.lucide) lucide.createIcons();
      return;
    }
    
    notifications.forEach(n => {
      const isRead = readIds.includes(n.id);
      const item = document.createElement('div');
      item.className = `notification-item ${isRead ? 'read' : ''}`;
      item.dataset.id = n.id;
      
      let iconName = 'bell';
      if (n.type === 'overdue') iconName = 'alert-triangle';
      else if (n.type === 'balloon') iconName = 'calendar';
      else if (n.type === 'import') iconName = 'file-text';
      
      item.innerHTML = `
        <div class="notification-icon ${n.type}">
          <i data-lucide="${iconName}"></i>
        </div>
        <div class="notification-content">
          <div class="notification-title">${n.title}</div>
          <div class="notification-message">${n.message}</div>
          <div class="notification-time">${formatTime(n.date)}</div>
        </div>
        <button class="notification-dismiss-btn" title="Dismiss">
          <i data-lucide="x"></i>
        </button>
      `;
      
      // Navigate to link on item click (except if dismiss btn clicked)
      item.addEventListener('click', (e) => {
        if (e.target.closest('.notification-dismiss-btn')) return;
        if (n.link) window.location.href = n.link;
      });
      
      // Dismiss button handler
      item.querySelector('.notification-dismiss-btn').addEventListener('click', (e) => {
        e.stopPropagation();
        dismissNotification(n.id, item);
      });
      
      notifList.appendChild(item);
    });
    
    if (window.lucide) lucide.createIcons();
  }

  function dismissNotification(id, element) {
    if (!dismissedIds.includes(id)) {
      dismissedIds.push(id);
      localStorage.setItem('dismissed_notifications', JSON.stringify(dismissedIds));
    }
    
    // Animate removal
    element.style.transition = 'all 0.25s ease';
    element.style.opacity = '0';
    element.style.transform = 'translateX(20px)';
    
    setTimeout(() => {
      element.remove();
      // Recalculate badge / empty state after animation
      fetchNotifications();
    }, 250);
  }

  function formatTime(dateStr) {
    if (!dateStr) return '';
    const d = new Date(dateStr);
    if (isNaN(d.getTime())) return dateStr;
    
    const now = new Date();
    const diffMs = now - d;
    const diffMins = Math.floor(diffMs / 60000);
    const diffHrs = Math.floor(diffMins / 60);
    const diffDays = Math.floor(diffHrs / 24);
    
    if (diffMins < 1) return 'Just now';
    if (diffMins < 60) return `${diffMins}m ago`;
    if (diffHrs < 24) return `${diffHrs}h ago`;
    if (diffDays === 1) return 'Yesterday';
    if (diffDays < 7) return `${diffDays}d ago`;
    
    return d.toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' });
  }

  // Handle Bell Click
  if (notifBtn && notifDropdown) {
    notifBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      notifDropdown.classList.toggle('open');
      
      // Close profile dropdown if open
      if (dd) dd.classList.remove('open');
      
      // Mark all current notifications as read when opening
      if (notifDropdown.classList.contains('open')) {
        const items = Array.from(notifList.querySelectorAll('.notification-item'));
        items.forEach(item => {
          const id = item.dataset.id;
          if (id && !readIds.includes(id)) {
            readIds.push(id);
            item.classList.add('read');
          }
        });
        localStorage.setItem('read_notifications', JSON.stringify(readIds));
        notifBadge.style.display = 'none';
      }
    });
  }

  // Clear All / Mark all read button handler
  if (clearAllBtn) {
    clearAllBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      const items = Array.from(notifList.querySelectorAll('.notification-item'));
      items.forEach(item => {
        const id = item.dataset.id;
        if (id && !readIds.includes(id)) {
          readIds.push(id);
          item.classList.add('read');
        }
      });
      localStorage.setItem('read_notifications', JSON.stringify(readIds));
      notifBadge.style.display = 'none';
    });
  }

  // Global document click listener for closing dropdowns
  document.addEventListener('click', (e) => {
    if (notifDropdown && !notifDropdown.contains(e.target) && e.target !== notifBtn) {
      notifDropdown.classList.remove('open');
    }
  });

  // Initial load
  fetchNotifications();
});

function openConfirm(msg, onYes) {
  let m = $('#confirmModal');
  if (!m) {
    m = document.createElement('div');
    m.id = 'confirmModal';
    m.className = 'modal-backdrop';
    m.innerHTML = `<div class="modal"><h3>Please confirm</h3><p id="cm-msg"></p>
      <div class="modal-actions"><button class="btn secondary" id="cm-no">Cancel</button>
      <button class="btn danger" id="cm-yes">Confirm</button></div></div>`;
    document.body.appendChild(m);
  }
  $('#cm-msg', m).textContent = msg;
  m.classList.add('open');
  $('#cm-no', m).onclick = () => m.classList.remove('open');
  $('#cm-yes', m).onclick = () => { m.classList.remove('open'); onYes(); };
}

async function refreshDashboard() {
  // No-op unless on dashboard
  if (!window.__dashboard) return;
  try {
    const res = await fetch('/api/dashboard');
    const d = await res.json();
    window.__dashboard.update(d);
  } catch (e) {}
}


// document.addEventListener("submit", async (e) => {
//   const form = e.target;

//   if (!(form instanceof HTMLFormElement)) return;
//   if (!form.matches('form[data-ajax="payment"]')) return;

//   e.preventDefault();

//   const row = form.closest("tr");
//   const btn = form.querySelector("button");
//   if (!btn) return;

//   const original = btn.innerHTML;

//   btn.innerHTML = "⏳";
//   btn.disabled = true;

//   try {
//     const res = await fetch(form.action, {
//       method: "POST",
//       headers: {
//         "X-Requested-With": "XMLHttpRequest"
//       },
//       body: new FormData(form)
//     });

//     const data = await res.json();
//     if (!data.ok) return;

//     const card = row.closest(".card");
//     const statusCell = row.querySelector("[data-status]");
//     const badge = statusCell?.querySelector(".badge");
//     const actionCell = row.querySelector("td:last-child");

//     // 🔥 IMPORTANT: decide from SERVER, not dataset
//     const nowPaid = badge.textContent.trim() !== "Paid";

//     // update badge
//     if (nowPaid) {
//       badge.textContent = "Paid";
//       badge.className = "badge Paid";
//     } else {
//       badge.textContent = "Pending";
//       badge.className = "badge Pending";
//     }

//     const csrf = form.querySelector('[name="csrf_token"]')?.value || "";

//     // 🔁 toggle correctly
//     if (nowPaid) {
//       actionCell.innerHTML = `
//         <form method="post"
//               action="${form.action.replace("mark-paid", "undo-paid")}"
//               data-ajax="payment"
//               data-kind="undo"
//               style="display:inline">
//           <input type="hidden" name="csrf_token" value="${csrf}">
//           <button class="btn ghost sm">Undo</button>
//         </form>
//       `;
//     } else {
//       actionCell.innerHTML = `
//         <form method="post"
//               action="${form.action.replace("undo-paid", "mark-paid")}"
//               data-ajax="payment"
//               data-kind="paid"
//               style="display:inline">
//           <input type="hidden" name="csrf_token" value="${csrf}">
//           <button class="btn success sm">Mark paid</button>
//         </form>
//       `;
//     }

//     // update progress
//     const bar = card?.querySelector(".progress-bar");
//     if (bar && data.completion_percentage !== undefined) {
//       bar.style.width = data.completion_percentage + "%";
//     }

//   } finally {
//     btn.innerHTML = original;
//     btn.disabled = false;
//   }
// });
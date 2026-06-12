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
  if (pb && dd) {
    pb.addEventListener('click', e => { e.stopPropagation(); dd.classList.toggle('open'); });
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
            const paidDateCell = row.querySelectorAll('td')[7];
            const csrf = form.querySelector('[name="csrf_token"]').value;
            const dateStr = data.paid_date;

            if (form.dataset.kind === 'paid') {
              statusCell.innerHTML = '<span class="badge Paid">Paid</span>';
              if (paidDateCell) {
                paidDateCell.innerHTML = dateStr;
                if (notesVal) {
                  paidDateCell.innerHTML += `<div style="font-size:10px; color:var(--slate-500); margin-top:2px;">${notesVal}</div>`;
                }
              }
              actionCell.innerHTML = `<form method="post" action="${form.action.replace('/mark-paid/', '/undo-paid/')}" data-ajax="payment" data-kind="undo" style="display:inline">
                <input type="hidden" name="csrf_token" value="${csrf}">
                <button class="btn ghost sm" title="Undo paid"><i data-lucide="rotate-ccw"></i></button>
              </form>`;
            } else {
              statusCell.innerHTML = '<span class="badge Pending">Pending</span>';
              const noteDiv = paidDateCell ? paidDateCell.querySelector('div') : null;
              const oldNoteVal = noteDiv ? noteDiv.textContent.trim() : '';
              if (paidDateCell) paidDateCell.textContent = '—';
              actionCell.innerHTML = `<form method="post" action="${form.action.replace('/undo-paid/', '/mark-paid/')}" data-ajax="payment" data-kind="paid" style="display:inline-flex; gap:6px; align-items:center;">
                <input type="hidden" name="csrf_token" value="${csrf}">
                <input type="text" name="notes" placeholder="Ref ID / Notes" value="${oldNoteVal}" style="font-size:11px; padding:3px 6px; border:1px solid var(--slate-200); border-radius:6px; width:110px;">
                <button class="btn success sm"><i data-lucide="check"></i> Mark paid</button>
              </form>`;
            }
            if (window.lucide) lucide.createIcons();
            attachPaymentHandlers();

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
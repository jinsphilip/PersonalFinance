// ── Formatting helpers ───────────────────────────────────────────────────────

function fmt(n) {
  if (n === null || n === undefined || n === '') return '—';
  return '₹' + Number(n).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function fmtNum(n, dp = 2) {
  return Number(n).toLocaleString('en-IN', { minimumFractionDigits: dp, maximumFractionDigits: dp });
}

function fmtDate(s) {
  if (!s) return '—';
  const d = new Date(s);
  if (isNaN(d)) return s;
  return d.toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' });
}

// Renders a +x.xx% / -x.xx% coloured span from a numeric percentage.
function gainPctBadge(pct) {
  const p = Number(pct);
  const cls = p >= 0 ? 'gain' : 'loss';
  const sign = p >= 0 ? '+' : '';
  return `<span class="${cls}">${sign}${fmtNum(p)}%</span>`;
}

// Renders a coloured absolute gain/loss amount.
function gainAmt(n) {
  const v = Number(n);
  const cls = v >= 0 ? 'gain' : 'loss';
  const sign = v >= 0 ? '+' : '';
  return `<span class="${cls}">${sign}${fmt(v).replace('₹', '₹')}</span>`;
}

function esc(s) {
  if (s === null || s === undefined) return '';
  return String(s).replace(/[&<>"']/g, c => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]
  ));
}

// ── Toast ────────────────────────────────────────────────────────────────────

function showToast(msg, type = 'success') {
  const t = document.getElementById('toast');
  if (!t) return;
  t.textContent = msg;
  t.className = `toast ${type} show`;
  setTimeout(() => { t.className = 'toast'; }, 3000);
}

// ── Delete confirmation (wired to the shared modal in base.html) ──────────────

let _deleteCallback = null;
function confirmDelete(callback) {
  _deleteCallback = callback;
  const m = document.getElementById('deleteModal');
  if (m) m.style.display = 'flex';
}
function closeDeleteModal() {
  const m = document.getElementById('deleteModal');
  if (m) m.style.display = 'none';
  _deleteCallback = null;
}
document.addEventListener('DOMContentLoaded', () => {
  const btn = document.getElementById('confirmDeleteBtn');
  if (btn) btn.onclick = () => {
    const cb = _deleteCallback;
    closeDeleteModal();
    if (cb) cb();
  };
});

// ── Generic modal helpers ────────────────────────────────────────────────────

function openModal(id) {
  const m = document.getElementById(id);
  if (m) m.style.display = 'flex';
}
function closeModal(id) {
  const m = document.getElementById(id);
  if (m) m.style.display = 'none';
}

// ── REST helpers ─────────────────────────────────────────────────────────────

async function apiGet(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

async function apiSend(url, method, body) {
  const res = await fetch(url, {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

// Multipart upload (e.g. PDF statement). `fields` adds extra form fields.
async function apiUpload(url, file, fields = {}) {
  const fd = new FormData();
  fd.append('file', file);
  Object.entries(fields).forEach(([k, v]) => { if (v != null) fd.append(k, v); });
  const res = await fetch(url, { method: 'POST', body: fd });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

// Collects a form's named fields into a plain object.
// Checkboxes are reported as booleans by their checked state (FormData would
// otherwise omit unchecked ones and emit the raw value attribute for checked).
function formToObject(formId) {
  const form = document.getElementById(formId);
  const data = {};
  new FormData(form).forEach((v, k) => { data[k] = v; });
  Array.from(form.elements).forEach(el => {
    if (el.name && el.type === 'checkbox') data[el.name] = el.checked;
  });
  return data;
}

// Fills a form's inputs/selects from an object (used when editing).
function fillForm(formId, obj) {
  const form = document.getElementById(formId);
  if (!form) return;
  Array.from(form.elements).forEach(el => {
    if (!el.name) return;
    if (el.type === 'checkbox') {            // set checked state, never .value
      el.checked = !!obj[el.name];
      return;
    }
    if (obj[el.name] !== undefined && obj[el.name] !== null) {
      el.value = obj[el.name];
    }
  });
}

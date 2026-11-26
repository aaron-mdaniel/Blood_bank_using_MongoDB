/**
 * Shared UI Utilities: XSS-safe escaping, status badges, toasts, and loading states.
 */
export function escapeHtml(value) {
  if (value === null || value === undefined) return "";
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

export function showToast(message, type = "info") {
  let container = document.getElementById("toast-container");
  if (!container) {
    container = document.createElement("div");
    container.id = "toast-container";
    container.className = "toast-container";
    document.body.appendChild(container);
  }
  const toast = document.createElement("div");
  toast.className = `toast ${type}`;
  toast.textContent = message;
  container.appendChild(toast);
  setTimeout(() => toast.remove(), 4200);
}

export function badgeForStatus(status) {
  const val = String(status || "").toUpperCase();
  const map = {
    AVAILABLE: "badge-success",
    PASSED: "badge-success",
    ELIGIBLE: "badge-success",
    VERIFIED: "badge-success",
    APPROVED: "badge-success",
    ALLOCATED: "badge-info",
    SUCCESS: "badge-success",
    ACTIVE: "badge-success",
    UPCOMING: "badge-info",
    PENDING: "badge-warning",
    PARTIALLY_ALLOCATED: "badge-warning",
    URGENT: "badge-warning",
    TEMPORARY_DEFERRED: "badge-warning",
    CRITICAL: "badge-danger",
    REJECTED: "badge-danger",
    EXPIRED: "badge-danger",
    DISCARDED: "badge-danger",
    DENIED: "badge-danger",
    FAILURE: "badge-danger",
    PERMANENT_DEFERRED: "badge-danger",
  };
  const cls = map[val] || "badge-neutral";
  return `<span class="badge ${cls}">${escapeHtml(val)}</span>`;
}

export function formatDate(value) {
  if (!value) return "—";
  const dt = new Date(value);
  if (Number.isNaN(dt.getTime())) return escapeHtml(value);
  return dt.toLocaleString();
}

export function setLoading(element, isLoading, text = "Loading...") {
  if (!element) return;
  if (isLoading) {
    element.innerHTML = `<div class="flex-row text-muted"><span class="spinner"></span><span>${escapeHtml(text)}</span></div>`;
  }
}

export function renderBarChart(container, rows, labelFn, valueFn) {
  if (!rows || rows.length === 0) {
    container.innerHTML = `<p class="text-muted">No aggregation records available yet.</p>`;
    return;
  }
  const maxVal = Math.max(...rows.map(valueFn), 1);
  container.innerHTML = `<div class="bar-list">${rows
    .map((row) => {
      const val = valueFn(row);
      const pct = Math.max(4, Math.round((val / maxVal) * 100));
      return `
        <div class="bar-row">
          <strong>${escapeHtml(labelFn(row))}</strong>
          <div class="bar-track"><div class="bar-fill" style="width:${pct}%"></div></div>
          <span>${escapeHtml(val)}</span>
        </div>
      `;
    })
    .join("")}</div>`;
}

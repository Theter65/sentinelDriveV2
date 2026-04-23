/* Global UI behavior: layout readiness, nav highlighting and event toasts. */

function $(id) {
  return document.getElementById(id);
}

function clampInt(value, fallback) {
  const parsed = Number.parseInt(value, 10);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function fmtLocalDate(isoString) {
  try {
    return new Date(isoString).toLocaleString("es-EC");
  } catch {
    return isoString;
  }
}

function escapeHtml(value) {
  const str = value === null || value === undefined ? "" : String(value);
  return str
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function initLayout() {
  setTimeout(() => document.body.classList.remove("no-transition"), 100);
}

function initActiveNav() {
  const currentPath = window.location.pathname;
  document.querySelectorAll(".nav-link").forEach((link) => {
    if (link.getAttribute("href") === currentPath) link.classList.add("active");
  });
}

function initNavbarMenu() {
  const navbarMenu = $("navbarMenu");
  if (!navbarMenu || !window.bootstrap) return;

  const collapse = bootstrap.Collapse.getOrCreateInstance(navbarMenu, { toggle: false });
  navbarMenu.querySelectorAll(".nav-link").forEach((link) => {
    link.addEventListener("click", () => {
      if (window.innerWidth < 992 && navbarMenu.classList.contains("show")) {
        collapse.hide();
      }
    });
  });
}

function showToast(title, body, variant) {
  const container = $("toastContainer");
  if (!container || !window.bootstrap) return;

  const id = "toast_" + Math.random().toString(16).slice(2);
  const headerClass =
    variant === "danger" ? "text-danger" : variant === "warning" ? "text-warning" : "text-success";

  const el = document.createElement("div");
  el.className = "toast";
  el.id = id;
  el.setAttribute("role", "alert");
  el.setAttribute("aria-live", "assertive");
  el.setAttribute("aria-atomic", "true");
  el.innerHTML = `
    <div class="toast-header">
      <strong class="me-auto ${headerClass}">${escapeHtml(title)}</strong>
      <small class="text-muted">ahora</small>
      <button type="button" class="btn-close btn-close-white ms-2 mb-1" data-bs-dismiss="toast" aria-label="Close"></button>
    </div>
    <div class="toast-body">${body}</div>
  `;
  container.appendChild(el);
  const toast = new bootstrap.Toast(el, { delay: 6500 });
  toast.show();
  el.addEventListener("hidden.bs.toast", () => el.remove());
}

async function pollEventNotifications() {
  const endpoint = document.body.getAttribute("data-events-poll-url");
  if (!endpoint) return;

  let lastId = 0;
  try {
    lastId = clampInt(localStorage.getItem("sd_last_event_id"), 0);
  } catch {
    // ignore
  }

  try {
    const res = await fetch(`${endpoint}?after_id=${lastId}`, { credentials: "same-origin" });
    if (!res.ok) return;
    const payload = await res.json();
    const latestId = typeof payload.latest_id === "number" ? payload.latest_id : null;
    if (latestId !== null && latestId < lastId) {
      try {
        localStorage.setItem("sd_last_event_id", String(latestId));
      } catch {
        // ignore
      }
      return;
    }
    if (lastId === 0 && latestId && latestId > 0) {
      try {
        localStorage.setItem("sd_last_event_id", String(latestId));
      } catch {
        // ignore
      }
      return;
    }
    const events = Array.isArray(payload.events) ? payload.events : [];
    if (!events.length) return;

    // Solo muestra toasts, no actualiza el badge aqui (loadEventsBadge ya lo hace)
    for (const evt of events) {
      const type = evt.type || "Evento";
      const plate = evt.plate || `Bus ${evt.bus_id ?? "?"}`;
      const when = evt.timestamp ? fmtLocalDate(evt.timestamp) : "sin fecha";
      const bodyParts = [
        `<div><strong>${escapeHtml(plate)}</strong></div>`,
        `<div class="text-muted">${escapeHtml(when)}</div>`,
      ];

      const description = evt.description ? String(evt.description).trim() : "";
      if (description) {
        const valueText =
          evt.value === null || evt.value === undefined || evt.value === "" ? "" : ` · ${escapeHtml(String(evt.value))}`;
        bodyParts.push(`<div class="mt-1">${escapeHtml(description)}${valueText}</div>`);
      }
      const body = bodyParts.join("");

      const variant =
        type === "Sobrecalentamiento" ? "danger" :
        type === "Exceso de velocidad" ? "warning" :
        type === "Otros" ? "warning" :
        "success";
      showToast(type, body, variant);
      if (typeof evt.id === "number") lastId = Math.max(lastId, evt.id);
    }

    try {
      localStorage.setItem("sd_last_event_id", String(lastId));
    } catch {
      // ignore
    }
  } catch {
    // ignore
  }
}

async function loadEventsBadge() {
  const badge = $("eventsBadge");
  if (!badge) return;
  try {
    const res = await fetch("/api/events/count", { credentials: "same-origin" });
    if (!res.ok) return;
    const data = await res.json();
    if (data.total > 0) {
      badge.textContent = String(data.total);
      badge.classList.remove("d-none");
    }
  } catch {
    // ignore
  }
}

function initEventNotifications() {
  const endpoint = document.body.getAttribute("data-events-poll-url");
  if (!endpoint) return;
  if (window.location.pathname === "/events") {
    const badge = $("eventsBadge");
    if (badge) {
      badge.textContent = "0";
      badge.classList.add("d-none");
    }
    return;
  }

  // Cargar conteo inicial y luego polling suave.
  loadEventsBadge();
  pollEventNotifications();
  setInterval(pollEventNotifications, 6000);
}

document.addEventListener("DOMContentLoaded", () => {
  initLayout();
  initActiveNav();
  initNavbarMenu();
  initEventNotifications();
});

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
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function isTouchLikeDevice() {
  try {
    return window.matchMedia("(hover: none), (pointer: coarse), (max-width: 991.98px)").matches;
  } catch {
    return window.innerWidth <= 992;
  }
}

function initLayout() {
  const syncDeviceClasses = () => {
    document.body.classList.toggle("touch-device", isTouchLikeDevice());
    document.body.classList.toggle("mobile-performance", isTouchLikeDevice());
  };
  syncDeviceClasses();
  window.addEventListener("resize", syncDeviceClasses);
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
  const toggler = document.querySelector(".app-navbar-toggler");
  const overlay = $("mobileNavOverlay");
  if (!navbarMenu || !toggler) return;

  const isMobileNav = () => window.matchMedia("(max-width: 991.98px)").matches;

  function openMobileNav() {
    if (!isMobileNav()) return;
    closeNotificationCenter();
    overlay.hidden = false;
    requestAnimationFrame(() => {
      navbarMenu.classList.add("is-open");
      navbarMenu.classList.add("show");
      navbarMenu.setAttribute("aria-hidden", "false");
      overlay.classList.add("is-open");
      document.body.classList.add("nav-drawer-open");
      toggler.setAttribute("aria-expanded", "true");
    });
  }

  function closeMobileNav() {
    navbarMenu.classList.remove("is-open");
    navbarMenu.classList.remove("show");
    navbarMenu.setAttribute("aria-hidden", "true");
    overlay?.classList.remove("is-open");
    document.body.classList.remove("nav-drawer-open");
    toggler.setAttribute("aria-expanded", "false");
    window.setTimeout(() => {
      if (!overlay?.classList.contains("is-open")) overlay.hidden = true;
    }, 230);
  }

  toggler.addEventListener("click", (event) => {
    if (!isMobileNav()) return;
    event.preventDefault();
    event.stopPropagation();
    if (navbarMenu.classList.contains("is-open")) closeMobileNav();
    else openMobileNav();
  });

  navbarMenu.querySelectorAll(".nav-link").forEach((link) => {
    link.addEventListener("click", () => {
      if (isMobileNav() && navbarMenu.classList.contains("is-open")) closeMobileNav();
    });
  });
  overlay?.addEventListener("click", closeMobileNav);
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && navbarMenu.classList.contains("is-open")) closeMobileNav();
  });
  window.addEventListener("resize", () => {
    if (!isMobileNav() && navbarMenu.classList.contains("is-open")) closeMobileNav();
  });
}

function initBootstrapPopovers() {
  if (!window.bootstrap) return;
  const touchMode = isTouchLikeDevice();
  document.querySelectorAll('[data-bs-toggle="tooltip"]').forEach((element) => {
    bootstrap.Tooltip.getOrCreateInstance(element, {
      container: "body",
      customClass: "glass-tooltip",
    });
  });
  document.querySelectorAll('[data-bs-toggle="popover"]').forEach((element) => {
    if (touchMode) {
      element.setAttribute("data-bs-trigger", "click");
    }
    bootstrap.Popover.getOrCreateInstance(element, {
      container: "body",
      customClass: "glass-popover",
      trigger: touchMode ? "click" : "hover focus",
    });
    if (touchMode) {
      element.addEventListener("click", (event) => {
        event.stopPropagation();
        document.querySelectorAll('[data-bs-toggle="popover"]').forEach((other) => {
          if (other !== element) bootstrap.Popover.getInstance(other)?.hide();
        });
      });
    }
  });
  if (touchMode) {
    document.addEventListener("click", (event) => {
      if (event.target.closest(".popover") || event.target.closest('[data-bs-toggle="popover"]')) return;
      document.querySelectorAll('[data-bs-toggle="popover"]').forEach((element) => {
        bootstrap.Popover.getInstance(element)?.hide();
      });
    });
  }
}

function initModalLayering() {
  document.querySelectorAll(".modal").forEach((modal) => {
    modal.addEventListener("show.bs.modal", () => {
      if (modal.parentElement !== document.body) {
        document.body.appendChild(modal);
      }
    });
  });
}

const NOTIFICATION_ITEMS_KEY_PREFIX = "sd_notification_items";
const NOTIFICATION_READ_KEY_PREFIX = "sd_notification_read_ids";
const EVENTS_LAST_POLLED_KEY_PREFIX = "sd_last_event_id";
const EVENTS_LAST_SEEN_KEY_PREFIX = "sd_events_seen_last_id";
const MAX_STORED_NOTIFICATIONS = 60;
let notificationItems = [];
let notificationReadIds = new Set();

function currentUsername() {
  const username = document.body?.dataset?.currentUser;
  return username ? String(username) : "guest";
}

function scopedStorageKey(prefix) {
  return `${prefix}::${currentUsername()}`;
}

function readStoredInt(key, fallback = 0) {
  try {
    const parsed = clampInt(localStorage.getItem(key), fallback);
    return Math.max(0, parsed);
  } catch {
    return fallback;
  }
}

function setStoredInt(key, value) {
  try {
    localStorage.setItem(key, String(Math.max(0, clampInt(value, 0))));
  } catch {
    // ignore
  }
}

function safeJsonParse(value, fallback) {
  try {
    return JSON.parse(value) ?? fallback;
  } catch {
    return fallback;
  }
}

function notificationKey(notification) {
  return String(notification.id || `${notification.type}-${notification.timestamp}-${notification.bus}`);
}

function loadNotificationState() {
  const itemsKey = scopedStorageKey(NOTIFICATION_ITEMS_KEY_PREFIX);
  const readKey = scopedStorageKey(NOTIFICATION_READ_KEY_PREFIX);
  try {
    notificationItems = safeJsonParse(localStorage.getItem(itemsKey), []);
    const readIds = safeJsonParse(localStorage.getItem(readKey), []);
    notificationReadIds = new Set(Array.isArray(readIds) ? readIds.map(String) : []);
  } catch {
    notificationItems = [];
    notificationReadIds = new Set();
  }
}

function saveNotificationState() {
  const itemsKey = scopedStorageKey(NOTIFICATION_ITEMS_KEY_PREFIX);
  const readKey = scopedStorageKey(NOTIFICATION_READ_KEY_PREFIX);
  try {
    localStorage.setItem(itemsKey, JSON.stringify(notificationItems.slice(0, MAX_STORED_NOTIFICATIONS)));
    localStorage.setItem(readKey, JSON.stringify(Array.from(notificationReadIds)));
  } catch {
    // ignore
  }
}

function unreadNotificationCount() {
  return notificationItems.filter((notification) => !notificationReadIds.has(notificationKey(notification))).length;
}

function updateNotificationBadge() {
  const badge = $("notificationBellBadge");
  if (!badge) return;
  const total = unreadNotificationCount();
  if (total > 0) {
    badge.textContent = total > 99 ? "99+" : String(total);
    badge.classList.remove("d-none");
  } else {
    badge.textContent = "0";
    badge.classList.add("d-none");
  }
}

function normalizeEventNotification(eventData) {
  const type = eventData.type || "Evento";
  const bus = eventData.plate || `Bus ${eventData.bus_id ?? "?"}`;
  const description = eventData.description ? String(eventData.description).trim() : "";
  const valueText =
    eventData.value === null || eventData.value === undefined || eventData.value === "" ? "" : String(eventData.value);
  return {
    id: eventData.id,
    type,
    bus,
    description,
    value: valueText,
    timestamp: eventData.timestamp || new Date().toISOString(),
  };
}

function notificationBodyText(notification) {
  const valueSuffix = notification.value ? ` · ${notification.value}` : "";
  const description = notification.description ? `${notification.description}${valueSuffix}` : "Evento registrado";
  return `${notification.bus}: ${description}`;
}

function addEventNotifications(events) {
  if (!Array.isArray(events) || !events.length) return;
  const existingIds = new Set(notificationItems.map(notificationKey));
  const newNotifications = [];

  events.forEach((eventData) => {
    const notification = normalizeEventNotification(eventData);
    const key = notificationKey(notification);
    if (!existingIds.has(key)) {
      newNotifications.push(notification);
      existingIds.add(key);
    }
  });

  if (!newNotifications.length) return;
  notificationItems = [...newNotifications.reverse(), ...notificationItems].slice(0, MAX_STORED_NOTIFICATIONS);
  saveNotificationState();
  renderNotificationCenter();
  updateNotificationBadge();
}

function browserNotificationsAvailable() {
  return "Notification" in window;
}

function updateBrowserNotificationUi() {
  const button = $("enableBrowserNotifications");
  const note = $("notificationPermissionNote");
  if (!button || !note) return;

  if (!browserNotificationsAvailable()) {
    button.disabled = true;
    button.innerHTML = '<i class="bi bi-bell-slash"></i> No compatible';
    note.textContent = "Este navegador no soporta notificaciones del sistema.";
    return;
  }

  if (Notification.permission === "granted") {
    button.disabled = true;
    button.innerHTML = '<i class="bi bi-check2-circle"></i> Notificaciones activas';
    note.textContent = "Las alertas críticas también pueden aparecer como notificaciones del navegador.";
  } else if (Notification.permission === "denied") {
    button.disabled = true;
    button.innerHTML = '<i class="bi bi-bell-slash"></i> Bloqueadas';
    note.textContent = "El navegador bloqueó las notificaciones. Puedes habilitarlas desde la configuración del sitio.";
  } else {
    button.disabled = false;
    button.innerHTML = '<i class="bi bi-bell"></i> Activar notificaciones';
    note.textContent = "Las notificaciones del navegador se activan solo si lo autorizas.";
  }
}

async function requestBrowserNotifications() {
  if (!browserNotificationsAvailable() || Notification.permission !== "default") {
    updateBrowserNotificationUi();
    return;
  }
  try {
    await Notification.requestPermission();
  } catch {
    // ignore
  }
  updateBrowserNotificationUi();
}

function showBrowserNotification(notification) {
  if (!browserNotificationsAvailable() || Notification.permission !== "granted") return;
  try {
    const browserNotification = new Notification(`SENTNLDRIVE - ${notification.type}`, {
      body: notificationBodyText(notification),
      icon: "/static/img/logo.png",
      tag: `sentinldrive-event-${notificationKey(notification)}`,
    });
    browserNotification.onclick = () => {
      window.focus();
      window.location.href = "/events";
    };
  } catch {
    // ignore
  }
}

function renderNotificationCenter() {
  const list = $("notificationList");
  const empty = $("notificationEmpty");
  if (!list || !empty) return;

  list.innerHTML = notificationItems
    .map((notification) => {
      const key = notificationKey(notification);
      const isUnread = !notificationReadIds.has(key);
      const valueSuffix = notification.value ? ` · ${escapeHtml(notification.value)}` : "";
      const description = notification.description ? `${escapeHtml(notification.description)}${valueSuffix}` : "Evento registrado";
      return `
        <article class="notification-item ${isUnread ? "is-unread" : ""}" data-notification-id="${escapeHtml(key)}">
          <span class="notification-icon"><i class="bi bi-exclamation-triangle"></i></span>
          <div>
            <p class="notification-title">${escapeHtml(notification.type)}</p>
            <p class="notification-meta">${escapeHtml(notification.bus)} · ${escapeHtml(fmtLocalDate(notification.timestamp))} · ${isUnread ? "Nueva" : "Leída"}</p>
            <p class="notification-description">${description}</p>
          </div>
          <button type="button" class="notification-read-button" data-notification-read="${escapeHtml(key)}" aria-label="Marcar como leída">
            <i class="bi ${isUnread ? "bi-circle" : "bi-check-circle"}"></i>
          </button>
        </article>
      `;
    })
    .join("");

  empty.classList.toggle("is-visible", notificationItems.length === 0);
  updateNotificationBadge();
}

function openNotificationCenter() {
  const panel = $("notificationCenter");
  const backdrop = $("notificationBackdrop");
  const bell = $("notificationBell");
  if (!panel || !backdrop || !bell) return;
  panel.classList.add("is-open");
  panel.setAttribute("aria-hidden", "false");
  bell.setAttribute("aria-expanded", "true");
  backdrop.hidden = false;
}

function closeNotificationCenter() {
  const panel = $("notificationCenter");
  const backdrop = $("notificationBackdrop");
  const bell = $("notificationBell");
  if (!panel || !backdrop || !bell) return;
  panel.classList.remove("is-open");
  panel.setAttribute("aria-hidden", "true");
  bell.setAttribute("aria-expanded", "false");
  backdrop.hidden = true;
}

function initNotificationCenter() {
  loadNotificationState();
  renderNotificationCenter();
  updateBrowserNotificationUi();

  const bell = $("notificationBell");
  const closeButton = $("notificationClose");
  const backdrop = $("notificationBackdrop");
  const enableButton = $("enableBrowserNotifications");
  const markAllButton = $("markAllNotificationsRead");
  const list = $("notificationList");

  if (bell) {
    bell.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      const panel = $("notificationCenter");
      if (document.querySelector(".app-navbar .navbar-collapse")?.classList.contains("is-open")) {
        document.querySelector(".app-navbar .navbar-collapse")?.classList.remove("is-open");
        document.querySelector(".app-navbar .navbar-collapse")?.classList.remove("show");
        $("mobileNavOverlay")?.classList.remove("is-open");
        document.body.classList.remove("nav-drawer-open");
        const toggler = document.querySelector(".app-navbar-toggler");
        toggler?.setAttribute("aria-expanded", "false");
        const overlay = $("mobileNavOverlay");
        if (overlay) overlay.hidden = true;
      }
      if (panel?.classList.contains("is-open")) closeNotificationCenter();
      else openNotificationCenter();
    });
  }
  closeButton?.addEventListener("click", closeNotificationCenter);
  backdrop?.addEventListener("click", closeNotificationCenter);
  enableButton?.addEventListener("click", requestBrowserNotifications);
  markAllButton?.addEventListener("click", () => {
    notificationItems.forEach((notification) => notificationReadIds.add(notificationKey(notification)));
    saveNotificationState();
    renderNotificationCenter();
  });
  list?.addEventListener("click", (event) => {
    const readButton = event.target.closest("[data-notification-read]");
    if (!readButton) return;
    notificationReadIds.add(String(readButton.getAttribute("data-notification-read")));
    saveNotificationState();
    renderNotificationCenter();
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") closeNotificationCenter();
  });
}

function showToast(title, body, variant) {
  const container = $("toastContainer");
  if (!container || !window.bootstrap) return;

  const id = "toast_" + Math.random().toString(16).slice(2);
  const headerClass =
    variant === "danger" ? "text-danger" : variant === "warning" ? "text-warning" : "text-success";

  const el = document.createElement("div");
  el.className = "toast notification-toast";
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
  const toast = new bootstrap.Toast(el, { delay: 4200 });
  toast.show();
  el.addEventListener("hidden.bs.toast", () => el.remove());
}

async function pollEventNotifications() {
  const endpoint = document.body.getAttribute("data-events-poll-url");
  if (!endpoint) return;

  const lastPolledKey = scopedStorageKey(EVENTS_LAST_POLLED_KEY_PREFIX);
  let lastId = readStoredInt(lastPolledKey, 0);

  try {
    const res = await fetch(`${endpoint}?after_id=${lastId}`, { credentials: "same-origin" });
    if (!res.ok) return;
    const payload = await res.json();
    const latestId = typeof payload.latest_id === "number" ? payload.latest_id : null;
    if (latestId !== null && latestId < lastId) {
      setStoredInt(lastPolledKey, latestId);
      return;
    }
    if (lastId === 0 && latestId && latestId > 0) {
      setStoredInt(lastPolledKey, latestId);
      return;
    }
    const events = Array.isArray(payload.events) ? payload.events : [];
    if (!events.length) return;

    addEventNotifications(events);

    for (const eventData of events) {
      const notification = normalizeEventNotification(eventData);
      const type = notification.type;
      const plate = notification.bus;
      const when = notification.timestamp ? fmtLocalDate(notification.timestamp) : "sin fecha";
      const bodyParts = [
        `<div><strong>${escapeHtml(plate)}</strong></div>`,
        `<div class="text-muted">${escapeHtml(when)}</div>`,
      ];

      const description = notification.description ? String(notification.description).trim() : "";
      if (description) {
        const valueText = notification.value ? ` · ${escapeHtml(String(notification.value))}` : "";
        bodyParts.push(`<div class="mt-1">${escapeHtml(description)}${valueText}</div>`);
      }
      const body = bodyParts.join("");

      const variant =
        type === "Sobrecalentamiento" ? "danger" :
        type === "Exceso de velocidad" ? "warning" :
        type === "Otros" ? "warning" :
        "success";
      showToast(type, body, variant);
      showBrowserNotification(notification);
      if (typeof eventData.id === "number") lastId = Math.max(lastId, eventData.id);
    }

    setStoredInt(lastPolledKey, lastId);
    loadEventsBadge();
  } catch {
    // ignore
  }
}

async function loadEventsBadge() {
  const badge = $("eventsBadge");
  if (!badge) return;
  const seenKey = scopedStorageKey(EVENTS_LAST_SEEN_KEY_PREFIX);
  const polledKey = scopedStorageKey(EVENTS_LAST_POLLED_KEY_PREFIX);
  const lastSeenId = readStoredInt(seenKey, 0);

  try {
    const res = await fetch(`/api/events/count?after_id=${lastSeenId}`, { credentials: "same-origin" });
    if (!res.ok) return;
    const data = await res.json();

    if (lastSeenId === 0 && data.latest_id > 0) {
      setStoredInt(seenKey, data.latest_id);
      if (readStoredInt(polledKey, 0) === 0) setStoredInt(polledKey, data.latest_id);
      badge.textContent = "0";
      badge.classList.add("d-none");
      return;
    }

    if (data.total > 0) {
      badge.textContent = String(data.total);
      badge.classList.remove("d-none");
    } else {
      badge.textContent = "0";
      badge.classList.add("d-none");
    }
  } catch {
    // ignore
  }
}

async function markEventsAsSeen() {
  const seenKey = scopedStorageKey(EVENTS_LAST_SEEN_KEY_PREFIX);
  const polledKey = scopedStorageKey(EVENTS_LAST_POLLED_KEY_PREFIX);
  try {
    const res = await fetch("/api/events/count?after_id=0", { credentials: "same-origin" });
    if (!res.ok) return;
    const data = await res.json();
    const latestId = clampInt(data.latest_id, 0);
    setStoredInt(seenKey, latestId);
    if (latestId > readStoredInt(polledKey, 0)) {
      setStoredInt(polledKey, latestId);
    }
  } catch {
    // ignore
  }
}

function initEventNotifications() {
  const endpoint = document.body.getAttribute("data-events-poll-url");
  if (!endpoint) return;
  if (window.location.pathname === "/events") {
    markEventsAsSeen();
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
  [
    initLayout,
    initActiveNav,
    initNavbarMenu,
    initBootstrapPopovers,
    initModalLayering,
    initNotificationCenter,
    initEventNotifications,
  ].forEach((initializer) => {
    try {
      initializer();
    } catch (error) {
      console.error("UI init failed:", initializer.name, error);
    }
  });
});

const PATHS = {
  zap: '<path d="M13 2 4 14h7l-1 8 9-12h-7z"/>',
  terminal: '<path d="m5 7 5 5-5 5M12 19h7"/>',
  bell: '<path d="M6 9a6 6 0 1 1 12 0c0 6 2 7 2 8H4c0-1 2-2 2-8M10 21h4"/>',
  globe: '<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3c3 3 3 15 0 18M12 3c-3 3-3 15 0 18"/>',
  clipboard: '<rect x="6" y="5" width="12" height="16" rx="2"/><path d="M9 5a3 3 0 0 1 6 0z"/>',
  keyboard: '<rect x="3" y="6" width="18" height="12" rx="2"/><path d="M7 10h.01M11 10h.01M15 10h.01M8 14h8"/>',
  "arrow-right": '<path d="M5 12h14M13 6l6 6-6 6"/>',
  folder: '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
  pause: '<path d="M9 5v14M15 5v14"/>',
  clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  tag: '<path d="M3 12V5a2 2 0 0 1 2-2h7l9 9-9 9zM8 8h.01"/>',
  moon: '<path d="M20 14A8 8 0 1 1 10 4a7 7 0 0 0 10 10"/>',
  sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4 12H2M22 12h-2M5 5l1.5 1.5M17.5 17.5 19 19M5 19l1.5-1.5M17.5 6.5 19 5"/>',
  branch: '<circle cx="6" cy="6" r="2"/><circle cx="18" cy="6" r="2"/><circle cx="6" cy="18" r="2"/><path d="M6 8v8M18 8c0 5-12 3-12 8"/>',
  repeat: '<path d="M4 11V9a3 3 0 0 1 3-3h13l-3-3M20 13v2a3 3 0 0 1-3 3H4l3 3"/>',
  play: '<path d="M7 4v16l13-8z" fill="currentColor"/>',
  stop: '<rect x="6" y="6" width="12" height="12" rx="1" fill="currentColor"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  search: '<circle cx="11" cy="11" r="7"/><path d="m20 20-4-4"/>',
  grid: '<rect x="4" y="4" width="7" height="7" rx="1"/><rect x="13" y="4" width="7" height="7" rx="1"/><rect x="4" y="13" width="7" height="7" rx="1"/><rect x="13" y="13" width="7" height="7" rx="1"/>',
  list: '<path d="M9 6h11M9 12h11M9 18h11M4 6h.01M4 12h.01M4 18h.01"/>',
  star: '<path d="m12 3 2.7 5.6 6.1.8-4.5 4.2 1.2 6.1L12 16.8 6.5 19.7l1.2-6.1L3.2 9.4l6.1-.8z"/>',
  more: '<path d="M5 12h.01M12 12h.01M19 12h.01"/>',
  home: '<path d="M3 11.5 12 4l9 7.5M5.5 10v10h13V10M10 20v-6h4v6"/>',
  mail: '<rect x="3" y="5" width="18" height="14" rx="2"/><path d="m3.5 7.5 8.5 6 8.5-6"/>',
  message: '<path d="M4 5h16a1 1 0 0 1 1 1v11a1 1 0 0 1-1 1H9l-5 4v-4a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1z"/>',
  phone: '<rect x="7" y="2.5" width="10" height="19" rx="2"/><path d="M11 18.5h2"/>',
  calendar: '<rect x="4" y="5" width="16" height="16" rx="2"/><path d="M4 10h16M8 3v4M16 3v4"/>',
  download: '<path d="M12 4v11M7 10l5 5 5-5M5 20h14"/>',
  cloud: '<path d="M7 19a4.5 4.5 0 0 1-.5-8.970A6 6 0 0 1 18 10.5a4.3 4.3 0 0 1-.5 8.5z"/>',
  wifi: '<path d="M3 9.5a13 13 0 0 1 18 0M6.5 13a8 8 0 0 1 11 0M9.7 16.5a3.5 3.5 0 0 1 4.6 0M12 20h.01"/>',
  battery: '<rect x="2.5" y="7" width="16" height="10" rx="2"/><path d="M21.5 11v2M6 10.5v3M10 10.5v3"/>',
  power: '<path d="M12 3v9M6.5 6.5a8 8 0 1 0 11 0"/>',
  key: '<circle cx="8" cy="15" r="4.5"/><path d="m11.5 12 8.5-8.5M16 7.5l3 3M13.5 10l2 2"/>',
  shield: '<path d="M12 3 5 6v6c0 4.5 3 7.5 7 9 4-1.5 7-4.5 7-9V6z"/>',
  heart: '<path d="M12 20.5S3.5 15.5 3.5 9.5A4.7 4.7 0 0 1 12 6.7a4.7 4.7 0 0 1 8.5 2.8c0 6-8.5 11-8.5 11z"/>',
  coffee: '<path d="M5 9h12v7a4 4 0 0 1-4 4H9a4 4 0 0 1-4-4zM17 10.5h1.5a2.5 2.5 0 0 1 0 5H17M8 3v3M12 3v3"/>',
  book: '<path d="M12 6.5C10 5 7 4.5 3.5 5v14c3.5-.5 6.5 0 8.5 1.5 2-1.5 5-2 8.5-1.5V5C17 4.5 14 5 12 6.5zM12 6.5v14"/>',
  pencil: '<path d="m4 20 1-4.5L16.5 4a2.1 2.1 0 0 1 3 3L8 18.8zM14.5 6l3 3"/>',
  gear: '<circle cx="12" cy="12" r="3"/><path d="M12 3v3M12 18v3M3 12h3M18 12h3M5.6 5.6l2.1 2.1M16.3 16.3l2.1 2.1M18.4 5.6l-2.1 2.1M7.7 16.3l-2.1 2.1"/>',
  code: '<path d="m8 7-5 5 5 5M16 7l5 5-5 5M14 4l-4 16"/>',
  database: '<ellipse cx="12" cy="6" rx="8" ry="3"/><path d="M4 6v12c0 1.7 3.6 3 8 3s8-1.3 8-3V6M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3"/>',
  monitor: '<rect x="3" y="4" width="18" height="12" rx="2"/><path d="M9 20h6M12 16v4"/>',
  music: '<circle cx="7" cy="18" r="2.5"/><circle cx="17" cy="16" r="2.5"/><path d="M9.5 18V6l10-2v12"/>',
  headphones: '<path d="M4 15v-3a8 8 0 0 1 16 0v3"/><rect x="3" y="14" width="4.5" height="6" rx="1.5"/><rect x="16.5" y="14" width="4.5" height="6" rx="1.5"/>',
  mic: '<rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5.5 11a6.5 6.5 0 0 0 13 0M12 17.5V21"/>',
  image: '<rect x="3" y="4" width="18" height="16" rx="2"/><circle cx="8.5" cy="9.5" r="1.5"/><path d="m4 18 5-5 3.5 3.5 3-3 4.5 4.5"/>',
  film: '<rect x="3" y="5" width="18" height="14" rx="2"/><path d="M8 5v14M16 5v14M3 10h5M3 14h5M16 10h5M16 14h5"/>',
  gamepad: '<path d="M7 7h10a5 5 0 0 1 5 5v2.5a3 3 0 0 1-5.5 1.7L15 14H9l-1.5 2.2A3 3 0 0 1 2 14.5V12a5 5 0 0 1 5-5zM7.5 9.5v3M6 11h3M15.5 11h.01M18 11h.01"/>',
  rocket: '<path d="M12 21c-1-1-2-2.5-2.5-4.5h5C14 18.5 13 20 12 21zM9.5 16.5c-1-3-.8-8.5 2.5-13 3.3 4.5 3.5 10 2.5 13zM9.3 12 6 15v3l3.5-1.5M14.7 12l3.3 3v3l-3.5-1.5M12 8.5h.01"/>',
  flag: '<path d="M5 21V4M5 4c5-2 8 2 14 0v10c-6 2-9-2-14 0"/>',
  gift: '<rect x="4" y="9" width="16" height="11" rx="1"/><path d="M3 9h18M12 9v11M12 9S10 3 7.5 4.5 9 9 12 9zM12 9s2-6 4.5-4.5S15 9 12 9z"/>',
  cart: '<path d="M3 4h2.5l2.5 11h10l2-8H6.5"/><circle cx="9.5" cy="19" r="1.5"/><circle cx="16.5" cy="19" r="1.5"/>',
  dollar: '<path d="M12 3v18M16.5 7.5C15.5 6 14 5.5 12 5.5c-2.5 0-4.5 1.3-4.5 3.3 0 4.7 9.5 2.2 9.5 6.7 0 2-2.2 3-5 3-2.2 0-4-.8-5-2.5"/>',
  droplet: '<path d="M12 3s6.5 6.7 6.5 11.5a6.5 6.5 0 0 1-13 0C5.5 9.7 12 3 12 3z"/>',
  flame: '<path d="M12 3c.5 3.5 6 6 6 11.5a6 6 0 0 1-12 0c0-2.5 1.5-4 2.5-5 .3 1.5 1 2.5 2 3 0-4 .5-7 1.5-9.5z"/>',
  leaf: '<path d="M20 4c0 10-4 16-11 16-3 0-5-2-5-5C4 8 12 4 20 4zM4 20c3-5 6-8 10-10"/>',
  bug: '<rect x="7.5" y="8" width="9" height="12" rx="4.5"/><path d="M9 8a3 3 0 0 1 6 0M3.5 13h4M16.5 13h4M4.5 7.5l3.5 3M19.5 7.5l-3.5 3M4.5 19l3.5-3M19.5 19l-3.5-3"/>',
  link: '<path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1"/>',
  pin: '<path d="M12 21.5s7-6.5 7-12a7 7 0 0 0-14 0c0 5.5 7 12 7 12z"/><circle cx="12" cy="9.5" r="2.5"/>',
  grip: '<path d="M9 6h.01M15 6h.01M9 12h.01M15 12h.01M9 18h.01M15 18h.01"/>',
  chevron: '<path d="m6 9 6 6 6-6"/>',
  back: '<path d="m15 6-6 6 6 6"/>',
  check: '<path d="m5 12 5 5 9-10"/>',
  x: '<path d="M6 6l12 12M18 6 6 18"/>',
  warn: '<circle cx="12" cy="12" r="9"/><path d="M12 8v5M12 16.5h.01"/>',
  skip: '<path d="M6 5v14l10-7zM19 5v14"/>',
  sliders: '<path d="M4 7h10M18 7h2M4 17h2M10 17h10"/><circle cx="16" cy="7" r="2"/><circle cx="8" cy="17" r="2"/>',
  trash: '<path d="M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13"/>',
  copy: '<rect x="8" y="8" width="12" height="12" rx="2"/><path d="M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2"/>',
  up: '<path d="m6 15 6-6 6 6"/>',
  sparkle: '<path d="M12 3v6M12 15v6M3 12h6M15 12h6"/>',
  upload: '<path d="M12 16V5M7 10l5-5 5 5M5 19h14"/>',
  undo: '<path d="M9 7 4 12l5 5M4 12h11a5 5 0 0 1 0 10h-2"/>',
  redo: '<path d="m15 7 5 5-5 5M20 12H9a5 5 0 0 0 0 10h2"/>',
  volume: '<path d="M4 10v4h3l5 4V6L7 10zM16 9a4 4 0 0 1 0 6M18.5 6.5a8 8 0 0 1 0 11"/>',
  camera: '<path d="M4 8h3l2-3h6l2 3h3a1 1 0 0 1 1 1v10a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V9a1 1 0 0 1 1-1z"/><circle cx="12" cy="13" r="3.5"/>',
  lock: '<rect x="5" y="11" width="14" height="10" rx="2"/><path d="M8 11V7a4 4 0 0 1 8 0v4"/>',
  type: '<path d="M5 6V4h14v2M12 4v16M9 20h6"/>',
  hash: '<path d="M5 9h15M4 15h15M10 3 8 21M16 3l-2 18"/>',
  help: '<circle cx="12" cy="12" r="9"/><path d="M9.5 9a2.5 2.5 0 1 1 3.5 2.3c-.7.3-1 .8-1 1.700M12 16.5h.01"/>',
};

export const ICON_CHOICES = ["zap", "star", "heart", "flag", "rocket", "flame",
  "bell", "clock", "calendar", "moon", "sun", "cloud", "droplet", "leaf",
  "home", "folder", "book", "pencil", "clipboard", "list", "tag", "key",
  "mail", "message", "phone", "globe", "link", "wifi", "pin", "download",
  "music", "headphones", "mic", "volume", "camera", "image", "film", "gamepad",
  "terminal", "code", "keyboard", "monitor", "database", "gear", "bug", "shield",
  "lock", "power", "battery", "cart", "dollar", "gift", "coffee"];
export const COLOR_CHOICES = ["yellow", "blue", "pink", "teal", "purple", "green", "orange", "gray"];
export const BOLD_COLORS = { "bold-red": "#e11d2e", "bold-orange": "#f2600c", "bold-yellow": "#ffc400",
  "bold-lime": "#84cc16", "bold-green": "#0fa958", "bold-teal": "#00a6a6", "bold-blue": "#1463ff",
  "bold-indigo": "#4b2fe0", "bold-purple": "#9b1fe8", "bold-pink": "#f0148c" };

const SVG_NS = "http://www.w3.org/2000/svg";

export function icon(name, size = 18) {
  const svg = document.createElementNS(SVG_NS, "svg");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("width", size);
  svg.setAttribute("height", size);
  svg.setAttribute("fill", "none");
  svg.setAttribute("stroke", "currentColor");
  svg.setAttribute("stroke-width", "1.8");
  svg.setAttribute("stroke-linecap", "round");
  svg.setAttribute("stroke-linejoin", "round");
  svg.setAttribute("aria-hidden", "true");
  svg.innerHTML = PATHS[name] || PATHS.zap; // our own constant table, never user data
  return svg;
}

export function h(tag, props = {}, ...children) {
  const element = document.createElement(tag);
  for (const [key, value] of Object.entries(props || {})) {
    if (value === undefined || value === null || value === false) continue;
    if (key === "class") element.className = value;
    else if (key.startsWith("on")) element.addEventListener(key.slice(2).toLowerCase(), value);
    else if (key === "value") element.value = value;
    else if (key === "checked" || key === "disabled" || key === "selected") element[key] = true;
    else element.setAttribute(key, value === true ? "" : value);
  }
  for (const child of children.flat(Infinity)) {
    if (child === null || child === undefined || child === false) continue;
    element.append(child.nodeType ? child : document.createTextNode(String(child)));
  }
  return element;
}

export function chip(color, name, size = 18) {
  return h("span", { class: `chip c-${color}` }, icon(name, size));
}

export function button(label, onclick, opts = {}) {
  return h("button", { type: "button", class: `btn ${opts.class || ""}`, onclick,
    disabled: opts.disabled, title: opts.title },
    opts.icon && icon(opts.icon, 16), label);
}

export function iconButton(name, label, onclick, cls = "") {
  return h("button", { type: "button", class: `icon-btn ${cls}`, "aria-label": label, title: label,
    onclick }, icon(name));
}

export function toggle(checked, onchange, label) {
  return h("label", { class: "switch" },
    h("input", { type: "checkbox", checked, "aria-label": label,
      onchange: (event) => onchange(event.target.checked) }),
    h("span", { class: "track" }));
}

export function segmented(options, value, onchange, label) {
  return h("div", { class: "segmented", role: "group", "aria-label": label },
    options.map(([id, text, name]) => h("button", {
      type: "button", class: id === value ? "on" : "", "aria-pressed": String(id === value),
      "aria-label": name, title: name, onclick: () => onchange(id) }, text)));
}

export function toast(text, kind = "info", action = null) {
  const host = document.getElementById("overlays");
  let stack = host.querySelector(".toasts");
  if (!stack) {
    stack = h("div", { class: "toasts", role: "status", "aria-live": "polite" });
    host.append(stack);
  }
  const item = h("div", { class: `toast ${kind}` }, text, action && h("button", { type: "button", class: "toast-action",
    onclick: () => { item.remove(); action.run(); } }, action.label));
  stack.append(item);
  setTimeout(() => item.remove(), kind === "error" || action ? 8000 : 3500);
}

export function modal(title, body, actions = [], opts = {}) {
  const previous = document.activeElement;
  const close = () => {
    backdrop.remove();
    document.removeEventListener("keydown", onKey, true);
    previous?.focus?.();
    opts.onclose?.();
  };
  const onKey = (event) => {
    if (event.key === "Escape") { event.stopPropagation(); close(); }
    if (event.key !== "Tab") return;
    const stops = [...panel.querySelectorAll("button,input,select,textarea,summary,[tabindex='0']")]
      .filter((el) => !el.disabled && el.offsetParent !== null);
    if (!stops.length) { event.preventDefault(); return; }
    const first = stops[0];
    const last = stops[stops.length - 1];
    const outside = !panel.contains(document.activeElement) || document.activeElement === panel;
    if (event.shiftKey && (document.activeElement === first || outside)) { event.preventDefault(); last.focus(); }
    else if (!event.shiftKey && (document.activeElement === last || outside)) { event.preventDefault(); first.focus(); }
  };
  const panel = h("div", { class: `modal ${opts.wide ? "wide" : ""}`, role: "dialog",
    "aria-modal": "true", "aria-label": title, tabindex: "-1" },
    h("h2", {}, title),
    h("div", { class: "modal-body" }, body),
    actions.length ? h("div", { class: "modal-actions" }, actions.map(([label, run, cls]) =>
      button(label, async () => { if ((await run?.()) !== false) close(); }, { class: cls }))) : null);
  const backdrop = h("div", { class: "backdrop", onmousedown: (event) => {
    if (event.target === backdrop) close();
  } }, panel);
  document.getElementById("overlays").append(backdrop);
  document.addEventListener("keydown", onKey, true);
  (opts.focusPanel ? panel : panel.querySelector("input,textarea,select") || panel).focus();
  return close;
}

export function confirmDialog(title, text, label, run, cls = "danger") {
  modal(title, h("p", {}, text), [["Cancel", null, ""], [label, run, cls]]);
}

export function menu(anchor, items) {
  document.querySelector(".menu")?.remove();
  const rect = anchor.getBoundingClientRect();
  const close = () => {
    list.remove();
    document.removeEventListener("mousedown", outside, true);
    document.removeEventListener("keydown", onKey, true);
  };
  const outside = (event) => { if (!list.contains(event.target)) close(); };
  const onKey = (event) => {
    if (event.key === "Escape") { event.stopPropagation(); close(); anchor.focus(); }
    if (event.key !== "ArrowDown" && event.key !== "ArrowUp") return;
    event.preventDefault();
    const stops = [...list.querySelectorAll("button:not(:disabled)")];
    const step = event.key === "ArrowDown" ? 1 : -1;
    stops[(stops.indexOf(document.activeElement) + step + stops.length) % stops.length].focus();
  };
  const list = h("div", { class: "menu", role: "menu" }, items.filter(Boolean).map((item) =>
    h("button", { type: "button", role: "menuitem", class: item.danger ? "danger" : "",
      disabled: item.disabled, onclick: () => { close(); item.run(); } },
      item.icon && icon(item.icon, 16), item.label)));
  document.getElementById("overlays").append(list);
  const width = list.offsetWidth;
  const height = list.offsetHeight;
  list.style.left = `${Math.max(8, Math.min(rect.right - width, innerWidth - width - 8))}px`;
  list.style.top = `${rect.bottom + height + 8 > innerHeight ? rect.top - height - 4 : rect.bottom + 4}px`;
  document.addEventListener("mousedown", outside, true);
  document.addEventListener("keydown", onKey, true);
  list.querySelector("button:not(:disabled)")?.focus();
}

export function when(epoch) {
  if (!epoch) return "—";
  return new Date(epoch * 1000).toLocaleString(undefined, {
    weekday: "short", month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
}

export function ago(epoch) {
  if (!epoch) return "never";
  const seconds = Math.max(0, Date.now() / 1000 - epoch);
  if (seconds < 60) return "just now";
  if (seconds < 3600) return `${Math.floor(seconds / 60)} min ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)} h ago`;
  return `${Math.floor(seconds / 86400)} d ago`;
}

export function until(epoch) {
  if (!epoch) return "";
  const date = new Date(epoch * 1000);
  const time = date.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
  const today = new Date();
  const tomorrow = new Date(today.getTime() + 86400000);
  if (date.toDateString() === today.toDateString()) return `today at ${time}`;
  if (date.toDateString() === tomorrow.toDateString()) return `tomorrow at ${time}`;
  return when(epoch);
}

export function duration(seconds) {
  if (seconds === null || seconds === undefined) return "—";
  if (seconds < 60) return `${seconds.toFixed(seconds < 10 ? 1 : 0)} s`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes} m ${Math.floor(seconds % 60)} s`;
  return `${Math.floor(minutes / 60)} h ${minutes % 60} m`;
}

export function hotkeyLabel(combo) {
  return (combo || "").split("+").map((part) => part.trim()).join(" + ");
}

export async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text);
  } catch {
    // WebKitGTK refuses the async clipboard on plain http.
    const area = h("textarea", { style: "position:fixed;opacity:0" }, text);
    document.body.append(area);
    area.select();
    document.execCommand("copy");
    area.remove();
  }
}

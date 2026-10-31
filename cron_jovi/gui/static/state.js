import { get } from "./api.js";

export const S = {
  view: { name: "library", filter: "all" },
  workflows: [],
  errors: [],
  status: null,
  actions: [],
  templates: [],
  search: "",
  sort: "recent",
  layout: "grid",
};

const listeners = [];

export function onChange(fn) { listeners.push(fn); }

export async function refresh() {
  const state = await get("/state");
  Object.assign(S, state);
  listeners.forEach((fn) => fn());
}

export function triggerKind(w) {
  if (w.hotkey) return "hotkey";
  if (w.schedule) return "scheduled";
  if (eventText(w)) return "event";
  return "manual";
}

function clock(text) {
  const [hours, minutes] = text.split(":").map(Number);
  const date = new Date(2000, 0, 1, hours, minutes);
  return date.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
}

export function scheduleText(spec) {
  const text = (spec || "").trim();
  let m;
  if ((m = /^daily at (\d{1,2}:\d\d)$/i.exec(text))) return `Daily at ${clock(m[1])}`;
  if ((m = /^weekdays at (\d{1,2}:\d\d)$/i.exec(text))) return `Weekdays at ${clock(m[1])}`;
  if ((m = /^weekly on (\w{3}) at (\d{1,2}:\d\d)$/i.exec(text))) return `${m[1]}s at ${clock(m[2])}`;
  if ((m = /^every (\d+) ?h/i.exec(text))) return m[1] === "1" ? "Every hour" : `Every ${m[1]} hours`;
  if ((m = /^every (\d+) ?m/i.exec(text))) return m[1] === "1" ? "Every minute" : `Every ${m[1]} minutes`;
  return text;
}

export function eventText(w) {
  const t = w.trigger || w;
  if (t.file) {
    const folder = (t.file.path || t.file).toString().replace(/\/$/, "").split("/").pop() || "/";
    return `File in ${folder}`;
  }
  if (t.device) return `${t.device.match || "USB device"} ${t.device.event === "removed" ? "unplugged" : "plugged in"}`;
  if (t.battery) return `Battery below ${t.battery.below}%`;
  if (t.power) return t.power === "plugged" ? "Power plugged in" : "Power unplugged";
  if (t.webhook) return "Web request";
  if (t.login) return "When you log in";
  if (t.wake) return "After sleep";
  return "";
}

export function triggerText(w) {
  if (w.hotkey) return w.hotkey;
  if (w.schedule) return scheduleText(w.schedule);
  return eventText(w) || "Run by hand";
}

export function needsHotkeyLink() {
  const links = S.status?.hotkey_links || [];
  return S.workflows.some((w) => w.enabled && w.hotkey) && links.some((link) => !link.linked);
}

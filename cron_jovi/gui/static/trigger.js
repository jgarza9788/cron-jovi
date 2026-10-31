import { get, post } from "./api.js";
import { button, chip, copyText, h, hotkeyLabel, icon, iconButton, menu, modal, toast, until } from "./ui.js";
import { S } from "./state.js";

const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const MODIFIER_KEYS = ["Control", "Shift", "Alt", "Meta", "OS", "Super", "Hyper", "AltGraph"];
const customMode = new WeakSet(); // keeps Custom open while its text matches a friendly form
const KEY_NAMES = { " ": "Space", ArrowUp: "Up", ArrowDown: "Down", ArrowLeft: "Left", ArrowRight: "Right" };

export function parseSchedule(spec) {
  const text = (spec || "").trim();
  let m;
  if ((m = /^daily at (\d{1,2}:\d\d)$/i.exec(text))) return { kind: "daily", time: m[1].padStart(5, "0") };
  if ((m = /^weekdays at (\d{1,2}:\d\d)$/i.exec(text))) return { kind: "weekdays", time: m[1].padStart(5, "0") };
  if ((m = /^weekly on (\w{3}) at (\d{1,2}:\d\d)$/i.exec(text))) return { kind: "weekly", day: m[1], time: m[2].padStart(5, "0") };
  if ((m = /^every (\d+) ?h/i.exec(text))) return { kind: "hours", every: Number(m[1]) };
  if ((m = /^every (\d+) ?m/i.exec(text))) return { kind: "minutes", every: Number(m[1]) };
  return { kind: "custom", text };
}

export function formatSchedule(s) {
  switch (s.kind) {
    case "daily": return `daily at ${s.time}`;
    case "weekdays": return `weekdays at ${s.time}`;
    case "weekly": return `weekly on ${s.day} at ${s.time}`;
    case "hours": return `every ${s.every}h`;
    case "minutes": return `every ${s.every}m`;
    default: return s.text;
  }
}

function comboFromEvent(event) {
  if (MODIFIER_KEYS.includes(event.key)) return null;
  const parts = [];
  if (event.metaKey) parts.push("Super");
  if (event.ctrlKey) parts.push("Ctrl");
  if (event.altKey) parts.push("Alt");
  if (event.shiftKey) parts.push("Shift");
  let key = event.key;
  if (/^Key[A-Z]$/.test(event.code)) key = event.code.slice(3);
  else if (/^Digit\d$/.test(event.code)) key = event.code.slice(5);
  else key = KEY_NAMES[key] || (key.length === 1 ? key.toUpperCase() : key);
  return [...parts, key].join("+");
}

function hotkeyDialog(current, slug, onPick) {
  let combo = current || "";
  const show = h("div", { class: "keycap", "aria-live": "polite" }, combo ? hotkeyLabel(combo) : "Press your keys…");
  const note = h("div", { class: "key-note" });
  const accept = (value) => {
    combo = value;
    show.textContent = hotkeyLabel(value);
    note.replaceChildren();
    post("/hotkey/check", { hotkey: value, slug }).then(({ conflicts }) => {
      note.replaceChildren(...conflicts.map((text) => h("div", { class: "banner" }, icon("warn"), h("p", {}, text))));
    }).catch((err) => {
      note.replaceChildren(h("div", { class: "banner error" }, icon("warn"), h("p", {}, err.message)));
    });
  };
  const typed = h("input", { class: "input mono", placeholder: "Or type it, like Super+Shift+F", "aria-label": "Type a hotkey",
    oninput: (event) => { if (event.target.value.trim()) accept(event.target.value.trim()); } });
  const listen = (event) => {
    if (event.target === typed || event.key === "Tab" || event.key === "Escape" || event.key === "Enter") return;
    const value = comboFromEvent(event);
    event.preventDefault();
    if (value) accept(value);
  };
  document.addEventListener("keydown", listen, true);
  modal("Choose a hotkey", [
    show,
    h("p", {}, "Hold the keys together. If nothing shows up, your desktop is already using that shortcut, so try another."),
    typed, note,
  ], [["Cancel", null, ""], ["Use this hotkey", () => { if (combo) onPick(combo); }, "primary"]],
  { focusPanel: true, onclose: () => document.removeEventListener("keydown", listen, true) });
}

function scheduleBuilder(trigger, ctx, rerender) {
  const s = customMode.has(trigger) ? { kind: "custom", text: trigger.schedule } : parseSchedule(trigger.schedule);
  const write = (next) => {
    trigger.schedule = formatSchedule(next);
    ctx.changed();
    preview();
  };
  const kind = h("select", { class: "pill-select", "aria-label": "How often",
    onchange: (event) => {
      const id = event.target.value;
      if (id === "custom") customMode.add(trigger); else customMode.delete(trigger);
      const starts = { daily: { time: "09:00" }, weekdays: { time: "09:00" }, weekly: { day: "Mon", time: "09:00" },
        hours: { every: 2 }, minutes: { every: 15 }, custom: { text: trigger.schedule } };
      trigger.schedule = formatSchedule({ kind: id, ...starts[id] });
      ctx.changed();
      rerender();
    } }, [["daily", "Every day at"], ["weekdays", "Every weekday at"], ["weekly", "Every week on"],
    ["hours", "Every few hours"], ["minutes", "Every few minutes"], ["custom", "Custom"]].map(([id, text]) =>
    h("option", { value: id, selected: id === s.kind }, text)));
  const parts = [kind];
  if (s.kind === "weekly") {
    parts.push(h("select", { class: "pill-select", "aria-label": "Day",
      onchange: (event) => { s.day = event.target.value; write(s); } },
    DAYS.map((d) => h("option", { value: d, selected: d === s.day }, d))), "at");
  }
  if (s.time) {
    parts.push(h("input", { class: "pill-input", type: "time", value: s.time, "aria-label": "Time",
      oninput: (event) => { if (event.target.value) { s.time = event.target.value; write(s); } } }));
  }
  if (s.every) {
    parts.push(h("input", { class: "pill-input num", type: "number", min: "1", value: s.every, "aria-label": "How often",
      oninput: (event) => { if (Number(event.target.value) > 0) { s.every = Number(event.target.value); write(s); } } }),
    s.kind === "hours" ? "hours" : "minutes");
  }
  if (s.kind === "custom") {
    parts.push(h("input", { class: "pill-input mono wide", value: s.text, spellcheck: "false", "aria-label": "systemd calendar expression",
      oninput: (event) => { s.text = event.target.value; write(s); } }));
  }
  const next = h("p", { class: "hint" });
  let pending = 0;
  const preview = () => {
    const ticket = ++pending;
    post("/schedule/preview", { schedule: trigger.schedule })
      .then((data) => {
        if (ticket !== pending) return;
        next.textContent = data.next.length ? `Next run: ${data.next.map(until).join(", then ")}` : "This schedule never comes up";
      })
      .catch(() => { if (ticket === pending) next.textContent = "That schedule isn't valid yet"; });
  };
  preview();
  return [h("div", { class: "block-row wrap" }, parts), next];
}

function choice(name, trigger, key, options, ctx, rerender) {
  return h("div", { class: "choices", role: "radiogroup" }, options.map(([id, title, text]) => {
    const selected = (trigger[key] || options[0][0]) === id;
    return h("label", { class: `choice ${selected ? "on" : ""}` },
      h("input", { type: "radio", name, checked: selected,
        onchange: () => { trigger[key] = id; ctx.changed(); rerender(); } }),
      h("span", {}, h("strong", {}, title), h("small", {}, text)));
  }));
}

const FILE_EVENTS = [["created", "is added"], ["modified", "changes"], ["deleted", "is deleted"]];
const EVENT_KEYS = ["hotkey", "schedule", "file", "device", "battery", "power", "webhook", "login", "wake"];

function pillSelect(label, options, value, onchange) {
  return h("select", { class: "pill-select", "aria-label": label, onchange: (event) => onchange(event.target.value) },
    options.map(([id, text]) => h("option", { value: id, selected: id === value }, text)));
}

function eventRow(glyph, removeLabel, onRemove, ...content) {
  return h("div", { class: "block" }, h("div", { class: "block-row wraps" }, chip("yellow", glyph), content,
    h("span", { class: "grow" }), iconButton("x", removeLabel, onRemove)));
}

function noBatteryHint() {
  return S.status?.has_battery ? null : h("p", { class: "hint inset" }, "This computer has no built-in battery, so this won't fire here.");
}

function fileRow(trigger, commit, rerender) {
  const spec = trigger.file;
  const row = eventRow("folder", "Remove file trigger", () => { delete trigger.file; commit(); rerender(); },
    "When a file",
    pillSelect("File event", FILE_EVENTS, (spec.events || ["created"])[0], (value) => { spec.events = [value]; commit(); }),
    "in",
    // Saved when you leave the box: half-typed folders would restart the engine.
    h("input", { class: "pill-input mono wide", value: spec.path, spellcheck: "false", "aria-label": "Folder", placeholder: "~/Downloads",
      onchange: (event) => { spec.path = event.target.value.trim(); commit(); } }));
  row.append(h("div", { class: "details" },
    h("div", { class: "field" }, h("span", {}, "Only files matching (optional)"),
      h("input", { class: "input mono", value: spec.pattern && spec.pattern !== "*" ? spec.pattern : "", placeholder: "*.pdf", "aria-label": "File pattern",
        onchange: (event) => { spec.pattern = event.target.value.trim() || "*"; commit(); } })),
    h("label", { class: "check" }, h("input", { type: "checkbox", checked: Boolean(spec.recursive),
      onchange: (event) => { spec.recursive = event.target.checked; commit(); } }), "Include folders inside it"),
    h("p", { class: "hint" }, "Actions can use the file through the tag button: file.name and file.path.")));
  return row;
}

function deviceRow(trigger, commit, rerender) {
  const spec = trigger.device;
  return eventRow("zap", "Remove device trigger", () => { delete trigger.device; commit(); rerender(); },
    "When",
    h("input", { class: "pill-input wide", value: spec.match || "", placeholder: "any USB device", "aria-label": "Device name",
      onchange: (event) => { spec.match = event.target.value.trim(); commit(); } }),
    pillSelect("Device event", [["added", "is plugged in"], ["removed", "is unplugged"]], spec.event || "added",
      (value) => { spec.event = value; commit(); }));
}

function batteryRow(trigger, commit, rerender) {
  const row = eventRow("warn", "Remove battery trigger", () => { delete trigger.battery; commit(); rerender(); },
    "When the battery drops below",
    h("input", { class: "pill-input num", type: "number", min: "1", max: "99", value: trigger.battery.below, "aria-label": "Battery percent",
      oninput: (event) => { trigger.battery.below = Number(event.target.value); commit(); } }), "%");
  row.append(noBatteryHint() || "");
  return row;
}

function powerRow(trigger, commit, rerender) {
  const row = eventRow("zap", "Remove power trigger", () => { delete trigger.power; commit(); rerender(); },
    "When the computer is",
    pillSelect("Power event", [["plugged", "plugged in"], ["unplugged", "unplugged"]], trigger.power,
      (value) => { trigger.power = value; commit(); }));
  row.append(noBatteryHint() || "");
  return row;
}

function webhookRow(trigger, commit, rerender, slug) {
  const address = h("code", { class: "codebox" }, "…");
  get(`/webhook/${slug}`).then(({ url }) => { address.textContent = url; }).catch(() => {});
  const row = eventRow("globe", "Remove web request trigger", () => { delete trigger.webhook; commit(); rerender(); },
    "When a web request arrives");
  row.append(h("div", { class: "details" }, address,
    h("p", { class: "hint" }, "Send a POST to this address from a script on this computer. It isn't reachable from other machines. Actions can read what was sent as webhook.body."),
    h("div", {}, button("Copy address", () => copyText(address.textContent).then(() => toast("Copied")), { class: "small" }))));
  return row;
}

export function triggerSection(data, slug, ctx) {
  const trigger = data.trigger || {};
  const host = h("div", {});
  const commit = () => {
    const any = EVENT_KEYS.some((key) => trigger[key]);
    if (any) data.trigger = trigger;
    else delete data.trigger;
    if (!trigger.schedule) delete trigger.if_missed;
    if (!trigger.schedule && !EVENT_KEYS.slice(2).some((key) => trigger[key])) delete trigger.if_running;
    ctx.changed();
  };
  const rerender = () => host.replaceChildren(...paint());
  const trackedCtx = { changed: commit };
  const pick = () => hotkeyDialog(trigger.hotkey, slug, (combo) => { trigger.hotkey = combo; commit(); rerender(); });
  const add = (apply) => () => { apply(); commit(); rerender(); };
  const addMenu = (event) => menu(event.currentTarget, [
    !trigger.hotkey && { label: "A hotkey", icon: "keyboard", run: pick },
    !trigger.schedule && { label: "A schedule", icon: "clock", run: add(() => {
      trigger.schedule = "daily at 09:00";
      trigger.if_missed = "run_once";
    }) },
    !trigger.file && { label: "A file changes", icon: "folder", run: add(() => { trigger.file = { path: "~/Downloads", events: ["created"] }; }) },
    !trigger.device && { label: "A device is plugged in", icon: "zap", run: add(() => { trigger.device = { match: "", event: "added" }; }) },
    !trigger.battery && { label: "The battery runs low", icon: "warn", run: add(() => { trigger.battery = { below: 15 }; }) },
    !trigger.power && { label: "Power is plugged or unplugged", icon: "zap", run: add(() => { trigger.power = "unplugged"; }) },
    !trigger.webhook && { label: "A web request arrives", icon: "globe", run: add(() => { trigger.webhook = true; }) },
    !trigger.login && { label: "You log in", icon: "play", run: add(() => { trigger.login = true; }) },
    !trigger.wake && { label: "The computer wakes from sleep", icon: "sun", run: add(() => { trigger.wake = true; }) },
  ]);
  const paint = () => {
    const rows = [];
    if (trigger.hotkey) {
      rows.push(h("div", { class: "block" }, h("div", { class: "block-row" }, chip("yellow", "keyboard"),
        "When", h("span", { class: "pill" }, "Hotkey"), "is pressed",
        h("button", { type: "button", class: "pill key", onclick: pick, "aria-label": `Change hotkey ${trigger.hotkey}` }, hotkeyLabel(trigger.hotkey)),
        h("span", { class: "grow" }),
        iconButton("x", "Remove hotkey", () => { delete trigger.hotkey; commit(); rerender(); }))));
    }
    if (trigger.schedule) {
      rows.push(h("div", { class: "block" },
        h("div", { class: "block-row" }, chip("yellow", "clock"), h("strong", {}, "On a schedule"),
          h("span", { class: "grow" }),
          iconButton("x", "Remove schedule", () => { delete trigger.schedule; commit(); rerender(); })),
        h("div", { class: "details" },
          scheduleBuilder(trigger, trackedCtx, rerender),
          h("h2", { class: "ask" }, "If the computer is asleep or off at that time"),
          choice(`${slug}-missed`, trigger, "if_missed", [
            ["run_once", "Run once when the computer is back", "Several missed times still mean one run, never a replay."],
            ["skip", "Skip it", "Wait for the next time. History shows “skipped: machine was off”."],
          ], trackedCtx, rerender))));
    }
    if (trigger.file) rows.push(fileRow(trigger, commit, rerender));
    if (trigger.device) rows.push(deviceRow(trigger, commit, rerender));
    if (trigger.battery) rows.push(batteryRow(trigger, commit, rerender));
    if (trigger.power) rows.push(powerRow(trigger, commit, rerender));
    if (trigger.webhook) rows.push(webhookRow(trigger, commit, rerender, slug));
    if (trigger.login) {
      rows.push(eventRow("play", "Remove login trigger", () => { delete trigger.login; commit(); rerender(); }, "When you log in"));
    }
    if (trigger.wake) {
      rows.push(eventRow("sun", "Remove wake trigger", () => { delete trigger.wake; commit(); rerender(); }, "When the computer wakes from sleep"));
    }
    if (trigger.schedule || EVENT_KEYS.slice(2).some((key) => trigger[key])) {
      rows.push(h("div", { class: "block" }, h("div", { class: "details flat" },
        h("h2", { class: "ask" }, "If the previous run is still going"),
        choice(`${slug}-overlap`, trigger, "if_running", [
          ["skip", "Skip the new run", "History shows “skipped: previous run still active”."],
          ["restart", "Stop the old run, start fresh", "Sends SIGTERM to the old run first."],
        ], trackedCtx, rerender))));
    }
    if (!EVENT_KEYS.some((key) => trigger[key])) {
      rows.push(h("p", { class: "hint pad" }, "Right now this only runs when you press Run."));
    }
    rows.push(h("div", { class: "add-row" }, button("Add a trigger", addMenu, { class: "small", icon: "plus" })));
    return rows;
  };
  rerender();
  return host;
}

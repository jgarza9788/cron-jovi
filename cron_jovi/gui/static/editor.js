import { del, get, post, put } from "./api.js";
import { ago, button, chip, COLOR_CHOICES, confirmDialog, duration, h, hotkeyLabel, ICON_CHOICES, icon, iconButton, menu, modal, segmented, toast, toggle } from "./ui.js";
import { S, eventText, refresh, scheduleText, triggerKind, triggerText, needsHotkeyLink } from "./state.js";
import { actionPanel, newStep, stepList, unfinishedSteps } from "./steps.js";
import { triggerSection } from "./trigger.js";
import { historyPanel, resultTag } from "./history.js";
import { startRun, testStep } from "./runner.js";
import { go } from "./main.js";
import { folders, newWorkflowDialog } from "./library.js";
import { hotkeyBanner } from "./settings.js";

const E = { marks: {}, slug: null, data: null, yaml: "", tab: "blocks", timer: null, saving: null, again: false,
  undo: [], redo: [], snapshot: "",
  error: "", expanded: new WeakSet(), run: null, log: [], logMeta: null, filter: "" };
let parts = {};

function sidebar() {
  const query = E.filter.toLowerCase();
  const list = S.workflows.filter((w) => !query || w.name.toLowerCase().includes(query));
  const group = (kind, title) => {
    const items = list.filter((w) => triggerKind(w) === kind);
    if (!items.length) return null;
    return [h("div", { class: "side-label" }, title), items.map((w) => h("button", {
      type: "button", class: `side-item ${w.slug === E.slug ? "on" : ""}`, onclick: () => go({ name: "editor", slug: w.slug }) },
      icon({ hotkey: "keyboard", scheduled: "clock", event: "zap", manual: "play" }[kind]),
      h("span", { class: "stack" }, w.name, h("small", {}, triggerText(w)))))];
  };
  return [group("hotkey", "Hotkey"), group("scheduled", "Scheduled"), group("event", "On event"),
    group("manual", "Manual")];
}

export function updateEditorSidebar() {
  parts.sideList?.replaceChildren(...sidebar().flat(Infinity).filter(Boolean));
}

function setSaveState() {
  if (!parts.saveState) return;
  const notes = [];
  if (E.error) notes.push(h("div", { class: "banner error" }, icon("warn"), h("p", {}, `Not saved yet: ${friendly(E.error)}`)));
  if (E.conflict) {
    notes.push(h("div", { class: "banner error" }, icon("warn"),
      h("p", {}, "This workflow's file was changed outside the app, so your latest edit isn't saved."),
      button("Use the file", reloadFromFile, { class: "small" }),
      button("Keep mine", keepMine, { class: "small" })));
  }
  parts.saveBanner.replaceChildren(...notes);
  parts.saveState.textContent = E.error ? "" : E.saving ? "Saving…" : "";
}

function friendly(message) {
  const text = message.replace(/^\S+\.yaml: /, "");
  const step = /(?:steps|on_failure)\[(\d+)\]/.exec(text)?.[1];
  const where = step ? `Step ${step}` : "This workflow";
  if (/unknown action|unknown condition/.test(text)) return `${where} uses something this version of Cron Jovi doesn't have.`;
  if (/missing option/.test(text)) return `${where} still needs filling in.`;
  if (/not a number/.test(text)) return `${where} needs a number.`;
  if (/unknown option|must be one of|not a duration|not a boolean/.test(text)) return `${where} has a setting that doesn't look right.`;
  if (/too many steps/.test(text)) return "This workflow has too many steps.";
  if (/bad hotkey/.test(text)) return "That hotkey isn't a valid key combination.";
  if (/invalid YAML/.test(text)) return "The file has a formatting mistake, so it can't be read.";
  return text.replace(/steps\[(\d+)\]/g, "step $1");
}

async function flush() {
  clearTimeout(E.timer);
  E.timer = null;
  if (E.data) snapshot();
  if (E.saving) { E.again = true; await E.saving; return; }
  const slug = E.slug;
  E.saving = (async () => {
    try {
      const { messages, stamp } = await put(`/workflows/${slug}`, E.data, E.stamp);
      E.stamp = stamp;
      E.error = "";
      E.conflict = false;
      messages.filter((m) => !m.includes("not loaded yet")).forEach((m) => toast(m));
      await refresh();
    } catch (err) {
      E.conflict = Boolean(err.changed);
      E.error = err.changed ? "" : err.message;
    }
  })();
  setSaveState();
  await E.saving;
  E.saving = null;
  setSaveState();
  if (E.again) { E.again = false; await flush(); }
}

/** Painting needs these lists, so they must exist before a snapshot or undo sees a change. */
const withLists = (data) => ({ ...data, steps: data.steps || [], on_failure: data.on_failure || [] });

function snapshot() {
  const now = JSON.stringify(E.data);
  if (now === E.snapshot) return;
  E.undo.push(E.snapshot);
  E.undo = E.undo.slice(-100);
  E.redo = [];
  E.snapshot = now;
  paintUndo();
}

function restore(source, target) {
  snapshot(); // this can replace the lists, so look them up afterwards
  if (!E[source].length) return;
  E[target].push(E.snapshot);
  E.data = withLists(JSON.parse(E[source].pop()));
  E.snapshot = JSON.stringify(E.data);
  paintHeader();
  paintTab();
  paintUndo();
  clearTimeout(E.timer);
  E.timer = setTimeout(flush, 100);
}

const undo = () => restore("undo", "redo");
const redo = () => restore("redo", "undo");

function paintUndo() {
  if (!parts.undoSlot) return;
  const make = (glyph, label, run, list) => {
    const control = iconButton(glyph, label, run);
    control.disabled = !list.length;
    return control;
  };
  parts.undoSlot.replaceChildren(make("undo", "Undo", undo, E.undo), make("redo", "Redo", redo, E.redo));
}

document.addEventListener("keydown", (event) => {
  if (S.view.name !== "editor" || E.tab !== "blocks") return;
  if (!(event.ctrlKey || event.metaKey) || event.key.toLowerCase() !== "z") return;
  if (document.querySelector(".modal")) return;
  // Text boxes keep their own undo while you're typing in them.
  if (event.target.matches("input,textarea")) return;
  event.preventDefault();
  if (event.shiftKey) redo(); else undo();
});

async function reloadFromFile() {
  const fresh = await get(`/workflows/${E.slug}`);
  const data = withLists(fresh.data);
  Object.assign(E, { data, yaml: fresh.yaml, stamp: fresh.stamp, conflict: false, error: "",
    snapshot: JSON.stringify(data) });
  setSaveState();
  paintHeader();
  paintTab();
}

async function keepMine() {
  E.stamp = "";
  E.conflict = false;
  await flush();
}

async function tryStep(step) {
  if (E.tab !== "blocks") return;
  E.log = [];
  E.logMeta = { running: true };
  paintLog();
  try {
    await testStep(step, {
      onLine: (line) => { E.log.push(line); paintLog(); },
      onDone: (code) => {
        E.logMeta = { tested: code === 0 ? "good" : "bad" };
        paintLog();
      },
    });
  } catch (err) {
    E.logMeta = null;
    paintLog();
    toast(friendly(err.message), "error");
  }
}

function changed() {
  if (E.slug === null) return;
  clearTimeout(E.timer);
  E.timer = setTimeout(flush, 500);
}

const ctx = {
  changed,
  structure(save = true) {
    if (save) E.marks = {}; // numbering may have shifted, so old marks could land on the wrong step
    paintBlocks();
    if (save) changed();
  },
  expanded: E.expanded,
  root: () => [...(E.data.steps || []), ...(E.data.on_failure || [])],
  trigger: () => E.data.trigger || {},
  offerUndo: (text) => toast(text, "info", { label: "Undo", run: undo }),
  testStep: tryStep,
  slug: () => E.slug,
};

function appendAction(name) {
  const step = newStep(name);
  E.expanded.add(step);
  E.data.steps.push(step);
  ctx.structure();
  requestAnimationFrame(() => {
    const blocks = parts.canvas.querySelectorAll(":scope .steps.main > .block");
    blocks[blocks.length - 1]?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  });
}

function runLog() {
  const log = E.logMeta;
  let head = h("span", { class: "muted" }, "Not run yet");
  if (log?.running) head = h("span", { class: "result dim" }, icon("clock", 14), "Running…");
  else if (log?.tested) {
    head = h("span", { class: `result ${log.tested}` }, icon(log.tested === "good" ? "check" : "x", 14),
      log.tested === "good" ? "Step worked" : "Step failed");
  } else if (log?.row) head = resultTag(log.row);
  const extra = log?.row?.finished_at ? ` · ${duration(log.row.finished_at - log.row.started_at)}` : "";
  const problem = log?.row?.status === "failed" ? log.row.note : "";
  return h("section", { class: "run-log", "aria-label": "Run log" },
    h("div", { class: "output-head" }, h("strong", {}, "Run log"), head, extra,
      h("span", { class: "grow" }),
      button("Open full log", () => { setTab("history"); }, { class: "small ghost" })),
    problem ? h("p", { class: "plain-error", role: "alert" }, icon("warn", 16), problem) : null,
    // The numbers stay under Technical details; this pane is for people.
    h("pre", { class: "output compact", tabindex: "0" },
      E.log.map((line) => line.replace(/(: \S+ exited \d+)? \(exit \d+\)$/, "")).join("\n")));
}

function paintLog() {
  if (!parts.logHost) return;
  parts.logHost.replaceChildren(runLog());
  const pre = parts.logHost.querySelector("pre");
  pre.scrollTop = pre.scrollHeight;
}

async function run() {
  if (E.run) { await E.run.stop(); return; }
  if (E.timer || E.saving) await flush();
  if (E.error) { toast("Fix the problem shown first, then run again.", "error"); return; }
  if (!E.data.steps.length) { toast("Add an action first, so there's something to run.", "error"); return; }
  const blanks = unfinishedSteps(E.data.steps) + unfinishedSteps(E.data.on_failure);
  if (blanks) {
    paintBlocks();
    toast(`${blanks} step${blanks === 1 ? " needs" : "s need"} filling in first`, "error");
    return;
  }
  const slug = E.slug;
  E.log = [];
  E.logMeta = { running: true };
  E.marks = {};
  paintMarks(false);
  paintLog();
  paintRunButton();
  try {
    E.run = await startRun(slug, {
      onLine: (line) => {
        if (E.slug === slug) { E.log.push(line); paintLog(); }
      },
      onDone: async () => {
        E.run = null;
        if (E.slug !== slug) return;
        const [row] = await get(`/history?workflow=${slug}&limit=1`);
        E.logMeta = { row };
        paintLog();
        paintRunButton();
        parts.history?.reload?.();
      },
    });
    paintRunButton();
  } catch (err) {
    E.logMeta = null;
    toast(err.message, "error");
    paintRunButton();
  }
}

function paintRunButton() {
  parts.runSlot?.replaceChildren(E.run
    ? button("Stop", run, { icon: "stop", class: "danger" })
    : button("Run", run, { icon: "play", class: "primary" }));
}

function addActionDialog() {
  const close = modal("Add an action", actionPanel((name) => { close(); appendAction(name); }));
}

function paintBlocks() {
  if (!parts.canvas) return;
  const data = E.data;
  data.steps = data.steps || [];
  data.on_failure = data.on_failure || [];
  const scroll = parts.canvas.scrollTop;
  const main = stepList(data.steps, ctx, "Add your first action from the list on the right");
  main.classList.add("main");
  parts.canvas.replaceChildren(h("div", { class: "canvas-inner" },
    h("div", { class: "side-label flush" }, "Description"),
    h("textarea", { class: "textarea description", value: data.description || "", "aria-label": "Description",
      placeholder: "What does this workflow do, and why? (optional)",
      oninput: (event) => {
        if (event.target.value) data.description = event.target.value;
        else delete data.description;
        changed();
      } }),
    h("div", { class: "side-label flush" }, "Trigger"),
    triggerSection(data, E.slug, ctx),
    h("div", { class: "side-label flush" }, "Actions"),
    main,
    h("div", { class: "add-row narrow-only" }, button("Add action", addActionDialog, { class: "small", icon: "plus" })),
    h("div", { class: "side-label flush" }, "If something goes wrong"),
    stepList(data.on_failure, ctx, "Optional: drag a step here, like a notification", "on_failure")));
  parts.canvas.scrollTop = scroll;
  paintMarks(false);
}

function paintMarks(follow = true) {
  const blocks = parts.canvas?.querySelectorAll("[data-path]") || [];
  blocks.forEach((element) => {
    const state = E.marks[element.dataset.path];
    element.classList.remove("step-running", "step-ok", "step-failed", "step-stopped");
    element.removeAttribute("aria-current");
    if (!state) return;
    element.classList.add(`step-${state}`);
    if (state === "running") element.setAttribute("aria-current", "step");
  });
  const current = [...blocks].filter((element) => E.marks[element.dataset.path] === "running").pop();
  if (follow && current && current !== parts.followed) {
    parts.followed = current;
    current.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }
}

let watching = false;

async function watchProgress() {
  if (watching) return;
  watching = true;
  let active = false;
  while (S.view.name === "editor") {
    const slug = E.slug;
    let running = false;
    if (slug && E.tab === "blocks") {
      try {
        const progress = await get(`/workflows/${slug}/progress`);
        running = progress.running;
        // Keep the last result on screen, but only pick marks up from a run seen here.
        if (slug === E.slug && (running || active)) {
          E.marks = progress.steps;
          paintMarks();
        }
      } catch { /* the offline banner covers this */ }
    }
    active = running;
    await new Promise((resolve) => { setTimeout(resolve, running || E.run ? 250 : 1000); });
  }
  watching = false;
}

function iconPicker(event) {
  const body = [
    h("div", { class: "picker" }, ICON_CHOICES.map((name) => h("button", { type: "button",
      class: `pick ${E.data.icon === name ? "on" : ""}`, "aria-label": name,
      onclick: () => { E.data.icon = name; update(); } }, icon(name)))),
    h("div", { class: "picker" }, COLOR_CHOICES.map((color) => h("button", { type: "button",
      class: `pick swatch c-${color} ${E.data.color === color ? "on" : ""}`, "aria-label": color,
      onclick: () => { E.data.color = color; update(); } }))),
  ];
  const update = () => { changed(); close(); paintHeader(); };
  const close = modal("Icon and color", body);
}

function folderDialog() {
  const input = h("input", { class: "input", value: E.data.folder || "", list: "folders", placeholder: "Folder name", "aria-label": "Folder name" });
  modal("Move to folder", [input, h("datalist", { id: "folders" }, folders().map((f) => h("option", { value: f }))),
    h("p", {}, "Leave it empty to take this workflow out of its folder.")],
  [["Cancel", null, ""], ["Save", () => {
    if (input.value.trim()) E.data.folder = input.value.trim(); else delete E.data.folder;
    changed();
  }, "primary"]]);
}

function workflowMenu(event) {
  menu(event.currentTarget, [
    { label: E.data.favorite ? "Remove from favorites" : "Add to favorites", icon: "star",
      run: () => { E.data.favorite = !E.data.favorite; changed(); } },
    { label: "Move to folder…", icon: "folder", run: folderDialog },
    { label: "Export to share…", icon: "upload", run: async () => {
      try {
        await flush();
        const save = async (confirmed) => {
          const reply = await post(`/workflows/${E.slug}/export`, { confirmed });
          if (reply.path) toast(`Saved a copy to ${reply.path}`, "success");
          return reply;
        };
        const { secrets } = await save(false);
        if (secrets) {
          confirmDialog("This may contain a password or key",
            `Anyone you share it with could read it. Check: ${secrets.join(", ")}.`, "Export anyway", () => save(true));
        }
      } catch (err) { toast(err.message, "error"); }
    } },
    { label: "Duplicate", icon: "copy", run: async () => {
      await flush();
      const { slug } = await post("/workflows", { ...structuredClone(E.data), name: `${E.data.name} copy`, enabled: false });
      await refresh();
      go({ name: "editor", slug });
    } },
    { label: "Delete", icon: "trash", danger: true, run: () => confirmDialog(
      `Delete “${E.data.name}”?`, "This removes the workflow and its hotkey or schedule. Its run history stays in the log.", "Delete",
      async () => {
        clearTimeout(E.timer);
        await del(`/workflows/${E.slug}`);
        E.slug = null;
        await refresh();
        go({ name: "library", filter: "all" });
      }) },
  ]);
}

function headerSubtitle() {
  const w = S.workflows.find((item) => item.slug === E.slug);
  const count = (w?.actions ?? 0);
  const bits = [];
  if (E.data.trigger?.hotkey) bits.push(`Runs on ${hotkeyLabel(E.data.trigger.hotkey)}`);
  else if (E.data.trigger?.schedule) bits.push(w?.next_run ? `Next run ${new Date(w.next_run * 1000).toLocaleString(undefined, { weekday: "short", hour: "numeric", minute: "2-digit" })}` : scheduleText(E.data.trigger.schedule));
  else if (eventText(E.data)) bits.push(eventText(E.data));
  else bits.push("Runs when you press Run");
  bits.push(`${count} action${count === 1 ? "" : "s"}`);
  if (w?.last_run) bits.push(`last run ${ago(w.last_run.started_at || w.last_run.scheduled_at)}`);
  return bits.join(" · ");
}

function setTab(tab) {
  E.tab = tab;
  paintTab();
  paintHeader();
}

function paintHeader() {
  const enabled = E.data.enabled !== false;
  parts.header.replaceChildren(
    h("button", { type: "button", class: "big-icon", "aria-label": "Change icon and color", title: "Change icon and color", onclick: iconPicker },
      chip(E.data.color || "yellow", E.data.icon || "zap", 24)),
    h("div", { class: "title-stack" },
      h("input", { class: "title-input", value: E.data.name, "aria-label": "Workflow name", maxlength: "80",
        oninput: (event) => {
          E.data.name = event.target.value;
          parts.topName.textContent = E.data.name;
          parts.heading.textContent = E.data.name;
          if (E.data.name.trim()) changed();
        } }),
      h("p", {}, headerSubtitle())),
    h("span", { class: "save-state" }),
    segmented([["blocks", "Blocks"], ["yaml", "YAML"], ["history", "History"]], E.tab, setTab, "View"),
    h("label", { class: "enabled" }, enabled ? "On" : "Off"),
    toggle(enabled, (value) => { E.data.enabled = value; changed(); paintHeader(); }, "Workflow on or off"),
    iconButton("more", "Workflow options", workflowMenu));
  parts.saveState = parts.header.querySelector(".save-state");
}

function yamlPanel() {
  const area = h("textarea", { class: "yaml-editor", spellcheck: "false", "aria-label": "Workflow file", value: E.yaml });
  const note = h("p", { class: "hint" }, "This is the file itself. Editing blocks rewrites it and drops any comments.");
  const save = async () => {
    try {
      await put(`/workflows/${E.slug}/yaml`, { yaml: area.value }, E.stamp);
      const fresh = await get(`/workflows/${E.slug}`);
      E.data = withLists(fresh.data); E.yaml = fresh.yaml; E.error = ""; E.stamp = fresh.stamp;
      await refresh();
      toast("Saved", "success");
      paintHeader();
    } catch (err) {
      toast(err.changed ? "The file changed outside the app. Open the Blocks tab to choose which to keep."
        : friendly(err.message), "error");
    }
  };
  return h("div", { class: "yaml-wrap" }, area, h("div", { class: "yaml-foot" }, note, h("span", { class: "grow" }),
    button("Save file", save, { class: "primary small" })));
}

async function paintTab() {
  const host = parts.tabHost;
  parts.canvas = null;
  parts.logHost = null;
  parts.history = null;
  if (E.tab === "blocks") {
    parts.canvas = h("div", { class: "canvas" });
    parts.logHost = h("div", {});
    host.replaceChildren(parts.canvas, parts.logHost);
    paintBlocks();
    paintLog();
    parts.panel.replaceChildren(actionPanel(appendAction));
  } else if (E.tab === "yaml") {
    if (E.timer || E.saving) await flush();
    const fresh = await get(`/workflows/${E.slug}`);
    E.yaml = fresh.yaml;
    host.replaceChildren(yamlPanel());
    parts.panel.replaceChildren();
  } else {
    parts.history = historyPanel(E.slug, run);
    host.replaceChildren(h("div", { class: "canvas pad" }, parts.history));
    parts.panel.replaceChildren();
  }
}

export async function renderEditor(top, body) {
  const slug = S.view.slug;
  if (E.timer) await flush();
  const fresh = await get(`/workflows/${slug}`).catch((err) => {
    toast(err.message, "error");
    go({ name: "library", filter: "all" });
    return null;
  });
  if (!fresh) return;
  if (slug !== E.slug) {
    E.log = [];
    E.logMeta = fresh.summary.last_run ? { row: fresh.summary.last_run } : null;
    if (fresh.summary.last_run?.id) {
      get(`/history/${fresh.summary.last_run.id}`).then((row) => {
        if (E.slug === slug) { E.log = row.output.split("\n").filter(Boolean); paintLog(); }
      }).catch(() => {});
    }
    E.tab = "blocks";
    E.run = null;
    Object.assign(E, { undo: [], redo: [], marks: {} });
  }
  const data = withLists(fresh.data);
  Object.assign(E, { slug, data, yaml: fresh.yaml, stamp: fresh.stamp, error: "", conflict: false,
    snapshot: JSON.stringify(data) });

  parts = {};
  parts.topName = h("strong", {}, E.data.name);
  parts.runSlot = h("span", {});
  parts.undoSlot = h("span", { class: "undo-slot" });
  top.replaceChildren(
    iconButton("back", "Back to library", () => go({ name: "library", filter: "all" })),
    parts.undoSlot,
    h("div", { class: "top-title" }, parts.topName, h("span", {}, "Cron Jovi")),
    parts.runSlot);
  paintRunButton();
  paintUndo();

  parts.sideList = h("div", {});
  const left = h("nav", { class: "side editor-side", "aria-label": "Workflows" },
    h("label", { class: "search" }, icon("search"), h("input", { type: "search", placeholder: "Filter workflows", value: E.filter,
      "aria-label": "Filter workflows", oninput: (event) => { E.filter = event.target.value; updateEditorSidebar(); } })),
    parts.sideList,
    h("div", { class: "fill" }),
    button("New Workflow", newWorkflowDialog, { icon: "plus" }));
  parts.heading = h("h1", { class: "sr-only" }, E.data.name);
  parts.header = h("div", { class: "editor-head" });
  parts.saveBanner = h("div", {});
  parts.notice = h("div", {});
  parts.tabHost = h("div", { class: "tab-host" });
  parts.panel = h("div", { class: "panel-host" });
  body.replaceChildren(left, h("section", { class: "editor" }, parts.heading, parts.header, parts.saveBanner, parts.notice, parts.tabHost), parts.panel);
  updateEditorSidebar();
  paintHeader();
  paintNotice();
  await paintTab();
  watchProgress();
}

export function paintNotice() {
  parts.notice?.replaceChildren(...(needsHotkeyLink() ? [hotkeyBanner()] : []));
}

export function onStateRefresh() {
  updateEditorSidebar();
  paintNotice();
  const current = S.workflows.find((w) => w.slug === E.slug);
  if (current && E.stamp && current.stamp !== E.stamp && !E.timer && !E.saving && !E.conflict && !E.error) {
    // Nothing unsaved here, so a change on disk can simply appear.
    reloadFromFile().then(() => toast("Updated from the file")).catch(() => {});
    return;
  }
  if (parts.header && !document.activeElement?.classList.contains("title-input")) {
    const line = parts.header.querySelector(".title-stack p");
    if (line) line.textContent = headerSubtitle();
  }
}

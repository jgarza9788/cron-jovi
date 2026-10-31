import { post, put, get } from "./api.js";
import { button, h, icon, iconButton, modal, segmented, toast, ago } from "./ui.js";
import { S, refresh, triggerKind, triggerText, needsHotkeyLink } from "./state.js";
import { quickRun } from "./runner.js";
import { go } from "./main.js";
import { hotkeyBanner, importWorkflow, pausedBanner } from "./settings.js";

const FILTERS = [
  ["all", "All Workflows", "grid"],
  ["favorites", "Favorites", "star"],
  ["hotkey", "Hotkey", "keyboard"],
  ["scheduled", "Scheduled", "clock"],
  ["event", "On event", "zap"],
  ["manual", "Manual", "play"],
];

function matches(workflow, filter) {
  if (filter === "all") return true;
  if (filter === "favorites") return workflow.favorite;
  if (filter.startsWith("folder:")) return workflow.folder === filter.slice(7);
  return triggerKind(workflow) === filter;
}

export function folders() {
  return [...new Set(S.workflows.map((w) => w.folder).filter(Boolean))].sort();
}

export function sidebar(active) {
  const item = (filter, label, glyph) => h("button", {
    type: "button", class: `side-item ${active === filter ? "on" : ""}`,
    onclick: () => go({ name: "library", filter }) },
    icon(glyph), label,
    h("span", { class: "count" }, S.workflows.filter((w) => matches(w, filter)).length));
  const groups = folders();
  return h("nav", { class: "side", "aria-label": "Workflows" },
    h("button", { type: "button", class: `side-item ${active === "overview" ? "on" : ""}`,
      onclick: () => go({ name: "overview" }) }, icon("sparkle"), "Overview"),
    FILTERS.map(([id, label, glyph]) => item(id, label, glyph)),
    groups.length ? h("div", { class: "side-label" }, "Folders") : null,
    groups.map((name) => item(`folder:${name}`, name, "folder")),
    h("div", { class: "fill" }),
    h("button", { type: "button", class: `side-item ${active === "gallery" ? "on" : ""}`,
      onclick: () => go({ name: "gallery" }) }, icon("globe"), "Gallery"),
    h("button", { type: "button", class: `side-item ${active === "log" ? "on" : ""}`,
      onclick: () => go({ name: "log" }) }, icon("terminal"), "Run log"),
    h("button", { type: "button", class: `side-item ${active === "settings" ? "on" : ""}`,
      onclick: () => go({ name: "settings" }) }, icon("sliders"), "Settings"));
}

function subtitle(workflow) {
  const glyph = { hotkey: "keyboard", scheduled: "clock", event: "zap", manual: "play" }[triggerKind(workflow)];
  const count = `${workflow.actions} action${workflow.actions === 1 ? "" : "s"}`;
  const off = workflow.enabled ? "" : " · Off";
  const failed = !workflow.running && workflow.last_run?.status === "failed";
  return [icon(glyph, 13), `${triggerText(workflow)} · ${count}${off}`,
    workflow.running ? h("span", { class: "card-state" }, "Running…") : null,
    failed ? h("span", { class: "card-state" }, icon("warn", 13), "Last run failed") : null];
}

async function setFavorite(workflow, value) {
  const { data, stamp } = await get(`/workflows/${workflow.slug}`);
  await put(`/workflows/${workflow.slug}`, { ...data, favorite: value }, stamp);
  await refresh();
}

function card(workflow) {
  return h("article", { class: `card c-${workflow.color} ${workflow.enabled ? "" : "off"}`, title: workflow.description || null },
    h("button", { type: "button", class: "open", "aria-label": `Open ${workflow.name}`,
      onclick: () => go({ name: "editor", slug: workflow.slug }) }),
    h("span", { class: "glyph" }, icon(workflow.icon, 20)),
    h("div", { style: "pointer-events:none" },
      h("h2", {}, workflow.name),
      h("small", {}, subtitle(workflow))),
    h("div", { class: "card-actions" },
      h("button", { type: "button", class: `fav ${workflow.favorite ? "on" : ""}`,
        "aria-label": workflow.favorite ? "Remove from favorites" : "Add to favorites",
        onclick: () => setFavorite(workflow, !workflow.favorite).catch((e) => toast(e.message, "error")) },
        icon("star", 15)),
      workflow.running
        ? h("button", { type: "button", class: "play", "aria-label": `Stop ${workflow.name}`, title: "Stop",
          onclick: () => post(`/workflows/${workflow.slug}/stop`).then(refresh).catch((e) => toast(e.message, "error")) }, icon("stop", 14))
        : h("button", { type: "button", class: "play", "aria-label": `Run ${workflow.name}`,
          title: "Run now", onclick: () => quickRun(workflow) }, icon("play", 14))));
}

function row(workflow) {
  return h("div", { class: "row" },
    h("span", { class: `chip c-${workflow.color}` }, icon(workflow.icon)),
    h("button", { type: "button", class: "btn ghost", style: "padding:0;height:auto;flex:1;justify-content:flex-start;color:inherit",
      onclick: () => go({ name: "editor", slug: workflow.slug }) },
      h("span", { class: "meta", style: "text-align:left" },
        h("strong", {}, workflow.name),
        h("small", {}, workflow.description.split("\n")[0] || triggerText(workflow), workflow.enabled ? "" : " · Off"))),
    h("small", { style: "color:var(--text-dim)" },
      workflow.last_run ? `Last run ${ago(workflow.last_run.started_at || workflow.last_run.scheduled_at)}` : "Never run"),
    iconButton("play", `Run ${workflow.name}`, () => quickRun(workflow)));
}

function sorted(list) {
  const stamp = (w) => w.last_run?.started_at || w.last_run?.scheduled_at || 0;
  const copy = [...list];
  if (S.sort === "name") copy.sort((a, b) => a.name.localeCompare(b.name));
  else copy.sort((a, b) => stamp(b) - stamp(a) || a.name.localeCompare(b.name));
  return copy;
}

export function newWorkflowDialog() {
  const blank = async () => {
    const name = nameInput.value.trim() || "New Workflow";
    const { slug } = await post("/workflows", { name, icon: "zap", color: "yellow", steps: [] });
    await refresh();
    go({ name: "editor", slug });
  };
  const fromTemplate = (template) => async () => {
    close();
    const data = { ...template.workflow, enabled: false };
    const { slug } = await post("/workflows", data);
    await refresh();
    go({ name: "editor", slug });
    toast("Added, switched off. Review it, then turn it on.");
  };
  const nameInput = h("input", { class: "input", placeholder: "Name your workflow", "aria-label": "Workflow name",
    onkeydown: (event) => { if (event.key === "Enter") { event.preventDefault(); close(); blank().catch((e) => toast(e.message, "error")); } } });
  const body = [
    nameInput,
    h("div", { class: "side-label", style: "padding:6px 0 0" }, "Or start from an idea"),
    h("div", { class: "template-grid" }, S.templates.map((template) =>
      h("button", { type: "button", class: "template",
        onclick: () => fromTemplate(template)().catch((e) => toast(e.message, "error")) },
        h("span", { class: `chip c-${template.workflow.color}` }, icon(template.workflow.icon)),
        h("span", {}, h("strong", {}, template.workflow.name), h("small", {}, template.blurb))))),
  ];
  const close = modal("New workflow", body, [
    ["Import a file…", () => { importWorkflow(); }, "ghost"],
    ["Cancel", null, ""],
    ["Create", () => blank().catch((e) => { toast(e.message, "error"); return false; }), "primary"],
  ], { wide: true });
}

export function renderLibrary(top, body) {
  const filter = S.view.filter || "all";
  const search = h("label", { class: "search" }, icon("search"),
    h("input", { type: "search", placeholder: "Search workflows", value: S.search, "aria-label": "Search workflows",
      oninput: (event) => { S.search = event.target.value; content(); } }));
  top.replaceChildren(
    button("New", newWorkflowDialog, { class: "primary", icon: "plus" }),
    h("div", { class: "top-search" }, search));

  const page = h("section", { class: "page" });
  const content = () => {
    const title = FILTERS.find(([id]) => id === filter)?.[1] || filter.replace("folder:", "");
    const query = S.search.trim().toLowerCase();
    const visible = sorted(S.workflows.filter((w) => matches(w, filter)
      && (!query || `${w.name} ${w.description}`.toLowerCase().includes(query))));
    const on = visible.filter((w) => w.enabled).length;
    const head = h("div", { class: "page-head" },
      h("div", { class: "grow" }, h("h1", {}, title),
        h("p", {}, `${visible.length} workflow${visible.length === 1 ? "" : "s"} · ${on} on`)),
      h("select", { class: "select", "aria-label": "Sort", onchange: (event) => { S.sort = event.target.value; content(); } },
        h("option", { value: "recent", selected: S.sort === "recent" }, "Recently used"),
        h("option", { value: "name", selected: S.sort === "name" }, "Name")),
      segmented([["grid", icon("grid", 16), "Show as cards"], ["list", icon("list", 16), "Show as a list"]], S.layout,
        (value) => { S.layout = value; content(); }, "Layout"));
    const notices = [
      S.status?.paused ? pausedBanner() : null,
      needsHotkeyLink() ? hotkeyBanner() : null,
      ...S.errors.map((error) => h("div", { class: "banner error" }, icon("warn"),
        h("p", {}, `A workflow file couldn't be read: ${error}`))),
    ];
    let main;
    if (!S.workflows.length) {
      main = h("div", { class: "empty" }, icon("zap", 40), h("h2", {}, "Make your first workflow"),
        h("p", {}, "Pick something that should happen, and when."),
        button("New workflow", newWorkflowDialog, { class: "primary", icon: "plus" }));
    } else if (!visible.length) {
      main = h("div", { class: "empty" }, h("h2", {}, "Nothing here"),
        h("p", {}, query ? `No workflows match “${S.search}”.` : "No workflows in this group yet."));
    } else if (S.layout === "list") {
      main = h("div", { class: "rows" }, visible.map(row));
    } else {
      main = h("div", { class: "cards" }, visible.map(card),
        h("button", { type: "button", class: "tile", onclick: newWorkflowDialog }, icon("plus", 22), "New Workflow"));
    }
    page.replaceChildren(head, ...notices.filter(Boolean), main);
  };
  content();
  body.replaceChildren(sidebar(filter), page);
  return content;
}

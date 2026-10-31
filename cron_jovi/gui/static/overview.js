import { ago, button, h, icon, until } from "./ui.js";
import { S, needsHotkeyLink, triggerText } from "./state.js";
import { newWorkflowDialog, sidebar } from "./library.js";
import { go } from "./main.js";
import { hotkeyDialog, setPaused, toolDialog } from "./settings.js";

function workflowRow(workflow, detail, tail) {
  return h("div", { class: "row" }, h("span", { class: `chip c-${workflow.color}` }, icon(workflow.icon)),
    h("button", { type: "button", class: "run-link", "aria-label": `Open ${workflow.name}`,
      onclick: () => go({ name: "editor", slug: workflow.slug }) },
    h("span", { class: "meta" }, h("strong", {}, workflow.name), h("small", {}, detail))), tail);
}

function attention() {
  const items = [];
  const add = (text, label, run) => items.push(h("div", { class: "row" }, icon("warn"),
    h("div", { class: "meta" }, text), button(label, run, { class: "small" })));
  if (S.status?.paused) add("Everything is paused", "Resume", () => setPaused(false));
  if (needsHotkeyLink()) add("Your hotkeys aren't switched on", "Turn on", hotkeyDialog);
  if (!["running", "not needed"].includes(S.status?.engine)) {
    add("The engine isn't running, so event triggers won't fire", "Settings", () => go({ name: "settings" }));
  }
  const failed = S.workflows.filter((w) => w.last_run?.status === "failed");
  failed.forEach((w) => add(`${w.name} failed ${ago(w.last_run.started_at)}`, "See why", () => go({ name: "editor", slug: w.slug })));
  S.errors.forEach((text) => add(`A workflow file can't be read: ${text}`, "Settings", () => go({ name: "settings" })));
  const missing = (S.status?.tools || []).filter((tool) => !tool.found);
  missing.forEach((tool) => add(`${tool.tool} isn't installed`, "How to", () => toolDialog(tool)));
  return items;
}

export function renderOverview(top, body) {
  top.replaceChildren(button("New", newWorkflowDialog, { class: "primary", icon: "plus" }),
    h("div", { class: "top-title" }, h("strong", {}, "Overview"), h("span", {}, "Cron Jovi")));
  const page = h("section", { class: "page" });
  const paint = () => {
    const upcoming = S.workflows.filter((w) => w.next_run && !S.status?.paused).sort((a, b) => a.next_run - b.next_run).slice(0, 6);
    const recent = S.workflows.filter((w) => w.last_run)
      .sort((a, b) => (b.last_run.started_at || b.last_run.scheduled_at) - (a.last_run.started_at || a.last_run.scheduled_at)).slice(0, 6);
    const watching = S.workflows.filter((w) => w.enabled && !w.next_run && triggerText(w) !== "Run by hand");
    const issues = attention();
    page.replaceChildren(h("div", { class: "page-head" }, h("div", {}, h("h1", {}, "Overview"),
      h("p", {}, `${S.workflows.filter((w) => w.enabled).length} of ${S.workflows.length} workflows on`))),
    h("div", { class: "overview" },
      h("div", {}, h("h2", { class: "section" }, "Needs attention"),
        issues.length ? h("div", { class: "rows" }, issues)
          : h("div", { class: "all-good" }, icon("check"), "All good")),
      h("div", {}, h("h2", { class: "section" }, "Coming up"),
        upcoming.length ? h("div", { class: "rows" }, upcoming.map((w) => workflowRow(w, until(w.next_run))))
          : h("div", { class: "all-good" }, "Nothing scheduled")),
      h("div", {}, h("h2", { class: "section" }, "Waiting for a trigger"),
        watching.length ? h("div", { class: "rows" }, watching.slice(0, 6).map((w) => workflowRow(w, triggerText(w))))
          : h("div", { class: "all-good" }, "No hotkeys or events on")),
      h("div", {}, h("h2", { class: "section" }, "Recently ran"),
        recent.length ? h("div", { class: "rows" }, recent.map((w) => workflowRow(w,
          `${w.last_run.status} ${ago(w.last_run.started_at || w.last_run.scheduled_at)}`)))
          : h("div", { class: "all-good" }, "Nothing has run yet"))));
  };
  paint();
  body.replaceChildren(sidebar("overview"), page);
  return paint;
}

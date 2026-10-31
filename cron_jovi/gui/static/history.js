import { get } from "./api.js";
import { button, copyText, duration, h, icon, segmented, toast, when } from "./ui.js";
import { S } from "./state.js";

const RESULT = {
  succeeded: ["check", "good", () => "Succeeded"],
  failed: ["x", "bad", () => "Failed"],
  skipped: ["skip", "warn", () => "Skipped"],
  stopped: ["stop", "warn", () => "Stopped"],
  running: ["clock", "dim", () => "Running"],
};

export function resultTag(row) {
  const [glyph, tone, text] = RESULT[row.status] || RESULT.running;
  return h("span", { class: `result ${tone}` }, icon(glyph, 14), text(row));
}

function outputView(text) {
  return h("pre", { class: "output", tabindex: "0" }, (text || "No output was recorded.").split("\n").map((line) => {
    const tone = /^\S+ fail\b/.test(line) || /\b(error|failed|denied)\b/i.test(line) ? "bad"
      : line.startsWith("$ ") ? "cmd" : /^\d\d:\d\d:\d\d ok\b/.test(line) ? "dim" : "";
    return h("span", { class: tone }, `${line}\n`);
  }));
}

export function historyPanel(slug, onRunAgain) {
  const host = h("div", { class: "history" });
  let selected = null;
  let filter = "all";
  const load = async () => {
    const all = await get(`/history?limit=100${slug ? `&workflow=${slug}` : ""}`);
    const rows = filter === "all" ? all : all.filter((row) => row.status === filter);
    const filters = segmented([["all", "All"], ["failed", "Failed"], ["skipped", "Skipped"]], filter,
      (next) => { filter = next; selected = null; load().catch(() => {}); }, "Show runs");
    if (all.length && !rows.length) {
      host.replaceChildren(h("div", {}, filters), h("div", { class: "empty" }, h("h2", {}, `No ${filter} runs`)));
      return;
    }
    if (!rows.length) {
      host.replaceChildren(h("div", { class: "empty" }, icon("clock", 36), h("h2", {}, "No runs yet"),
        h("p", {}, "Every run shows up here, including the ones that were skipped.")));
      return;
    }
    selected = selected || rows.find((row) => row.status === "failed")?.id || rows[0].id;
    const nameOf = (id) => S.workflows.find((w) => w.slug === id)?.name || id;
    const table = h("table", { class: "runs" },
      h("thead", {}, h("tr", {}, !slug && h("th", {}, "Workflow"), h("th", {}, "Scheduled"), h("th", {}, "Started"),
        h("th", {}, "Took"), h("th", {}, "Result"), h("th", {}, "Note"))),
      h("tbody", {}, rows.map((row) => h("tr", { class: row.id === selected ? "on" : "", tabindex: "0",
        onclick: () => { selected = row.id; load(); },
        onkeydown: (event) => { if (event.key === "Enter") { selected = row.id; load(); } } },
        !slug && h("td", {}, nameOf(row.workflow)),
        h("td", {}, row.scheduled_at ? when(row.scheduled_at) : "—"),
        h("td", {}, row.started_at ? when(row.started_at) : "Not started"),
        h("td", {}, row.finished_at ? duration(row.finished_at - row.started_at) : "—"),
        h("td", {}, resultTag(row)),
        h("td", { class: "note" }, row.note)))));
    const run = await get(`/history/${selected}`);
    const stamp = when(run.started_at || run.scheduled_at);
    host.replaceChildren(h("div", {}, filters), h("div", { class: "table-wrap" }, table),
      h("div", { class: "output-head" }, h("strong", {}, `Technical details · ${stamp}`), h("span", { class: "grow" }),
        button("Copy", () => copyText(run.output).then(() => toast("Copied")), { class: "small" }),
        onRunAgain ? button("Run again", onRunAgain, { class: "small" }) : null),
      outputView(run.output));
  };
  load().catch((err) => toast(err.message, "error"));
  host.reload = load;
  return host;
}

export function renderLog(top, body, sidebar) {
  top.replaceChildren(h("div", { class: "top-title" }, h("strong", {}, "Run log"), h("span", {}, "Cron Jovi")));
  body.replaceChildren(sidebar("log"), h("section", { class: "page" },
    h("div", { class: "page-head" }, h("div", {}, h("h1", {}, "Run log"), h("p", {}, "Everything Cron Jovi has done, newest first"))),
    historyPanel(null)));
}

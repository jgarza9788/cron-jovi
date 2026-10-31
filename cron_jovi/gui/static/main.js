import { get, post } from "./api.js";
import { h, icon, modal } from "./ui.js";
import { S, onChange, refresh } from "./state.js";
import { refreshTheme } from "./theme.js";
import { newWorkflowDialog, renderLibrary, sidebar } from "./library.js";
import { renderEditor, onStateRefresh } from "./editor.js";
import { renderLog } from "./history.js";
import { renderGallery } from "./gallery.js";
import { renderOverview } from "./overview.js";
import { renderSettings, toolDialog } from "./settings.js";

const top = document.getElementById("top");
const body = document.getElementById("body");
const statusBar = document.getElementById("status");
let repaintLibrary = null;

function renderStatus() {
  const status = S.status;
  if (!status) return;
  const missing = status.tools.filter((tool) => !tool.found);
  const shown = status.tools.filter((tool) => tool.found).slice(0, 4);
  statusBar.replaceChildren(
    h("span", {}, status.session),
    ...shown.map((tool) => h("span", { class: "tool" }, h("span", { class: "ok" }, icon("check", 13)), tool.tool)),
    ...missing.map((tool) => h("button", { type: "button", class: "missing", onclick: () => toolDialog(tool) },
      icon("warn", 13), `${tool.tool} not found`)),
    h("span", { class: "spacer" }),
    ...(status.paused ? [h("span", { class: "bad-state" }, "Paused")] : []),
    ...(status.engine === "not needed" ? [] : [h("span", { class: status.engine === "running" ? "" : "bad-state" },
      status.engine === "running" ? "Engine running" : `Engine ${status.engine}`)]),
    h("span", {}, status.timers_total
      ? `${status.timers_active} of ${status.timers_total} schedules active`
      : "No schedules active"));
}

export async function go(view) {
  S.view = view;
  repaintLibrary = null;
  if (view.name === "library") repaintLibrary = renderLibrary(top, body);
  else if (view.name === "editor") await renderEditor(top, body);
  else if (view.name === "log") renderLog(top, body, sidebar);
  else if (view.name === "gallery") renderGallery(top, body);
  else if (view.name === "overview") repaintLibrary = renderOverview(top, body);
  else if (view.name === "settings") renderSettings(top, body);
}

onChange(() => {
  renderStatus();
  if (S.view.name === "library" || S.view.name === "overview") repaintLibrary?.();
  else if (S.view.name === "editor") onStateRefresh();
});

function welcomeDialog() {
  const seen = () => { post("/welcome").catch(() => {}); };
  modal("Welcome to Cron Jovi", [
    h("p", {}, "Cron Jovi does things for you on your computer. Pick when something should happen, then snap together what it should do."),
    h("ul", { class: "effects" },
      h("li", {}, "Everything saves by itself, and there's an undo button."),
      h("li", {}, "Nothing runs until you switch it on or press Run."),
      h("li", {}, "It all stays on this computer.")),
  ], [["Look around", seen, ""], ["Start with an idea", () => { seen(); setTimeout(newWorkflowDialog); }, "primary"]]);
}

addEventListener("cronjovi-connection", ({ detail: online }) => {
  const banner = document.getElementById("offline");
  if (online) banner?.remove();
  else if (!banner) {
    document.getElementById("app").prepend(h("div", { id: "offline", role: "alert" }, icon("warn"),
      "Cron Jovi lost its connection, so changes can't be saved. Close this window and open it again."));
  }
});

async function boot() {
  await refreshTheme();
  [S.actions, S.templates] = await Promise.all([get("/actions"), get("/templates")]);
  await refresh();
  await go(S.view);
  if (!(await get("/welcome")).seen) welcomeDialog();
  setInterval(() => refreshTheme().catch(() => {}), 3000);
  let tick = 0;
  setInterval(() => {
    tick += 1;
    // Quick while something is running, so cards show when it ends.
    if (!document.hidden && (tick % 5 === 0 || S.workflows.some((w) => w.running))) refresh().catch(() => {});
  }, 2000);
}

boot().catch((err) => {
  body.replaceChildren(h("div", { class: "empty", style: "flex:1" }, icon("warn", 36),
    h("h2", {}, "Cron Jovi couldn't start"), h("p", {}, err.message)));
});

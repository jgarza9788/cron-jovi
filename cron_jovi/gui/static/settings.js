import { del, get, post, put } from "./api.js";
import { button, confirmDialog, copyText, h, icon, modal, toast, toggle } from "./ui.js";
import { S, refresh } from "./state.js";
import { refreshTheme } from "./theme.js";
import { sidebar } from "./library.js";
import { go } from "./main.js";

export function hotkeyDialog() {
  const link = S.status.hotkey_links.find((item) => !item.linked);
  modal("Turn on hotkeys",
    h("p", {}, `Linux desktops only allow hotkeys through the window manager. Cron Jovi will add one `
      + `line to your ${link?.name || "desktop"} settings so your hotkeys load. A backup of that file is made first, `
      + `and removing Cron Jovi takes the line out again.`),
    [["Not now", null, ""], ["Turn on hotkeys", async () => {
      try {
        await post("/hotkeys/link");
        await refresh();
        toast("Hotkeys are on", "success");
      } catch (err) { toast(err.message, "error"); return false; }
      return true;
    }, "primary"]]);
}

export function hotkeyBanner() {
  return h("div", { class: "banner" }, icon("warn"),
    h("p", {}, "You have hotkeys set up, but they aren't switched on yet."),
    button("Turn on", hotkeyDialog, { class: "small" }));
}

export async function setPaused(paused) {
  try {
    await put("/settings", { paused });
    await refresh();
    toast(paused ? "Everything is paused" : "Back on", "success");
  } catch (err) { toast(err.message, "error"); }
}

export function pausedBanner() {
  return h("div", { class: "banner" }, icon("warn"),
    h("p", {}, "Everything is paused. Hotkeys, schedules and events won't run until you resume."),
    button("Resume", () => setPaused(false), { class: "small" }));
}

export function toolDialog(tool) {
  const copy = async () => {
    await copyText(tool.hint);
    toast("Copied. Paste it into a terminal.", "success");
  };
  modal(`${tool.tool} isn't installed`,
    [h("p", {}, `This is needed by: ${tool.actions}. Workflows using it will fail until it's installed. `
      + "To install it, run this in a terminal:"),
    h("code", { class: "codebox" }, tool.hint)],
    [["Close", null, ""], ["Copy command", copy, "primary"]]);
}

export function importWorkflow() {
  const picker = h("input", { type: "file", accept: ".yaml,.yml", style: "display:none",
    onchange: async () => {
      const file = picker.files[0];
      picker.remove();
      if (!file) return;
      const text = await file.text();
      try {
        const review = await post("/import/review", { yaml: text });
        reviewDialog(text, review);
      } catch (err) { toast(err.message, "error"); }
    } });
  document.body.append(picker);
  picker.click();
}

export function reviewDialog(text, review) {
  const body = [
    review.description ? h("p", { class: "description-text" }, review.description) : null,
    h("p", {}, `“${review.name}” has ${review.actions} action${review.actions === 1 ? "" : "s"} and is triggered by: ${review.trigger}.`),
    h("p", {}, "It's added switched off, so nothing runs until you turn it on."),
  ];
  if (review.commands.length) {
    body.push(h("div", { class: "banner error" }, icon("warn"),
      h("p", {}, "This workflow runs commands on your computer. Only add it if you trust where it came from.")));
    body.push(h("pre", { class: "codebox" }, review.commands.join("\n")));
  }
  if (review.effects.length) {
    body.push(h("p", {}, "It also:"), h("ul", { class: "effects" }, review.effects.map((text) => h("li", {}, text))));
  }
  modal("Check this workflow first", body, [["Cancel", null, ""], ["Add it", async () => {
    try {
      const { slug } = await post("/import", { yaml: text });
      await refresh();
      go({ name: "editor", slug });
    } catch (err) { toast(err.message, "error"); return false; }
    return true;
  }, "primary"]], { wide: true });
}

export function renderSettings(top, body) {
  top.replaceChildren(h("div", { class: "top-title" }, h("strong", {}, "Settings"), h("span", {}, "Cron Jovi")));
  const saveAccent = async (accent) => {
    await put("/settings", { accent });
    await refreshTheme();
  };
  const appearance = h("div", { class: "rows" });
  get("/settings").then((current) => appearance.replaceChildren(h("div", { class: "row" },
    h("div", { class: "meta" }, h("strong", {}, "Accent color"),
      h("small", {}, current.accent ? "Your own color" : "Following your theme")),
    h("input", { type: "color", class: "swatch-input", "aria-label": "Accent color",
      value: current.accent || getComputedStyle(document.documentElement).getPropertyValue("--accent").trim(),
      onchange: (event) => saveAccent(event.target.value).catch((e) => toast(e.message, "error")) }),
    current.accent ? button("Reset", () => saveAccent("").then(() => renderSettings(top, body)), { class: "small" }) : null))).catch(() => {});
  const tools = S.status?.tools || [];
  const links = S.status?.hotkey_links || [];
  const page = h("section", { class: "page" },
    h("div", { class: "page-head" }, h("h1", {}, "Settings")),
    h("h2", { class: "section" }, "Automation"),
    h("div", { class: "rows" }, h("div", { class: "row" },
      h("div", { class: "meta" }, h("strong", {}, "Pause everything"),
        h("small", {}, "Stops every hotkey, schedule and event. You can still press Run. Nothing catches up when you resume.")),
      toggle(Boolean(S.status?.paused), (value) => setPaused(value).then(() => renderSettings(top, body)), "Pause everything"))),
    h("h2", { class: "section" }, "Appearance"),
    appearance,
    h("h2", { class: "section" }, "Hotkeys"),
    h("div", { class: "rows" }, links.length ? links.map((link) => h("div", { class: "row" },
      h("div", { class: "meta" }, h("strong", {}, link.name),
        h("small", {}, link.linked ? "Hotkeys are on" : "Hotkeys are off")),
      link.linked ? icon("check") : button("Turn on", hotkeyDialog, { class: "small" })))
      : h("div", { class: "row" }, h("div", { class: "meta" },
        h("strong", {}, "No supported window manager found"),
        h("small", {}, "Hyprland and niri are supported. Other desktops can bind a key to “cronjovi run <name>”.")))),
    h("h2", { class: "section" }, "Linux tools"),
    h("div", { class: "rows" }, tools.map((tool) => h("div", { class: "row" },
      h("div", { class: "meta" }, h("strong", {}, tool.tool), h("small", {}, `Used by ${tool.actions}`)),
      tool.found ? h("span", { class: "ok-mark" }, icon("check"))
        : button("How to install", () => toolDialog(tool), { class: "small" })))),
    h("h2", { class: "section" }, "Privacy"),
    h("div", { class: "rows" }, h("div", { class: "row" },
      h("div", { class: "meta" }, h("strong", {}, "Clear run history"),
        h("small", {}, "Logs can contain what your commands printed. Running workflows aren't affected.")),
      button("Clear…", () => confirmDialog("Clear all run history?", "This can't be undone.", "Clear", async () => {
        await del("/history");
        await refresh();
        toast("History cleared", "success");
      }), { class: "small" }))),
    h("h2", { class: "section" }, "Workflows"),
    h("div", { class: "rows" }, h("div", { class: "row" },
      h("div", { class: "meta" }, h("strong", {}, "Import a workflow"),
        h("small", {}, "Add a .yaml file someone shared with you. You'll review it first.")),
      button("Import…", importWorkflow, { class: "small", icon: "upload" }))));
  body.replaceChildren(sidebar("settings"), page);
}

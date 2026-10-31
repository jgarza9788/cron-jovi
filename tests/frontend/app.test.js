// Boots the real app in a simulated browser, against a small stand-in for the server.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { before, beforeEach, test } from "node:test";
import { JSDOM } from "jsdom";

const STATIC = new URL("../../cron_jovi/gui/static/", import.meta.url);
const field = (name, kind, required = true) => ({ name, kind, label: name, required, choices: [] });
const ACTIONS = [
  { name: "notify", title: "Show Notification", blurb: "", category: "Scripting", icon: "bell", color: "green", tools: [], fields: [field("text", "text")] },
  { name: "wait", title: "Wait", blurb: "", category: "Scripting", icon: "clock", color: "gray", tools: [], fields: [field("duration", "duration")] },
];
const STATUS = {
  version: "0.0.1", codename: "Blaze of Glory", stage: "Beta", session: "Hyprland", tools: [], timers_active: 0,
  timers_total: 0, hotkey_links: [], engine: "not needed", paused: false, has_battery: false,
};
const THEME = { source: "default", stamp: "0", colors: {
  background: "#171a21", dark_background: "#12141a", darker_background: "#0d0f14", lighter_background: "#20242d",
  foreground: "#e6e8ec", dark_foreground: "#9aa1ad", light_foreground: "#f3f4f6", bright_foreground: "#ffffff",
  muted: "#6b7280", accent: "#f5a623", selection: "#2a2f3a", red: "#f87171", yellow: "#f5c451", orange: "#fdba74",
  green: "#a7e0a0", cyan: "#7fd8cc", blue: "#9cc3ff", magenta: "#f5a9c8", purple: "#c8b4fb", gray: "#c4cbd8" } };

let saved;
let stamp = "s0";
let workflow;
let go;
let S;

function summary() {
  return { slug: "demo", name: workflow.name, enabled: false, steps: workflow.steps.length, last_run: null, stamp };
}

async function fakeFetch(url, options = {}) {
  const path = url.replace("/api", "");
  const method = options.method || "GET";
  let body = {};
  if (method === "PUT" && path === "/workflows/demo") {
    workflow = JSON.parse(options.body);
    saved.push(workflow);
    stamp = `s${saved.length}`;
    body = { messages: [], stamp };
  } else if (path === "/state") body = { workflows: [summary()], errors: [], status: STATUS };
  else if (path === "/theme") body = THEME;
  else if (path === "/actions") body = ACTIONS;
  else if (path === "/templates") body = [];
  else if (path === "/welcome") body = { seen: true };
  else if (path === "/settings") body = { paused: false, accent: "" };
  else if (path === "/workflows/demo") body = { data: workflow, yaml: "", stamp, summary: summary() };
  else if (path.endsWith("/progress")) body = { running: false, steps: {} };
  else if (path.startsWith("/history")) body = [];
  return { ok: true, status: 200, json: async () => structuredClone(body) };
}

before(async () => {
  const page = readFileSync(new URL("index.html", STATIC), "utf8").replace(/<script.*<\/script>/, "");
  const { window } = new JSDOM(page, { url: "http://127.0.0.1/#token=t", pretendToBeVisual: true });
  for (const name of ["window", "document", "location", "history", "sessionStorage", "localStorage", "getComputedStyle",
    "requestAnimationFrame", "cancelAnimationFrame", "CustomEvent", "Event", "HTMLElement", "Node", "matchMedia"]) {
    if (window[name]) globalThis[name] = window[name];
  }
  globalThis.matchMedia ??= () => ({ matches: false, addEventListener() {} });
  globalThis.addEventListener = window.addEventListener.bind(window);
  globalThis.dispatchEvent = window.dispatchEvent.bind(window);
  globalThis.fetch = fakeFetch;
  workflow = { name: "Demo", description: "", steps: [] };
  saved = [];
  ({ go } = await import(new URL("main.js", STATIC)));
  ({ S } = await import(new URL("state.js", STATIC)));
  await tick(50);
});

const tick = (ms = 0) => new Promise((done) => { setTimeout(done, ms); });
const texts = () => [...document.querySelectorAll(".block")].map((el) => el.textContent);
const names = (data = workflow) => data.steps.map((step) => step.text ?? step.duration);
const button = (label) => document.querySelector(`[aria-label="${label}"]`);

/** Drag events carry a dataTransfer, which the simulated browser doesn't provide. */
function fire(element, type, clientY = 0) {
  const event = new window.Event(type, { bubbles: true, cancelable: true });
  Object.assign(event, { clientY, dataTransfer: { setData() {}, setDragImage() {}, effectAllowed: "" } });
  element.dispatchEvent(event);
}

function dragStep(from, onto, side) {
  const blocks = document.querySelectorAll(".block");
  fire(blocks[from].querySelector(".grip"), "dragstart");
  const target = blocks[onto];
  target.getBoundingClientRect = () => ({ top: 0, height: 100 });
  fire(target, "dragover", side === "after" ? 90 : 10);
  fire(target, "drop", side === "after" ? 90 : 10);
  fire(blocks[from].querySelector(".grip"), "dragend");
}

async function open(steps) {
  workflow = { name: "Demo", description: "", steps };
  saved = [];
  stamp = "s0";
  S.view = { name: "library", filter: "all" };
  await go({ name: "library", filter: "all" });
  await go({ name: "editor", slug: "demo" });
  await tick(20);
}

const three = () => [{ action: "notify", text: "one" }, { action: "notify", text: "two" }, { action: "notify", text: "three" }];

beforeEach(() => open(three()));

test("the editor shows steps in order", () => {
  const shown = texts();
  assert.equal(shown.length, 3);
  assert.match(shown[0], /one/);
  assert.match(shown[2], /three/);
});

test("dragging a step down moves it after the target", async () => {
  dragStep(0, 2, "after");
  await tick(600);
  assert.deepEqual(names(), ["two", "three", "one"]);
});

test("dragging a step up moves it before the target", async () => {
  dragStep(2, 0, "before");
  await tick(600);
  assert.deepEqual(names(), ["three", "one", "two"]);
});

test("the arrow keys move a focused step", async () => {
  const grip = document.querySelector(".block .grip");
  grip.dispatchEvent(new window.KeyboardEvent("keydown", { key: "ArrowDown", bubbles: true, cancelable: true }));
  await tick(600);
  assert.deepEqual(names(), ["two", "one", "three"]);
});

test("a step can be dragged into an empty If branch", async () => {
  await open([{ action: "notify", text: "one" }, { if: { equals: ["a", "a"] }, then: [], else: [] }]);
  fire(document.querySelector(".block .grip"), "dragstart");
  fire(document.querySelector(".drop-zone"), "dragover");
  fire(document.querySelector(".drop-zone"), "drop");
  await tick(600);
  assert.equal(workflow.steps.length, 1);
  assert.deepEqual(workflow.steps[0].then, [{ action: "notify", text: "one" }]);
});

test("a block can't be dragged into itself", async () => {
  await open([{ if: { equals: ["a", "a"] }, then: [], else: [] }]);
  const before = JSON.stringify(workflow);
  fire(document.querySelector(".block .grip"), "dragstart");
  fire(document.querySelector(".drop-zone"), "drop");
  await tick(600);
  assert.equal(JSON.stringify(workflow), before);
});

test("undo and redo walk back and forward through changes", async () => {
  dragStep(0, 2, "after");
  await tick(600);
  assert.deepEqual(names(), ["two", "three", "one"]);
  assert.equal(button("Redo").disabled, true);

  button("Undo").click();
  await tick(300);
  assert.deepEqual(names(), ["one", "two", "three"]);
  assert.match(texts()[0], /one/);

  button("Redo").click();
  await tick(300);
  assert.deepEqual(names(), ["two", "three", "one"]);
});

test("undo right after a change, before it saves, undoes that change", async () => {
  dragStep(0, 2, "after");
  await tick(600);
  dragStep(0, 2, "after");
  button("Undo").click();
  await tick(300);
  assert.deepEqual(names(), ["two", "three", "one"]);
  button("Redo").click();
  await tick(300);
  assert.deepEqual(names(), ["three", "one", "two"]);
});

test("a new change clears the redo list", async () => {
  dragStep(0, 2, "after");
  await tick(600);
  button("Undo").click();
  await tick(300);
  dragStep(2, 0, "before");
  await tick(600);
  assert.equal(button("Redo").disabled, true);
});

test("a window step reads as a sentence", async () => {
  ACTIONS.push({ name: "window", title: "Control a Window", blurb: "", category: "Windows", icon: "grid", color: "purple", tools: [], fields: [] });
  await open([{ action: "window", op: "move", app: "firefox", workspace: 3 }]);
  assert.match(texts()[0], /Move.*firefox.*to workspace.*3/s);
});

test("Settings ends with the version and release name", async () => {
  await go({ name: "settings" });
  await tick(20);
  const headings = [...document.querySelectorAll("h2.section")].map((el) => el.textContent);
  assert.equal(headings.at(-1), "About");
  const about = document.querySelector(".rows.about").textContent;
  assert.match(about, /Cron Jovi v0\.0\.1 Beta/);
  assert.match(about, /Blaze of Glory/);
  assert.match(about, /MIT/);
});

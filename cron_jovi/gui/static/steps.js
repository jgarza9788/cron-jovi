import { button, chip, h, icon, iconButton, menu, segmented } from "./ui.js";
import { S } from "./state.js";

const LABELS = {
  run: "Command", shell: "Shell", timeout: "Stop after", text: "Text", title: "Title",
  urgency: "Importance", target: "App, file or web address", keys: "Keys to press", url: "Web address",
  method: "Method", headers: "Headers (JSON)", json: "JSON body", body: "Body", src: "From", dest: "To",
  overwrite: "Replace if it already exists", command: "Do what", players: "Players", duration: "How long",
  name: "Variable name", value: "Value", state: "Turn", percent: "Percent", op: "What to do",
  do: "What to do", area: "What to capture", send_to: "Send it to", folder: "Save in folder",
  sum: "Sum", split_at: "Split at", question: "Question", kind: "Answer by", choices: "Choices", workflow: "Workflow",
  change: "Change", find: "Find", replace_with: "Replace with", number: "Workspace number",
};
const CHOICES = { type: "Typing", "yes-no": "Yes or no", choose: "Picking from a list", "play-pause": "Play or pause", get: "Read it", set: "Replace it", on: "On", off: "Off" };
const label = (name) => LABELS[name] || name;
const choiceLabel = (value) => CHOICES[value] || String(value)[0].toUpperCase() + String(value).slice(1);

export const CONTROL_BLOCKS = [
  { name: "if", title: "If / Otherwise", blurb: "Branch on a condition", category: "Scripting", icon: "branch", color: "orange" },
  { name: "repeat", title: "Repeat", blurb: "Loop over a set of actions", category: "Scripting", icon: "repeat", color: "orange" },
];

let drag = null;

export const actionDef = (name) => S.actions.find((a) => a.name === name);

function isBlank(value) {
  return value === undefined || value === null || String(value).trim() === "";
}

function needsFilling(step) {
  if (step.skip) return false;
  if ("if" in step) {
    return Object.entries(step.if).some(([kind, value]) => {
      if (kind === "equals") return isBlank(value[0]) && isBlank(value[1]);
      if (kind === "contains") return isBlank(value[0]) || isBlank(value[1]);
      return ["file_exists", "command", "app_running"].includes(kind) && isBlank(value);
    });
  }
  if ("repeat" in step) return Array.isArray(step.repeat) ? !step.repeat.length : isBlank(step.repeat);
  if (step.action === "math") return isBlank(step.sum);
  const def = actionDef(step.action);
  return (def?.fields || []).some((f) => f.required && isBlank(step[f.name]));
}

/** How many steps can't work yet, because something required is empty. */
export function unfinishedSteps(steps) {
  return (steps || []).reduce((total, step) => total + (needsFilling(step) ? 1 : 0)
    + unfinishedSteps(step.then) + unfinishedSteps(step.else) + unfinishedSteps(step.steps), 0);
}

export function newStep(name) {
  if (name === "if") return { if: { time_of_day: { after: "18:00" } }, then: [], else: [] };
  if (name === "repeat") return { repeat: 3, steps: [] };
  const step = { action: name };
  for (const field of actionDef(name).fields) {
    if (!field.required) continue;
    if (field.kind === "choice") step[field.name] = field.choices[0];
    else if (field.kind === "number") step[field.name] = 50;
    else if (field.kind === "duration") step[field.name] = "5s";
    else step[field.name] = "";
  }
  return step;
}

function sentence(step) {
  const v = (value, fallback = "…") => ({ chip: value === "" || value === undefined ? fallback : String(value) });
  switch (step.action) {
    case "dnd": return ["Turn Do Not Disturb", v(choiceLabel(step.state))];
    case "media": return [choiceLabel(step.command), "playback on", v(step.players && step.players !== "all" ? step.players : "All players")];
    case "brightness": return ["Set screen brightness to", v(`${step.percent}%`)];
    case "notify": return ["Show notification", v(step.text, "message")];
    case "open": return ["Open", v(step.target, "something")];
    case "wait": return ["Wait", v(step.duration)];
    case "clipboard": return step.op === "set" ? ["Copy to clipboard", v(step.text, "text")] : ["Get what's on the clipboard"];
    case "type": return ["Type", v(step.text || (step.keys || []).join(", "), "text")];
    case "http": return [step.method || "GET", v(step.url, "address")];
    case "file": return [choiceLabel(step.op), v(step.src, "a file"), "to", v(step.dest, "somewhere")];
    case "set": return ["Remember", v(step.name, "name"), "as", v(step.value)];
    case "workspace": return ["Switch to workspace", v(step.number)];
    case "volume": return step.do && step.do !== "set" ? [choiceLabel(step.do), "the sound"] : ["Set volume to", v(`${step.percent ?? 50}%`)];
    case "screenshot": return ["Screenshot of", v(step.area === "selection" ? "a selection" : "the screen")];
    case "lock": return ["Lock the screen"];
    case "math": return ["Calculate", v(step.sum)];
    case "ask": return ["Ask", v(step.question, "a question")];
    case "run": return ["Run workflow", v(step.workflow, "…")];
    case "text": return ["Change text:", v(choiceLabel(step.change || "trim"))];
    default: return [actionDef(step.action)?.title || step.action];
  }
}

function variableNames(ctx) {
  const found = new Set(["result", "date", "time", "weekday", "workflow"]);
  const walk = (steps) => (steps || []).forEach((step) => {
    if (step.save_as) found.add(step.save_as);
    if (step.action === "set" && step.name) found.add(step.name);
    walk(step.then); walk(step.else); walk(step.steps);
  });
  walk(ctx.root());
  const trigger = ctx.trigger?.() || {};
  if (trigger.file) ["file.name", "file.path"].forEach((name) => found.add(name));
  if (trigger.device) found.add("device.name");
  if (trigger.battery) found.add("battery.percent");
  if (trigger.webhook) found.add("webhook.body");
  if (JSON.stringify(ctx.root()).includes('"repeat"')) ["item", "index"].forEach((name) => found.add(name));
  return [...found];
}

function variableButton(input, ctx) {
  return iconButton("tag", "Insert a saved value", (event) => {
    menu(event.currentTarget, variableNames(ctx).map((name) => ({
      label: name,
      run: () => {
        const at = input.selectionStart ?? input.value.length;
        input.value = `${input.value.slice(0, at)}{{ ${name} }}${input.value.slice(at)}`;
        input.dispatchEvent(new Event("input"));
        input.focus();
      },
    })));
  }, "tag-btn");
}

function withVariables(input, ctx) {
  return h("div", { class: "with-action" }, input, variableButton(input, ctx));
}

function durationField(step, field, ctx) {
  const match = /^([\d.]+)\s*(ms|s|m|h)?$/.exec(String(step[field.name] ?? ""));
  const write = () => {
    if (!amount.value) delete step[field.name];
    else step[field.name] = `${amount.value}${unit.value}`;
    ctx.changed();
  };
  const amount = h("input", { class: "input", type: "number", min: "0", step: "any", value: match?.[1] ?? "",
    "aria-label": label(field.name), oninput: write });
  const unit = h("select", { class: "select", "aria-label": "Unit", onchange: write },
    [["ms", "milliseconds"], ["s", "seconds"], ["m", "minutes"], ["h", "hours"]].map(([id, text]) =>
      h("option", { value: id, selected: (match?.[2] || "s") === id }, text)));
  return h("div", { class: "pair" }, amount, unit);
}

function fieldEditor(step, field, ctx, rerender) {
  const value = step[field.name] ?? field.default ?? "";
  const set = (next) => {
    if (next === "" || next === undefined || next === null) delete step[field.name];
    else step[field.name] = next;
    ctx.changed();
  };
  if (field.kind === "bool") {
    return h("label", { class: "check" },
      h("input", { type: "checkbox", checked: Boolean(step[field.name] ?? field.default),
        onchange: (event) => set(event.target.checked) }), label(field.name));
  }
  if (field.kind === "choice") {
    return h("div", { class: "field" }, h("span", {}, label(field.name)),
      field.choices.length <= 4
        ? segmented(field.choices.map((c) => [c, choiceLabel(c)]), value,
          (next) => { step[field.name] = next; ctx.changed(); rerender(); }, label(field.name))
        : h("select", { class: "select", "aria-label": label(field.name),
          onchange: (event) => { step[field.name] = event.target.value; ctx.changed(); rerender(); } },
        field.choices.map((c) => h("option", { value: c, selected: c === value }, choiceLabel(c)))));
  }
  let input;
  if (field.kind === "duration") {
    input = durationField(step, field, ctx);
  } else if (field.kind === "number") {
    // Plain text so it can also hold {{ a variable }}; digits are saved as a number.
    input = withVariables(h("input", { class: "input", inputmode: "numeric", value, "aria-label": label(field.name),
      oninput: (event) => {
        const text = event.target.value.trim();
        set(text !== "" && !Number.isNaN(Number(text)) ? Number(text) : text);
      } }), ctx);
  } else if (field.kind === "json") {
    const write = (event) => {
      try { set(event.target.value.trim() ? JSON.parse(event.target.value) : ""); event.target.classList.remove("bad"); }
      catch { event.target.classList.add("bad"); }
    };
    input = h("textarea", { class: "textarea mono", "aria-label": label(field.name), oninput: write },
      value ? JSON.stringify(value, null, 2) : "");
  } else if (field.kind === "list") {
    input = h("input", { class: "input", value: (step[field.name] || []).join(", "),
      placeholder: step.action === "ask" ? "Yes, No, Later" : "Return, Tab",
      "aria-label": label(field.name),
      oninput: (event) => set(event.target.value.split(",").map((k) => k.trim()).filter(Boolean)) });
  } else if (step.action === "run" && field.name === "workflow") {
    const others = S.workflows.filter((w) => w.slug !== ctx.slug());
    input = h("select", { class: "select", "aria-label": "Workflow", onchange: (event) => set(event.target.value) },
      h("option", { value: "" }, "Pick a workflow…"),
      others.map((w) => h("option", { value: w.slug, selected: w.slug === value }, w.name)));
  } else if (field.name === "run") {
    input = withVariables(h("textarea", { class: "textarea mono code", value, spellcheck: "false", "aria-label": "Command",
      oninput: (event) => set(event.target.value) }), ctx);
  } else {
    input = h("input", { class: "input", value, "aria-label": label(field.name),
      oninput: (event) => set(event.target.value) });
    if (!(step.action === "set" && field.name === "name")) input = withVariables(input, ctx);
  }
  return h("div", { class: "field" }, h("span", {}, label(field.name)), input);
}

function visibleFields(step, def) {
  return def.fields.filter((f) => {
    if (step.action === "clipboard" && f.name === "text") return step.op === "set";
    if (step.action === "volume" && f.name === "percent") return (step.do || "set") === "set";
    if (step.action === "screenshot" && f.name === "folder") return step.send_to === "file";
    if (step.action === "text" && ["find", "replace_with"].includes(f.name)) return step.change === "replace";
    if (step.action === "text" && f.name === "split_at") return step.change === "split";
    if (step.action === "ask" && f.name === "choices") return step.kind === "choose";
    return true;
  });
}

const ALWAYS_SHOWN = ["clipboard", "volume", "screenshot", "text", "ask"];

function actionDetails(step, def, ctx, rerender) {
  const fields = visibleFields(step, def);
  const main = fields.filter((f) => f.required || ALWAYS_SHOWN.includes(step.action));
  const extra = fields.filter((f) => !main.includes(f));
  return h("div", { class: "details" },
    main.map((f) => fieldEditor(step, f, ctx, rerender)),
    h("details", { class: "more" }, h("summary", {}, "More options"),
      h("div", { class: "details" },
        extra.map((f) => fieldEditor(step, f, ctx, rerender)),
        h("div", { class: "field" }, h("span", {}, "Remember the result as"),
          h("input", { class: "input", value: step.save_as || "", placeholder: "Optional name",
            "aria-label": "Remember the result as",
            oninput: (event) => {
              if (event.target.value) step.save_as = event.target.value.replace(/\W/g, "_");
              else delete step.save_as;
              ctx.changed();
            } })))),
    h("label", { class: "check" },
      h("input", { type: "checkbox", checked: Boolean(step.stop_on_error),
        onchange: (event) => {
          if (event.target.checked) step.stop_on_error = true;
          else delete step.stop_on_error;
          ctx.changed();
        } }), "Stop the workflow if this step fails"),
    h("div", {}, button("Test this step", () => ctx.testStep(step), { class: "small", icon: "play" })));
}

const CONDITION_KINDS = [["time_of_day", "Time of day"], ["weekday", "Day of the week"], ["equals", "Two values match"],
  ["contains", "Text contains"], ["file_exists", "A file exists"], ["app_running", "An app is running"],
  ["on_battery", "Running on battery"], ["command", "A command succeeds"]];
const CONDITION_DEFAULTS = {
  time_of_day: () => ({ after: "18:00" }), weekday: () => ["Mon", "Tue", "Wed", "Thu", "Fri"], equals: () => ["", ""],
  contains: () => ["", ""], file_exists: () => "", app_running: () => "", on_battery: () => true, command: () => "",
};
const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

function textPill(value, aria, write, placeholder, ctx) {
  const input = h("input", { class: "pill-input", value, placeholder, "aria-label": aria,
    oninput: (event) => { write(event.target.value); ctx.changed(); } });
  return h("span", { class: "pill-with-tag" }, input, variableButton(input, ctx));
}

function timeControls(value, ctx, rerender) {
  const mode = "after" in value && "before" in value ? "between" : "before" in value ? "before" : "after";
  const clock = (key, aria) => h("input", { class: "pill-input", type: "time", value: value[key], "aria-label": aria,
    oninput: (event) => { if (event.target.value) { value[key] = event.target.value; ctx.changed(); } } });
  const pick = h("select", { class: "pill-select", "aria-label": "Before or after",
    onchange: (event) => {
      const keep = value.after || value.before || "18:00";
      delete value.after;
      delete value.before;
      if (event.target.value === "between") Object.assign(value, { after: keep, before: "23:00" });
      else value[event.target.value] = keep;
      ctx.changed();
      rerender();
    } }, [["after", "is after"], ["before", "is before"], ["between", "is between"]].map(([id, text]) =>
    h("option", { value: id, selected: id === mode }, text)));
  if (mode === "between") return [pick, clock("after", "From"), "and", clock("before", "Until")];
  return [pick, clock(mode, "Time")];
}

function dayControls(spec, set, ctx) {
  const days = typeof spec === "string" ? [spec] : spec;
  return h("span", { class: "days", role: "group", "aria-label": "Days" }, DAYS.map((day) =>
    h("button", { type: "button", class: `day ${days.includes(day) ? "on" : ""}`, "aria-pressed": String(days.includes(day)),
      onclick: (event) => {
        const on = days.includes(day);
        const next = on ? days.filter((d) => d !== day) : DAYS.filter((d) => days.includes(d) || d === day);
        if (!next.length) return;
        days.splice(0, days.length, ...next);
        set(days);
        event.currentTarget.classList.toggle("on", !on);
        event.currentTarget.setAttribute("aria-pressed", String(!on));
        ctx.changed();
      } }, day[0] + day[1])));
}

function conditionValue(kind, value, set, ctx, rerender) {
  if (kind === "time_of_day") return timeControls(value, ctx, rerender);
  if (kind === "weekday") return [dayControls(value, set, ctx)];
  if (kind === "equals") {
    return [textPill(value[0], "First value", (v) => { value[0] = v; }, "{{ result }}", ctx), "is",
      textPill(value[1], "Second value", (v) => { value[1] = v; }, "this", ctx)];
  }
  if (kind === "contains") {
    return [textPill(value[0], "Text", (v) => { value[0] = v; }, "{{ result }}", ctx), "has",
      textPill(value[1], "Piece of text", (v) => { value[1] = v; }, "this", ctx)];
  }
  if (kind === "on_battery") {
    return [h("select", { class: "pill-select", "aria-label": "Battery or plugged in",
      onchange: (event) => { set(event.target.value === "yes"); ctx.changed(); } },
    h("option", { value: "yes", selected: value !== false }, "yes"),
    h("option", { value: "no", selected: value === false }, "no, plugged in"))];
  }
  const hint = { command: "ping -c1 example.com", file_exists: "~/some/file", app_running: "firefox" }[kind];
  return [textPill(value, "Value", set, hint, ctx)];
}

function conditionRow(step, key, ctx, rerender) {
  const negated = key === "not" && Object.keys(step.if.not).length === 1;
  const holder = negated ? step.if.not : step.if;
  const kind = negated ? Object.keys(step.if.not)[0] : key;
  const replaceKey = (target, from, to, value) => {
    const next = {};
    for (const [name, old] of Object.entries(target)) {
      if (name === from) next[to] = value; else next[name] = old;
    }
    return next;
  };
  const removeRow = iconButton("x", "Remove this condition", () => { delete step.if[key]; ctx.structure(); });
  if (kind === "not") {
    return h("div", { class: "condition" }, h("span", { class: "pill" }, "Advanced “not” (edit it in YAML)"), removeRow);
  }
  const used = Object.keys(step.if).filter((name) => name !== key);
  const pick = h("select", { class: "pill-select", "aria-label": "Condition",
    onchange: (event) => {
      const next = event.target.value;
      if (negated) step.if.not = { [next]: CONDITION_DEFAULTS[next]() };
      else step.if = replaceKey(step.if, key, next, CONDITION_DEFAULTS[next]());
      ctx.structure();
    } }, CONDITION_KINDS.filter(([id]) => id === kind || !used.includes(id)).map(([id, text]) =>
    h("option", { value: id, selected: id === kind }, text)));
  const flip = h("select", { class: "pill-select", "aria-label": "Is or is not",
    disabled: !negated && "not" in step.if, onchange: (event) => {
      const value = holder[kind];
      if (event.target.value === "not") step.if = replaceKey(step.if, key, "not", { [kind]: value });
      else step.if = replaceKey(step.if, "not", kind, value);
      ctx.structure();
    } }, h("option", { value: "is", selected: !negated }, "Only if"), h("option", { value: "not", selected: negated }, "Unless"));
  return h("div", { class: "condition" }, flip, pick,
    conditionValue(kind, holder[kind], (value) => { holder[kind] = value; }, ctx, rerender),
    Object.keys(step.if).length > 1 ? removeRow : null);
}

function conditionRows(step, ctx, rerender) {
  const keys = Object.keys(step.if);
  const free = CONDITION_KINDS.find(([id]) => !keys.includes(id));
  return h("div", { class: "conditions" },
    keys.length > 1 ? h("p", { class: "hint" }, "All of these must be true") : null,
    keys.map((key) => conditionRow(step, key, ctx, rerender)),
    free ? h("div", {}, button("Add a condition", () => {
      step.if[free[0]] = CONDITION_DEFAULTS[free[0]]();
      ctx.structure();
    }, { class: "small ghost", icon: "plus" })) : null);
}

const SEPARATORS = [[",", "a comma"], [" ", "a space"], ["\n", "a new line"], ["custom", "something else"]];

function repeatMode(step) {
  if (Array.isArray(step.repeat)) return "list";
  if ("split" in step) return "split";
  const single = /^\s*\{\{\s*[\w.]+\s*\}\}\s*$/;
  return typeof step.repeat === "number" || single.test(String(step.repeat)) || /^\d+$/.test(String(step.repeat)) ? "times" : "split";
}

function repeatControls(step, ctx) {
  const mode = repeatMode(step);
  const pick = h("select", { class: "pill-select", "aria-label": "Repeat how",
    onchange: (event) => {
      delete step.split;
      if (event.target.value === "times") step.repeat = 3;
      if (event.target.value === "list") step.repeat = ["first", "second"];
      if (event.target.value === "split") Object.assign(step, { repeat: "one,two,three", split: "," });
      ctx.structure();
    } }, [["times", "times"], ["list", "for each item"], ["split", "for each part of"]].map(([id, text]) =>
    h("option", { value: id, selected: id === mode }, text)));
  if (mode === "list") {
    return { head: [pick], below: h("div", { class: "details" }, h("div", { class: "field" }, h("span", {}, "One item per line"),
      h("textarea", { class: "textarea", "aria-label": "Items", value: step.repeat.join("\n"),
        oninput: (event) => { step.repeat = event.target.value.split("\n").filter((line) => line.trim()); ctx.changed(); } }),
      h("p", { class: "hint" }, "Steps inside can use the current one: pick item from the tag button."))) };
  }
  if (mode === "times") {
    const count = h("input", { class: "pill-input count", inputmode: "numeric", value: step.repeat, "aria-label": "How many times",
      placeholder: "3", oninput: (event) => {
        const text = event.target.value.trim();
        step.repeat = /^\d+$/.test(text) ? Number(text) : text;
        ctx.changed();
      } });
    return { head: [h("span", { class: "pill-with-tag" }, count, variableButton(count, ctx)), pick] };
  }
  const source = h("input", { class: "pill-input wide", value: step.repeat, "aria-label": "Text to split", placeholder: "one,two,three",
    oninput: (event) => { step.repeat = event.target.value; ctx.changed(); } });
  const current = step.split ?? "\n";
  const known = SEPARATORS.some(([id]) => id === current);
  const custom = h("input", { class: "pill-input num", value: known ? "" : current, "aria-label": "Split at this text", placeholder: "|",
    oninput: (event) => { step.split = event.target.value; ctx.changed(); } });
  const at = h("select", { class: "pill-select", "aria-label": "Split at", onchange: (event) => {
    step.split = event.target.value === "custom" ? "|" : event.target.value;
    ctx.structure();
  } }, SEPARATORS.map(([id, text]) => h("option", { value: id, selected: known ? id === current : id === "custom" }, text)));
  return { head: [pick], below: h("div", { class: "details" }, h("div", { class: "condition" },
    h("span", { class: "pill-with-tag" }, source, variableButton(source, ctx)),
    "split at", at, known ? null : custom),
  h("p", { class: "hint" }, "Steps inside can use the current part: pick item from the tag button.")) };
}

function contains(step, list) {
  if (!step) return false;
  return [step.then, step.else, step.steps].some((inner) =>
    inner && (inner === list || inner.some((child) => contains(child, list))));
}

function dropInsert(list, index, ctx) {
  if (drag.action) {
    const step = newStep(drag.action);
    ctx.expanded.add(step);
    list.splice(index, 0, step);
  } else {
    if (drag.step === list[index] || contains(drag.step, list)) return;
    const from = drag.list.indexOf(drag.step);
    drag.list.splice(from, 1);
    if (drag.list === list && from < index) index -= 1;
    list.splice(index, 0, drag.step);
  }
  ctx.structure();
}

function clearMarks() {
  document.querySelectorAll(".drop-before,.drop-after,.drop-into").forEach((el) =>
    el.classList.remove("drop-before", "drop-after", "drop-into"));
}

/** A small pill for the cursor to carry, whatever the size of the block. */
function setDragPill(event, title, color, glyph) {
  const pill = h("div", { class: "drag-pill" }, chip(color, glyph, 14), title);
  document.body.append(pill); // the browser snapshots it now, so it can go on the next tick
  event.dataTransfer.setDragImage(pill, 18, 17);
  setTimeout(() => pill.remove());
}

function beginDragging(element) {
  document.body.classList.add("dragging-step");
  // After the snapshot, or some engines would photograph the faded version.
  requestAnimationFrame(() => element?.classList.add("being-dragged"));
}

function endDragging() {
  drag = null;
  clearMarks();
  document.body.classList.remove("dragging-step");
  document.querySelectorAll(".being-dragged").forEach((el) => el.classList.remove("being-dragged"));
}

function stepLabel(step) {
  if ("if" in step) return ["If / Otherwise", "orange", "branch"];
  if ("repeat" in step) return ["Repeat", "orange", "repeat"];
  const def = actionDef(step.action);
  return [def?.title || step.action, def?.color || "gray", def?.icon || "zap"];
}

export function beginActionDrag(event, item) {
  drag = { action: item.name };
  event.dataTransfer.effectAllowed = "copy";
  event.dataTransfer.setData("text/plain", item.name);
  setDragPill(event, item.title, item.color, item.icon);
  beginDragging(event.currentTarget);
}

function blockMenu(event, step, list, ctx) {
  const index = list.indexOf(step);
  const move = (delta) => { list.splice(index, 1); list.splice(index + delta, 0, step); ctx.structure(); };
  menu(event.currentTarget, [
    { label: "Move up", icon: "up", disabled: index === 0, run: () => move(-1) },
    { label: "Move down", icon: "chevron", disabled: index === list.length - 1, run: () => move(1) },
    { label: "Duplicate", icon: "copy", run: () => { list.splice(index + 1, 0, structuredClone(step)); ctx.structure(); } },
    { label: step.skip ? "Turn this step on" : "Turn this step off", icon: "stop", run: () => {
      if (step.skip) delete step.skip; else step.skip = true;
      ctx.structure();
    } },
    { label: "Delete", icon: "trash", danger: true, run: () => {
      list.splice(index, 1);
      ctx.structure();
      ctx.offerUndo("Step deleted");
    } },
  ]);
}

function block(step, list, ctx, where) {
  const moveBy = (delta) => {
    const index = list.indexOf(step);
    const target = index + delta;
    if (target < 0 || target >= list.length) return;
    list.splice(index, 1);
    list.splice(target, 0, step);
    ctx.refocus = step;
    ctx.structure();
  };
  const handle = h("span", { class: "grip", draggable: "true", tabindex: "0", role: "button",
    "aria-label": "Move this step. Press the up or down arrow.", title: "Drag to reorder, or focus and use the arrow keys",
    onkeydown: (event) => {
      if (event.key !== "ArrowUp" && event.key !== "ArrowDown") return;
      event.preventDefault();
      moveBy(event.key === "ArrowUp" ? -1 : 1);
    },
    ondragstart: (event) => {
      drag = { step, list };
      event.dataTransfer.effectAllowed = "move";
      event.dataTransfer.setData("text/plain", "step");
      setDragPill(event, ...stepLabel(step));
      beginDragging(wrap);
    },
    ondragend: endDragging }, icon("grip", 16));
  if (ctx.refocus === step) {
    ctx.refocus = null;
    requestAnimationFrame(() => handle.focus());
  }
  const dots = iconButton("more", "Step options", (event) => blockMenu(event, step, list, ctx));
  const rerender = () => ctx.structure(false);
  let inner;
  if ("if" in step) {
    inner = [h("div", { class: "block-row" }, handle, chip("orange", "branch"),
      h("strong", {}, "If"), needsFilling(step) ? h("span", { class: "tag warn" }, icon("warn", 13), "Fill this in") : null,
      h("span", { class: "grow" }), dots), conditionRows(step, ctx, rerender)];
  } else if ("repeat" in step) {
    const controls = repeatControls(step, ctx);
    inner = [h("div", { class: "block-row" }, handle, chip("orange", "repeat"), h("strong", {}, "Repeat"), controls.head,
      h("span", { class: "grow" }), dots), controls.below];
  } else {
    const def = actionDef(step.action);
    const open = ctx.expanded.has(step);
    const toggleOpen = () => {
      if (open) ctx.expanded.delete(step); else ctx.expanded.add(step);
      rerender();
    };
    const parts = sentence(step).map((part) => part.chip !== undefined
      ? h("span", { class: "pill" }, part.chip) : h("span", {}, part));
    const tools = def?.tools.flat() || [];
    const missing = (S.status?.tools || []).some((t) => !t.found && tools.some((n) => t.tool.split(" or ").includes(n)));
    inner = [h("div", { class: "block-row" }, handle, chip(def?.color || "gray", def?.icon || "zap"),
      h("button", { type: "button", class: "block-title", "aria-expanded": String(open), onclick: toggleOpen },
        open ? h("strong", {}, def?.title || step.action) : parts),
      missing ? h("span", { class: "tag warn", title: "A tool this step needs isn't installed" }, icon("warn", 13), "Tool missing") : null,
      needsFilling(step) ? h("span", { class: "tag warn" }, icon("warn", 13), "Fill this in") : null,
      h("span", { class: "grow" }),
      iconButton("chevron", open ? "Collapse" : "Expand", toggleOpen, open ? "flip" : ""), dots),
    open ? actionDetails(step, def, ctx, rerender) : null];
  }
  const wrap = h("div", { class: `block ${"action" in step ? "" : "control"} ${step.skip ? "skipped" : ""}`, "data-path": where },
    step.skip ? h("span", { class: "off-tag" }, "Off") : null, inner,
    "if" in step ? [nested(step, "then", null, ctx, where), nested(step, "else", "Otherwise", ctx, where)] : null,
    "repeat" in step ? nested(step, "steps", null, ctx, where) : null);
  wrap.addEventListener("dragover", (event) => {
    if (!drag || event.defaultPrevented) return;
    event.preventDefault();
    clearMarks();
    const box = wrap.getBoundingClientRect();
    wrap.classList.add(event.clientY < box.top + box.height / 2 ? "drop-before" : "drop-after");
  });
  wrap.addEventListener("drop", (event) => {
    if (!drag || event.defaultPrevented) return;
    event.preventDefault();
    const box = wrap.getBoundingClientRect();
    const after = event.clientY >= box.top + box.height / 2;
    const target = drag;
    dropInsert(list, list.indexOf(step) + (after ? 1 : 0), ctx);
    if (target === drag) endDragging();
  });
  return wrap;
}

function nested(step, key, title, ctx, where) {
  step[key] = step[key] || [];
  return h("div", { class: "branch" }, title ? h("div", { class: "branch-label" }, title) : null,
    stepList(step[key], ctx, "Drag an action here", `${where}.${key}`));
}

export function stepList(list, ctx, hint, path = "steps") {
  const host = h("div", { class: "steps" }, list.map((step, index) => block(step, list, ctx, `${path}.${index}`)));
  if (!list.length) {
    const zone = h("div", { class: "drop-zone",
      ondragover: (event) => { if (drag) { event.preventDefault(); event.stopPropagation(); clearMarks(); zone.classList.add("drop-into"); } },
      ondragleave: () => zone.classList.remove("drop-into"),
      ondrop: (event) => {
        if (!drag) return;
        event.preventDefault();
        event.stopPropagation();
        dropInsert(list, 0, ctx);
        endDragging();
      } }, hint);
    host.append(zone);
  }
  return host;
}

export function actionPanel(onPick) {
  const categories = ["All", ...new Set(S.actions.map((a) => a.category))];
  let category = "All";
  let query = "";
  const items = [...S.actions, ...CONTROL_BLOCKS].sort((a, b) => a.title.localeCompare(b.title));
  const list = h("div", { class: "action-list" });
  const paint = () => {
    const needle = query.toLowerCase();
    list.replaceChildren(...items
      .filter((a) => (category === "All" || a.category === category)
        && (!needle || `${a.title} ${a.blurb}`.toLowerCase().includes(needle)))
      .map((a) => h("button", { type: "button", class: "action-item", draggable: "true",
        title: "Click to add", onclick: () => onPick(a.name),
        ondragstart: (event) => beginActionDrag(event, a),
        ondragend: endDragging },
        chip(a.color, a.icon),
        h("span", {}, h("strong", {}, a.title), h("small", {}, a.blurb)))));
    chips.replaceChildren(...categories.map((name) => h("button", { type: "button",
      class: `filter ${name === category ? "on" : ""}`, "aria-pressed": String(name === category),
      onclick: () => { category = name; paint(); } }, name)));
  };
  const chips = h("div", { class: "filters" });
  paint();
  return h("aside", { class: "actions-panel", "aria-label": "Action library" },
    h("h2", {}, "Actions"),
    h("label", { class: "search" }, icon("search"), h("input", { type: "search", placeholder: "Search actions", "aria-label": "Search actions",
      oninput: (event) => { query = event.target.value; paint(); } })),
    chips, list,
    h("p", { class: "panel-foot" }, "Click to add, or drag onto the canvas."));
}


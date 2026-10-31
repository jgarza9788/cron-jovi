import { get, post } from "./api.js";
import { toast } from "./ui.js";
import { S, refresh } from "./state.js";

/** Start a run and follow it. onLine gets output as it arrives. */
export async function startRun(slug, handlers = {}) {
  return follow(await post(`/workflows/${slug}/run`), handlers);
}

export async function testStep(step, handlers = {}) {
  return follow(await post("/test-step", step), handlers);
}

function follow({ id }, { onLine, onDone }) {
  let seen = 0;
  const poll = async () => {
    const live = await get(`/live/${id}?from=${seen}`);
    seen += live.lines.length;
    live.lines.forEach((line) => onLine?.(line));
    if (live.done) {
      await refresh();
      onDone?.(live.code);
    } else {
      setTimeout(poll, 250);
    }
  };
  poll();
  return { stop: () => post(`/live/${id}/stop`) };
}

export function quickRun(workflow) {
  let skipped = false;
  startRun(workflow.slug, {
    onLine: (line) => { if (line.startsWith("skipped:")) skipped = true; },
    onDone: (code) => {
      if (skipped) toast(`${workflow.name} is already running`);
      else if (code === 0) toast(`${workflow.name} finished`, "success");
      else {
        const note = S.workflows.find((w) => w.slug === workflow.slug)?.last_run?.note;
        toast(`${workflow.name} didn't work. ${note || ""}`, "error");
      }
    },
  }).catch((err) => toast(err.message, "error"));
  toast(`Running ${workflow.name}…`);
}

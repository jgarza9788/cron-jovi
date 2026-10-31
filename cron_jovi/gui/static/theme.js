import { get } from "./api.js";
import { BOLD_COLORS } from "./ui.js";

let stamp = null;

function luminance(hex) {
  const value = parseInt(hex.slice(1), 16);
  const channel = (shift) => {
    const c = ((value >> shift) & 255) / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  };
  return 0.2126 * channel(16) + 0.7152 * channel(8) + 0.0722 * channel(0);
}

function contrast(a, b) {
  const [light, dark] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (light + 0.05) / (dark + 0.05);
}

/** Themes pick colors for looks. Pull one toward `toward` until it reads on every surface. */
function readable(color, surfaces, toward) {
  for (let amount = 0; amount <= 1; amount += 0.05) {
    const candidate = blend(color, toward, amount);
    if (surfaces.every((surface) => contrast(candidate, surface) >= 4.6)) return candidate;
  }
  return toward;
}

function ink(hex) {
  // Whichever of near-black or white reads better on this colour.
  const light = luminance(hex);
  return 1.05 / (light + 0.05) > (light + 0.05) / 0.056 ? "#ffffff" : "#14161b";
}

function blend(a, b, amount) {
  const parts = [a, b].map((hex) => parseInt(hex.slice(1), 16));
  const out = [16, 8, 0].map((shift) => Math.round(
    ((parts[0] >> shift) & 255) * (1 - amount) + ((parts[1] >> shift) & 255) * amount));
  return `#${out.map((n) => n.toString(16).padStart(2, "0")).join("")}`;
}

const mix = (a, b) => blend(a, b, 0.5);

export function applyTheme(theme) {
  const c = theme.colors;
  const root = document.documentElement.style;
  const set = (name, value) => root.setProperty(`--${name}`, value);
  const surfaces = [c.background, c.dark_background, c.darker_background, c.lighter_background];
  const legible = (color) => readable(color, surfaces, c.foreground);
  set("bg", c.background);
  set("bg-sunken", c.dark_background);
  set("bg-deep", c.darker_background);
  set("bg-raised", c.lighter_background);
  set("text", c.foreground);
  set("text-dim", legible(c.dark_foreground));
  set("text-bright", c.bright_foreground);
  set("muted", c.muted);
  set("accent", c.accent);
  set("accent-ink", ink(c.accent));
  set("selection", c.selection);
  set("red", legible(c.red));
  set("green", legible(c.green));
  set("warn", legible(c.yellow));
  const purple = theme.source === "omarchy" ? mix(c.blue, c.magenta) : c.purple;
  // The bold set stays the same in every theme, so those colors always look bold.
  const swatches = { yellow: c.yellow, blue: c.blue, pink: c.magenta, teal: c.cyan, purple,
    green: c.green, orange: c.orange, gray: theme.source === "omarchy" ? mix(c.foreground, c.muted) : c.gray,
    ...BOLD_COLORS };
  for (const [name, value] of Object.entries(swatches)) {
    set(`c-${name}`, value);
    set(`c-${name}-ink`, ink(value));
  }
  document.documentElement.dataset.mode = c.mode;
  document.documentElement.style.colorScheme = c.mode === "light" ? "light" : "dark";
}

export async function refreshTheme() {
  const theme = await get("/theme");
  if (theme.stamp !== stamp) {
    stamp = theme.stamp;
    applyTheme(theme);
  }
}

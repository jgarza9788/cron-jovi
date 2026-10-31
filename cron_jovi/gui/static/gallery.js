import { del, get, post } from "./api.js";
import { button, confirmDialog, h, icon, iconButton, toast } from "./ui.js";
import { sidebar } from "./library.js";
import { reviewDialog } from "./settings.js";

async function review(galleryId, file) {
  try {
    const { yaml } = await get(`/galleries/${galleryId}/item?file=${encodeURIComponent(file)}`);
    reviewDialog(yaml, await post("/import/review", { yaml }));
  } catch (err) { toast(err.message, "error"); }
}

function itemCard(galleryId, item) {
  if (!item.ok) {
    return h("div", { class: "gallery-card" }, h("span", { class: "chip c-gray" }, icon("warn")),
      h("div", { class: "meta" }, h("strong", {}, item.name), h("small", {}, "Can't be used with this version")));
  }
  return h("div", { class: "gallery-card" },
    h("span", { class: `chip c-${item.color}` }, icon(item.icon)),
    h("div", { class: "meta" }, h("strong", {}, item.name),
      item.description ? h("small", {}, item.description.split("\n")[0]) : null,
      h("small", {}, `${item.trigger} · ${item.actions} action${item.actions === 1 ? "" : "s"}`),
      item.runs_commands ? h("small", { class: "warns" }, "Runs commands on your computer") : null),
    button("Review", () => review(galleryId, item.file), { class: "small" }));
}

export function renderGallery(top, body) {
  top.replaceChildren(h("div", { class: "top-title" }, h("strong", {}, "Gallery"), h("span", {}, "Cron Jovi")));
  const list = h("div", {});
  const paint = async () => {
    const galleries = await get("/galleries");
    if (!galleries.length) {
      list.replaceChildren(h("div", { class: "empty" }, icon("globe", 36), h("h2", {}, "No galleries yet"),
        h("p", {}, "Add a folder or a git address above to browse workflows other people have shared.")));
      return;
    }
    list.replaceChildren(...galleries.flatMap((gallery) => [
      h("div", { class: "gallery-head" }, h("code", { title: gallery.source }, gallery.source),
        gallery.kind === "git" ? button("Update", async () => {
          try { await post(`/galleries/${gallery.id}/update`); await paint(); toast("Up to date"); }
          catch (err) { toast(err.message, "error"); }
        }, { class: "small" }) : null,
        iconButton("trash", "Remove gallery", () => confirmDialog("Remove this gallery?",
          "Workflows you already added stay.", "Remove", async () => {
            await del(`/galleries/${gallery.id}`);
            await paint();
          }))),
      gallery.items.length
        ? h("div", { class: "template-grid" }, gallery.items.map((item) => itemCard(gallery.id, item)))
        : h("p", { class: "hint" }, "No workflow files found here."),
    ]));
  };
  const input = h("input", { class: "input", placeholder: "A folder, or https://…/workflows.git", "aria-label": "Gallery address" });
  const addGallery = async () => {
    const add = page.querySelector(".gallery-add button");
    add.disabled = true;
    try {
      await post("/galleries", { source: input.value });
      input.value = "";
      await paint();
    } catch (err) { toast(err.message, "error"); }
    add.disabled = false;
  };
  const page = h("section", { class: "page" },
    h("div", { class: "page-head" }, h("div", {}, h("h1", {}, "Gallery"),
      h("p", {}, "Shared workflows. You check each one before it's added, and it arrives switched off."))),
    h("div", { class: "gallery-add" }, input, button("Add", addGallery, { class: "primary" })),
    list);
  body.replaceChildren(sidebar("gallery"), page);
  paint().catch((err) => toast(err.message, "error"));
}

from typing import Literal

from ..action_api import ActionError, action


@action("clipboard", tools=["wl-copy", "wl-paste"], title="Clipboard",
        blurb="Read or replace copied text", category="Clipboard", icon="clipboard", color="blue")
def clipboard(ctx, op: Literal["get", "set"] = "get", text: str | None = None) -> str | None:
    if op == "get":
        ctx.summary = "wl-paste"
        return ctx.run(["wl-paste", "--no-newline"])
    if text is None:
        raise ActionError("clipboard set needs text")
    ctx.summary = "wl-copy"
    # wl-copy forks a server that keeps any captured pipe open.
    ctx.run(["wl-copy"], input=text, capture=False)
    return None

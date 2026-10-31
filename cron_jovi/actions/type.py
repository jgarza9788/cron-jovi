import shutil

from ..action_api import ActionError, action


@action("type", tools=[("wtype", "ydotool")], title="Type Text",
        blurb="Send keystrokes to the focused app", category="Windows", icon="keyboard", color="purple")
def type_text(ctx, text: str | None = None, keys: list[str] | None = None) -> None:
    if not text and not keys:
        raise ActionError("type needs text or keys")
    if shutil.which("wtype"):
        ctx.summary = "wtype"
        if text:
            ctx.run(["wtype", "--", text])
        for key in keys or []:
            ctx.run(["wtype", "-k", key])
    elif shutil.which("ydotool"):
        if keys:
            raise ActionError("keys needs wtype; ydotool only supports text here")
        ctx.summary = "ydotool type"
        ctx.run(["ydotool", "type", "--", text])
    else:
        raise ActionError("neither wtype nor ydotool found", 127)

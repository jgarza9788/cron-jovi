from typing import Literal

from .. import compositor
from ..action_api import ActionError, action


@action("window", tools=[("hyprctl", "niri")], title="Control a Window",
        blurb="Focus, close or move a window", category="Windows", icon="grid", color="purple")
def window(
    ctx,
    op: Literal["focus", "close", "move"],
    app: str | None = None,
    workspace: int | None = None,
) -> None:
    target = app or "the focused window"
    ctx.summary = f"{op.title()} {target}"
    if op == "focus" and not app:
        raise ActionError("focus needs an app")
    if op == "move" and workspace is None:
        raise ActionError("move needs a workspace")
    compositor.control_window(op, app, workspace)

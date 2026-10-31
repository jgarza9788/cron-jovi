from .. import compositor
from ..action_api import action


@action("workspace", tools=[("hyprctl", "niri")], title="Switch Workspace",
        blurb="Jump to a numbered workspace", category="Windows", icon="grid", color="purple")
def workspace(ctx, number: int) -> None:
    ctx.summary = f"Switch to workspace {number}"
    compositor.focus_workspace(number)

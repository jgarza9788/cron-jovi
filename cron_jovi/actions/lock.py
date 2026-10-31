import shutil

from ..action_api import action


@action("lock", tools=[("omarchy", "loginctl")], title="Lock Screen", blurb="Lock this computer",
        category="Windows", icon="lock", color="gray")
def lock(ctx) -> None:
    ctx.summary = "Lock the screen"
    if shutil.which("omarchy"):
        ctx.run(["omarchy", "system", "lock"], capture=False)
    else:
        ctx.run(["loginctl", "lock-session"])

import subprocess

from ..action_api import ActionError, action


@action("open", tools=["xdg-open"], title="Open App or URL",
        blurb="Launch in your default app", category="Web", icon="globe", color="pink")
def open_target(ctx, target: str) -> None:
    ctx.summary = f"xdg-open {target}"
    try:
        # xdg-open can stay alive as long as the app, so don't wait for it.
        subprocess.Popen(
            ["xdg-open", target],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except FileNotFoundError:
        raise ActionError("xdg-open not found", 127) from None

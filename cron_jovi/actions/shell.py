import shlex

from ..action_api import ActionError, Duration, action
from ..shellvars import is_sh


@action("shell", tools=["bash"], raw=("run",), title="Run Shell Command",
        blurb="Execute a script or command", category="Scripting", icon="terminal", color="teal")
def shell(ctx, run: str, shell: str = "bash", timeout: Duration | None = None) -> str:
    # What people read has the values filled in. What runs only refers to them.
    shown = ctx.render(run, quote=shlex.quote)
    ctx.summary = shown
    ctx.log(f"$ {shown}")
    # Other languages can't read the environment the same way, so they get quoted text.
    command, env = ctx.render_shell(run) if is_sh(shell) else (shown, {})
    code, output = ctx.stream([shell, "-c", command], timeout, env)
    if code:
        raise ActionError(f"{shell} exited {code}", code)
    return output.strip()

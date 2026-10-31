import shlex

from ..action_api import ActionError, Duration, action


@action("shell", tools=["bash"], raw=("run",), title="Run Shell Command",
        blurb="Execute a script or command", category="Scripting", icon="terminal", color="teal")
def shell(ctx, run: str, shell: str = "bash", timeout: Duration | None = None) -> str:
    # Variables are quoted on the way in, so clipboard text and the like stay data.
    command = ctx.render(run, quote=shlex.quote)
    ctx.summary = command
    ctx.log(f"$ {command}")
    code, output = ctx.stream([shell, "-c", command], timeout)
    if code:
        raise ActionError(f"{shell} exited {code}", code)
    return output.strip()

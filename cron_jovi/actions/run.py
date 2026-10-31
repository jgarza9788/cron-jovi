from .. import paths
from ..action_api import ActionError, action


@action("run", title="Run Another Workflow", blurb="Use a workflow as a step",
        category="Scripting", icon="arrow-right", color="yellow")
def run_other(ctx, workflow: str) -> None:
    # A separate process, so its overlap lock also stops loops: A runs B runs A is skipped.
    ctx.summary = f"Run {workflow}"
    code, _ = ctx.stream([*paths.self_command(), "run", workflow, "--trigger", "workflow"],
                         env={"PYTHONUNBUFFERED": "1"})
    if code:
        raise ActionError(f"{workflow} failed", code)

import time

from ..action_api import Duration, action


@action("wait", title="Wait", blurb="Pause for a set time",
        category="Scripting", icon="clock", color="gray")
def wait(ctx, duration: Duration) -> None:
    ctx.summary = f"Wait {duration:g}s"
    time.sleep(duration)

import shutil
from typing import Literal

from ..action_api import ActionError, action

BACKENDS = {
    "omarchy-shell": {
        "on": ["notifications", "setDnd", "on"],
        "off": ["notifications", "setDnd", "off"],
    },
    "makoctl": {"on": ["mode", "-a", "do-not-disturb"], "off": ["mode", "-r", "do-not-disturb"]},
    "swaync-client": {"on": ["-dn"], "off": ["-df"]},
    "dunstctl": {"on": ["set-paused", "true"], "off": ["set-paused", "false"]},
}


@action("dnd", tools=[tuple(BACKENDS)], title="Do Not Disturb",
        blurb="Silence notifications", category="Windows", icon="moon", color="purple")
def dnd(ctx, state: Literal["on", "off"]) -> None:
    ctx.summary = f"Do Not Disturb → {state}"
    for tool, commands in BACKENDS.items():
        if shutil.which(tool):
            ctx.run([tool, *commands[state]])
            return
    raise ActionError("no supported notification daemon found", 127)

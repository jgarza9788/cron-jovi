from typing import Any

from ..action_api import action


@action("set", title="Set Variable", blurb="Remember a value for later steps",
        category="Scripting", icon="tag", color="gray")
def set_variable(ctx, name: str, value: Any) -> Any:
    ctx.vars[name] = value
    ctx.summary = f"Set {name} = {value}"
    return value

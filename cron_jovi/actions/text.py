import re
from typing import Literal

from ..action_api import ActionError, action


@action("text", title="Change Text", blurb="Trim, change case or replace",
        category="Clipboard", icon="type", color="blue")
def text_action(
    ctx,
    text: str,
    change: Literal["trim", "uppercase", "lowercase", "first-line", "replace", "split"] = "trim",
    find: str = "",
    replace_with: str = "",
    split_at: str = ",",
) -> str | list[str]:
    ctx.summary = f"Text: {change}"
    if change == "trim":
        return text.strip()
    if change == "uppercase":
        return text.upper()
    if change == "lowercase":
        return text.lower()
    if change == "first-line":
        return text.split("\n", 1)[0]
    if change == "split":
        if not split_at:
            raise ActionError("Split needs something to split the text at.")
        return [part.strip() for part in text.split(split_at) if part.strip()]
    if not find:
        raise ActionError("replace needs something to find")
    return re.sub(re.escape(find), lambda _: replace_with, text)

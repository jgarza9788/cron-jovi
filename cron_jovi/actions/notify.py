from typing import Literal

from ..action_api import action


@action("notify", tools=["notify-send"], title="Show Notification",
        blurb="Pop up a desktop message", category="Scripting", icon="bell", color="green")
def notify(
    ctx,
    text: str,
    title: str = "Cron Jovi",
    urgency: Literal["low", "normal", "critical"] = "normal",
) -> None:
    ctx.summary = f'notify-send "{text}"'
    ctx.run(["notify-send", "--app-name=Cron Jovi", "-u", urgency, title, text])

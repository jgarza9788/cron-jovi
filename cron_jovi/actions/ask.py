import subprocess
from typing import Literal

from ..action_api import ActionError, action


@action("ask", tools=["zenity"], title="Ask a Question", blurb="Type an answer, or pick one",
        category="Scripting", icon="help", color="yellow")
def ask(
    ctx,
    question: str,
    kind: Literal["type", "yes-no", "choose"] = "type",
    choices: list[str] | None = None,
) -> str:
    ctx.summary = f"Ask: {question}"
    argv = ["zenity", "--title=Cron Jovi", f"--text={question}"]
    if kind == "type":
        argv.append("--entry")
    elif kind == "yes-no":
        argv.append("--question")
    else:
        if not choices:
            raise ActionError("choose needs a list of choices")
        argv += ["--list", "--column=Choose one", "--hide-header", *choices]
    try:
        done = subprocess.run(argv, capture_output=True, text=True)
    except FileNotFoundError:
        raise ActionError("zenity not found", 127) from None
    if kind == "yes-no" and done.returncode in (0, 1):
        return "yes" if done.returncode == 0 else "no"
    if done.returncode:
        raise ActionError("no answer given")
    return done.stdout.strip()

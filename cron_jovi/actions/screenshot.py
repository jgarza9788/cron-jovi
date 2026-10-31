import subprocess
from datetime import datetime
from pathlib import Path
from typing import Literal

from ..action_api import ActionError, action


@action("screenshot", tools=["grim", "slurp", "wl-copy"], title="Take Screenshot",
        blurb="Grab the screen or a selection", category="Windows", icon="camera", color="teal")
def screenshot(
    ctx,
    area: Literal["screen", "selection"] = "screen",
    send_to: Literal["clipboard", "file"] = "clipboard",
    folder: str = "~/Pictures",
) -> str | None:
    ctx.summary = f"Screenshot of {area} to {send_to}"
    grim = ["grim"]
    if area == "selection":
        grim += ["-g", ctx.run(["slurp"])]
    if send_to == "file":
        path = Path(folder).expanduser() / f"screenshot-{datetime.now():%Y%m%d-%H%M%S}.png"
        path.parent.mkdir(parents=True, exist_ok=True)
        ctx.run([*grim, str(path)])
        return str(path)
    try:
        image = subprocess.run([*grim, "-"], capture_output=True, check=True).stdout
        # wl-copy forks a server that would hold a captured pipe open.
        subprocess.run(["wl-copy", "--type", "image/png"], input=image, check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except FileNotFoundError as err:
        raise ActionError(f"{err.filename} not found", 127) from None
    except subprocess.CalledProcessError as err:
        raise ActionError(f"screenshot failed (exit {err.returncode})", err.returncode) from None
    return None

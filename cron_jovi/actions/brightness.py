import shutil
from pathlib import Path

from ..action_api import ActionError, action


def command(percent: int) -> list[str]:
    if shutil.which("omarchy"):
        return ["omarchy", "brightness", "display", "--no-osd", f"{percent}%"]
    # Without --class, brightnessctl happily "dims" a keyboard LED and reports success.
    if shutil.which("brightnessctl") and any(Path("/sys/class/backlight").glob("*")):
        return ["brightnessctl", "--quiet", "--class=backlight", "set", f"{percent}%"]
    if shutil.which("ddcutil"):
        return ["ddcutil", "setvcp", "10", str(percent)]
    raise ActionError("no adjustable screen found", 127)


@action("brightness", tools=[("omarchy", "brightnessctl", "ddcutil")], title="Screen Brightness",
        blurb="Set the display brightness", category="Windows", icon="sun", color="gray")
def brightness(ctx, percent: int) -> None:
    if not 0 <= percent <= 100:
        raise ActionError(f"percent must be 0-100, got {percent}")
    ctx.summary = f"Set brightness to {percent}%"
    ctx.run(command(percent))

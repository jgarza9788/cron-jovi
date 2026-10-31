import shutil
from typing import Literal

from ..action_api import ActionError, action


def command(do: str, percent: int) -> list[str]:
    if shutil.which("wpctl"):
        sink = "@DEFAULT_AUDIO_SINK@"
        return {
            "set": ["wpctl", "set-volume", sink, f"{percent}%"],
            "mute": ["wpctl", "set-mute", sink, "1"],
            "unmute": ["wpctl", "set-mute", sink, "0"],
        }[do]
    if shutil.which("pamixer"):
        return {
            "set": ["pamixer", "--set-volume", str(percent)],
            "mute": ["pamixer", "--mute"],
            "unmute": ["pamixer", "--unmute"],
        }[do]
    raise ActionError("neither wpctl nor pamixer found", 127)


@action("volume", tools=[("wpctl", "pamixer")], title="Sound Volume", blurb="Set, mute or unmute",
        category="Media", icon="volume", color="pink")
def volume(ctx, do: Literal["set", "mute", "unmute"] = "set", percent: int = 50) -> None:
    if not 0 <= percent <= 100:
        raise ActionError(f"percent must be 0-100, got {percent}")
    ctx.summary = f"Volume → {percent}%" if do == "set" else f"Volume → {do}"
    ctx.run(command(do, percent))

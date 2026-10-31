from typing import Literal

from ..action_api import ActionError, action


@action("media", tools=["playerctl"], title="Media Control",
        blurb="Play, pause or skip", category="Media", icon="pause", color="pink")
def media(
    ctx,
    command: Literal["play", "pause", "play-pause", "stop", "next", "previous"],
    players: str = "all",
) -> None:
    select = "--all-players" if players == "all" else f"--player={players}"
    ctx.summary = f"playerctl {select} {command}"
    try:
        ctx.run(["playerctl", select, command])
    except ActionError as err:
        # Pausing silence already got the result it wanted.
        if command in ("pause", "stop") and "no players" in str(err).lower():
            ctx.summary = "Nothing was playing"
            return
        raise

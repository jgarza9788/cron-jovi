import shutil
from pathlib import Path
from typing import Literal

from ..action_api import ActionError, action


@action("file", title="Move File", blurb="Rename, copy or move",
        category="Files", icon="folder", color="green")
def file(
    ctx,
    op: Literal["move", "copy", "rename"],
    src: str,
    dest: str,
    overwrite: bool = False,
) -> str:
    source = Path(src).expanduser()
    target = Path(dest).expanduser()
    if op == "rename":
        if "/" in dest or dest in ("", ".", ".."):
            raise ActionError(f"“{dest}” isn't a file name. Use move to change folders.")
        target = source.with_name(dest)
    elif target.is_dir():
        target = target / source.name
    ctx.summary = f"{op} {source} → {target}"
    if not source.exists():
        raise ActionError(f"{source} does not exist")
    if target.exists() and not overwrite:
        raise ActionError(f"{target} already exists")
    try:
        if op == "copy" and source.is_dir():
            shutil.copytree(source, target, dirs_exist_ok=overwrite)
        elif op == "copy":
            shutil.copy2(source, target)
        else:
            shutil.move(source, target)
    except OSError as err:
        raise ActionError(str(err)) from None
    return str(target)

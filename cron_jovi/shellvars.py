"""Variables in shell commands.

A value is never pasted into the command, so no quoting mistake can turn a file
name or clipboard text into code. It travels in an environment variable and the
command only refers to it. Getting a context below wrong can garble a value,
but can't run it. The reference just has to suit where the {{ variable }} sits,
so that writing `echo "{{ x }}"` or `'{{ x }}'` still does the expected thing.
"""

import re
from pathlib import Path

PREFIX = "CRONJOVI_VALUE_"
SH_FAMILY = {"bash", "sh", "dash", "zsh", "ksh"}
HEREDOC = re.compile(r"<<-?\s*(['\"]?)(\w+)\1")


def is_sh(shell: str) -> bool:
    return Path(shell).name in SH_FAMILY


def context(text: str) -> str:
    """Where the end of `text` sits: code, double, single or heredoc."""
    stack = ["code"]
    i = 0
    while i < len(text):
        top, char, pair = stack[-1], text[i], text[i:i + 2]
        i += 1
        if top == "single":
            if char == "'":
                stack.pop()
        elif char == "\\":
            i += 1
        elif top == "double" and char == '"':
            stack.pop()
        elif pair == "$(":
            stack.append("code")
            i += 1
        elif char == "`":
            if top == "tick":
                stack.pop()
            else:
                stack.append("tick")
        elif top == "double":
            continue
        elif char == "'":
            stack.append("single")
        elif char == '"':
            stack.append("double")
        elif char == "(":
            stack.append("code")
        elif char == ")" and len(stack) > 1:
            stack.pop()
        elif char == "#" and (i == 1 or text[i - 2].isspace()):
            end = text.find("\n", i)
            i = len(text) if end < 0 else end
        elif text.startswith("<<<", i - 1):
            i += 2
        elif pair == "<<" and (doc := HEREDOC.match(text, i - 1)):
            end = re.compile(rf"^\t*{doc[2]}$", re.M).search(text, doc.end())
            if not end:
                return "heredoc"
            i = end.end()
    return "code" if stack[-1] == "tick" else stack[-1]


def reference(name: str, before: str) -> str:
    """Shell text that expands to variable `name`, given the command `before` it."""
    place = context(before)
    if place == "single":
        return f"""'"${{{name}}}"'"""
    if place in ("double", "heredoc"):
        return f"${{{name}}}"
    return f'"${{{name}}}"'

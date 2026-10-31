import ast
import operator

from ..action_api import ActionError, action

OPERATORS = {
    ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv, ast.Mod: operator.mod,
}


def evaluate(node: ast.AST) -> float:
    """Walks the sum by hand: variables end up in here, so eval() is out of the question."""
    if isinstance(node, ast.Expression):
        return evaluate(node.body)
    if isinstance(node, ast.Constant) and type(node.value) in (int, float):
        return node.value
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
        value = evaluate(node.operand)
        return -value if isinstance(node.op, ast.USub) else value
    if isinstance(node, ast.BinOp) and type(node.op) in OPERATORS:
        return OPERATORS[type(node.op)](evaluate(node.left), evaluate(node.right))
    raise ValueError


@action("math", title="Calculate", blurb="Add, subtract, multiply or divide",
        category="Scripting", icon="hash", color="gray")
def math(ctx, sum: str) -> int | float:
    ctx.summary = f"Calculate {sum}"
    try:
        result = evaluate(ast.parse(sum.strip(), mode="eval"))
    except ZeroDivisionError:
        raise ActionError("That sum divides by zero.") from None
    except (SyntaxError, ValueError, TypeError, RecursionError):
        raise ActionError(f"“{sum}” isn't a sum Cron Jovi can work out. Use numbers and + - * / %.") from None
    if isinstance(result, float) and result.is_integer():
        result = int(result)
    ctx.summary = f"Calculate {sum} = {result}"
    return result

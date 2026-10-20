"""Aritmética pura verificada localmente, sem eval, funções nem acesso ao SO."""
import ast
from decimal import Decimal, InvalidOperation, localcontext
import re


MAX_INPUT = 120
MAX_NODES = 30
MAX_ABS_VALUE = Decimal("100000000000000")


def calculate(expression):
    """Retorna apenas o valor da EXPRESSÃO; o LLM ainda deve verificar a fórmula."""
    if not isinstance(expression, str) or not 1 <= len(expression.strip()) <= MAX_INPUT:
        raise ValueError("Expressão fora do limite.")
    if not re.fullmatch(r"[\d\s.+*/()\-]+", expression) or "**" in expression:
        raise ValueError("Expressão deve conter somente operações aritméticas simples.")
    if expression.count("(") > 12 or expression.count(")") > 12:
        raise ValueError("Expressão contém aninhamento excessivo.")
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as error:
        raise ValueError("Expressão aritmética inválida.") from error
    nodes = list(ast.walk(tree))
    if len(nodes) > MAX_NODES:
        raise ValueError("Expressão excedeu o orçamento de operações.")

    def evaluate(node, depth=0):
        if depth > 15:
            raise ValueError("Expressão muito profunda.")
        if isinstance(node, ast.Expression):
            return evaluate(node.body, depth + 1)
        if isinstance(node, ast.Constant) and type(node.value) in (int, float):
            value = Decimal(ast.get_source_segment(expression, node))
        elif isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
            item = evaluate(node.operand, depth + 1)
            value = -item if isinstance(node.op, ast.USub) else item
        elif isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div)):
            left, right = evaluate(node.left, depth + 1), evaluate(node.right, depth + 1)
            if isinstance(node.op, ast.Add):
                value = left + right
            elif isinstance(node.op, ast.Sub):
                value = left - right
            elif isinstance(node.op, ast.Mult):
                value = left * right
            else:
                if not right:
                    raise ValueError("Divisão por zero.")
                value = left / right
        else:
            raise ValueError("Operação não permitida.")
        if not value.is_finite() or value.copy_abs() > MAX_ABS_VALUE:
            raise ValueError("Valor matemático fora do limite.")
        return value

    try:
        with localcontext() as decimal_context:
            decimal_context.prec = 28
            value = evaluate(tree)
    except (InvalidOperation, OverflowError, ZeroDivisionError) as error:
        raise ValueError("Expressão não pode ser calculada com segurança.") from error
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return {"expression": expression.strip(), "value": text,
            "expression_verified": True,
            "request_interpretation_verified": False}

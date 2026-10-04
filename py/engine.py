"""Math core for Equation Workbench.

Runs both in the browser (inside Pyodide, see js/worker.js) and under plain
CPython for tests. Expressions live in a module-level store keyed by integer
id; the UI only ever holds ids and LaTeX strings, so undo is just "go back to
an older id".
"""

import sympy as sp
from sympy.printing.latex import LatexPrinter
from sympy.parsing.sympy_parser import (
    convert_xor,
    implicit_multiplication_application,
    parse_expr,
    standard_transformations,
)

TRANSFORMATIONS = standard_transformations + (
    implicit_multiplication_application,
    convert_xor,
)
LOCAL_DICT = {"e": sp.E, "pi": sp.pi}

OPERATORS = {
    "+": "+",
    "-": "-",
    "−": "-",  # unicode minus
    "*": "*",
    "×": "*",  # ×
    "/": "/",
    "÷": "/",  # ÷
    "^": "^",
}

_store = {}
_next_id = 0


class UserError(Exception):
    """An error whose message is safe and friendly to show a student."""


# ---------------------------------------------------------------- helpers


def _save(expr):
    global _next_id
    _next_id += 1
    _store[_next_id] = expr
    return _next_id


def _get(expr_id):
    try:
        return _store[int(expr_id)]
    except (KeyError, ValueError, TypeError):
        raise UserError("That step no longer exists. Try starting a new problem.")


class _Printer(LatexPrinter):
    """SymPy's LaTeX printer, made unambiguous for unevaluated products.

    Stock output for x·(3x) is "x 3 x" and for x·6 is "x 6". Here a product
    nested in a product gets brackets and a number that isn't the leading
    factor gets a dot: "x \\left(3 x\\right)", "x \\cdot 6".
    """

    def _print_Mul(self, expr):
        args = list(expr.args)
        sign = ""
        if args[0] == -1 and len(args) > 1:
            sign, args = "-", args[1:]
        fiddly = any(isinstance(a, sp.Mul) for a in args) or any(
            a.is_Number for a in args[1:]
        )
        has_denominator = any(
            isinstance(a, sp.Pow) and a.exp.is_negative for a in args
        )
        if not fiddly or has_denominator:
            return super()._print_Mul(expr)
        if len(args) == 1:
            return sign + self._print(args[0])
        parts = []
        for i, a in enumerate(args):
            tex = self._print(a)
            if isinstance(a, (sp.Mul, sp.Add)) or (a.is_Number and a.is_negative):
                tex = rf"\left({tex}\right)"
            if i and tex[0].isdigit():
                parts.append(r"\cdot")
            parts.append(tex)
        return sign + " ".join(parts)


def to_latex(expr):
    if isinstance(expr, sp.Equality):
        return f"{to_latex(expr.lhs)} = {to_latex(expr.rhs)}"
    # Keep the student's term order while the expression is unevaluated, but
    # use SymPy's tidy polynomial order once a button has evaluated it.
    order = None if _evaluated(expr) == expr else "none"
    return _Printer({"order": order}).doprint(expr)


def _check_parens(text):
    depth = 0
    for ch in text:
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
            if depth < 0:
                raise UserError("There's a ')' without a matching '('.")
    if depth:
        raise UserError("Check your parentheses — one isn't closed.")


def _make_real(expr):
    """Treat every variable as a real number (lets log(e^x) simplify to x)."""
    syms = {s: sp.Symbol(s.name, real=True) for s in expr.free_symbols}
    if "e" in {s.name for s in syms}:
        syms[next(s for s in syms if s.name == "e")] = sp.E
    with sp.evaluate(False):
        return expr.xreplace(syms)


def _parse_side(text):
    text = text.strip()
    if not text:
        raise UserError("Something is missing — there's an empty side.")
    _check_parens(text)
    try:
        if "\\" in text:
            from sympy.parsing.latex import parse_latex

            expr = parse_latex(text, backend="lark")
        else:
            expr = parse_expr(
                text,
                transformations=TRANSFORMATIONS,
                local_dict=dict(LOCAL_DICT),
                evaluate=False,
            )
    except UserError:
        raise
    except Exception:
        raise UserError(f"Couldn't read “{text}”. Check for typos.")
    if not isinstance(expr, sp.Expr):
        raise UserError(f"“{text}” isn't an algebraic expression.")
    return _make_real(expr)


def _parse(text):
    text = (text or "").strip()
    if not text:
        raise UserError("Type an expression or an equation to get started.")
    parts = text.split("=")
    if len(parts) > 2:
        raise UserError("An equation can only have one '=' sign.")
    if len(parts) == 2:
        return sp.Eq(_parse_side(parts[0]), _parse_side(parts[1]), evaluate=False)
    return _parse_side(text)


def _parse_op(op_text):
    op_text = (op_text or "").strip()
    if not op_text:
        raise UserError("Type a step like +1, -x, *2 or /(x+1).")
    op = OPERATORS.get(op_text[0])
    if op is None:
        raise UserError(
            "Start with +, −, *, / or ^ — for example +1 or /(x+1)."
        )
    rest = op_text[1:].strip()
    if not rest:
        raise UserError(f"What should come after '{op_text[0]}'?")
    operand = _parse_side(rest)
    if "=" in rest:
        raise UserError("A step can't contain '='.")
    if op == "/" and operand.is_zero:
        raise UserError("You can't divide by zero.")
    return op, operand


def _wrap(operand, op):
    tex = to_latex(operand)
    needs_parens = (
        isinstance(operand, sp.Add)
        or (operand.is_number and operand.is_negative)
        or (op in "/^" and isinstance(operand, sp.Mul))
    )
    return rf"\left({tex}\right)" if needs_parens else tex


def _op_label(op, operand):
    w = _wrap(operand, op)
    return {
        "+": f"+\\,{w}",
        "-": f"-\\,{w}",
        "*": f"\\times\\,{w}",
        "/": f"\\div\\,{w}",
        "^": f"(\\;\\cdot\\;)^{{{w}}}",
    }[op]


def _apply_to_side(side, op, operand):
    with sp.evaluate(False):
        if op == "+":
            terms = side.args if isinstance(side, sp.Add) else (side,)
            return sp.Add(*terms, operand)
        if op == "-":
            terms = side.args if isinstance(side, sp.Add) else (side,)
            neg = -operand if operand.is_number else sp.Mul(-1, operand)
            return sp.Add(*terms, neg)
        if op == "*":
            return sp.Mul(operand, side)
        if op == "/":
            return sp.Mul(side, sp.Pow(operand, -1))
        if op == "^":
            return sp.Pow(side, operand)
    raise UserError("Unknown operation.")  # pragma: no cover


def _evaluated(expr):
    """Rebuild an unevaluated tree with normal SymPy evaluation turned on."""
    if not expr.args:
        return expr
    return expr.func(*(_evaluated(a) for a in expr.args))


def _per_side(expr, fn):
    if isinstance(expr, sp.Equality):
        return sp.Eq(fn(expr.lhs), fn(expr.rhs), evaluate=False)
    return fn(expr)


def _split_term(term):
    """Split a term into (rational coefficient, its other factors).

    The other factors are compared as written, in any order, so 2xy and yx
    match but x·x and x^2 don't. Nothing is evaluated.
    """
    factors, stack = [], [term]
    while stack:
        t = stack.pop()
        if isinstance(t, sp.Mul):
            stack.extend(reversed(t.args))
        else:
            factors.append(t)
    coeff, rest = sp.Integer(1), []
    for f in factors:
        value = _evaluated(f) if f.is_number else None
        if value is not None and value.is_Rational:
            coeff *= value
        else:
            rest.append(f)
    return coeff, tuple(sorted(rest, key=sp.default_sort_key))


def _build_term(coeff, key):
    if not key:
        return coeff
    with sp.evaluate(False):
        if coeff == 1:
            return key[0] if len(key) == 1 else sp.Mul(*key)
        return sp.Mul(coeff, *key)


def combine_like_terms(expr):
    """Add up the coefficients of matching terms in every sum, and nothing else.

    3x^2 + 2x^2 + x -> 5x^2 + x, but 2(x+1) stays put and log(e^x) is left alone.
    """
    if not expr.args:
        return expr
    args = [combine_like_terms(a) for a in expr.args]
    if not isinstance(expr, sp.Add):
        with sp.evaluate(False):
            return expr.func(*args)
    groups = {}  # dicts keep first-seen order, so the student's order survives
    for a in args:
        for t in a.args if isinstance(a, sp.Add) else (a,):
            coeff, key = _split_term(t)
            groups[key] = groups.get(key, 0) + coeff
    terms = [_build_term(c, k) for k, c in groups.items() if c != 0]
    if not terms:
        return sp.Integer(0)
    with sp.evaluate(False):
        return terms[0] if len(terms) == 1 else sp.Add(*terms)


TRANSFORMS = {
    "combine": combine_like_terms,
    "simplify": lambda e: sp.simplify(_evaluated(e)),
    "distribute": lambda e: sp.expand(_evaluated(e)),
    "factor": lambda e: sp.factor(_evaluated(e)),
}
LABELS = {"combine": "combine like terms"}


# ---------------------------------------------------------------- public API


def parse_problem(text):
    expr = _parse(text)
    return {"id": _save(expr), "latex": to_latex(expr)}


def apply_op(expr_id, op_text):
    expr = _get(expr_id)
    op, operand = _parse_op(op_text)
    new = _per_side(expr, lambda side: _apply_to_side(side, op, operand))
    return {"id": _save(new), "latex": to_latex(new), "label": _op_label(op, operand)}


def transform(expr_id, kind):
    expr = _get(expr_id)
    fn = TRANSFORMS.get(kind)
    if fn is None:
        raise UserError(f"Unknown button: {kind}")
    new = _per_side(expr, fn)
    label = rf"\text{{{LABELS.get(kind, kind)}}}"
    return {"id": _save(new), "latex": to_latex(new), "label": label}


def preview(text, mode="problem"):
    """LaTeX for the live preview under the input box ('' if not parseable yet)."""
    try:
        if mode == "op":
            return _op_label(*_parse_op(text))
        return to_latex(_parse(text))
    except Exception:
        return ""


def reset():
    global _next_id
    _store.clear()
    _next_id = 0

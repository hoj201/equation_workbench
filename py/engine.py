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
        # The stock printer routes x**-1 here too; that one prints as 1/x.
        if not isinstance(expr, sp.Mul):
            return super()._print_Mul(expr)
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
        if has_denominator:
            return sign + self._print_fraction(args)
        if not fiddly:
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

    def _print_fraction(self, args):
        """One \\frac for the whole product, so 1·3⁻¹ reads 1/3, not 1·(1/3)."""
        top, bottom = [], []
        for a in args:
            if isinstance(a, sp.Pow) and a.exp.is_negative:
                exp = -a.exp
                bottom.append(a.base if exp == 1 else sp.Pow(a.base, exp, evaluate=False))
            else:
                top.append(a)
        sign = ""
        lead = top[0] if top else None
        if lead is not None and lead.is_Number and lead.is_negative and not (
            bottom[0].is_Number and bottom[0].is_negative
        ):
            sign = "-"
            top = top[1:] if lead == -1 else [-lead] + top[1:]
        with sp.evaluate(False):
            num = sp.Mul(*top) if len(top) > 1 else (top[0] if top else sp.Integer(1))
            den = sp.Mul(*bottom) if len(bottom) > 1 else bottom[0]
        return rf"{sign}\frac{{{self._print(num)}}}{{{self._print(den)}}}"


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


def _flatten_mul(term):
    factors, stack = [], [term]
    while stack:
        t = stack.pop()
        if isinstance(t, sp.Mul):
            stack.extend(reversed(t.args))
        else:
            factors.append(t)
    return factors


class _Fraction:
    """One product split into numbers and other factors, top and bottom.

    x·2/(3y) -> top numbers [2], top factors [[x, 1]], bottom numbers [3],
    bottom factors [[y, 1]]. Factors are [base, exponent] pairs.
    """

    def __init__(self, term):
        self.top_numbers, self.top = [], []
        self.bottom_numbers, self.bottom = [], []
        factors = _flatten_mul(term)
        # -2x is stored as -1·2·x, but it's one number to a student.
        if len(factors) > 1 and factors[0] == -1 and factors[1].is_Integer:
            factors = [-factors[1]] + factors[2:]
        for f in factors:
            self._add(f, top=True)

    def _add(self, factor, top):
        if isinstance(factor, sp.Pow) and factor.exp.is_Integer and factor.exp < 0:
            exp = -factor.exp
            for f in _flatten_mul(factor.base):
                self._add(f if exp == 1 else sp.Pow(f, exp, evaluate=False), not top)
            return
        if factor.is_number:
            value = _evaluated(factor)
            if value.is_Integer or value.is_Float:
                (self.top_numbers if top else self.bottom_numbers).append(value)
                return
            if value.is_Rational:
                if value.p != 1:
                    (self.top_numbers if top else self.bottom_numbers).append(sp.Integer(value.p))
                (self.bottom_numbers if top else self.top_numbers).append(sp.Integer(value.q))
                return
        base, exp = factor, sp.Integer(1)
        if isinstance(factor, sp.Pow) and factor.exp.is_Integer:
            base, exp = factor.base, factor.exp
        (self.top if top else self.bottom).append([base, exp])

    def build(self):
        def power(base, exp):
            return base if exp == 1 else sp.Pow(base, exp, evaluate=False)

        def parts(numbers, factors):
            return list(numbers) + [power(b, e) for b, e in factors if e]

        with sp.evaluate(False):
            top = parts(self.top_numbers, self.top) or [sp.Integer(1)]
            bottom = parts(self.bottom_numbers, self.bottom)
            if bottom:
                denominator = bottom[0] if len(bottom) == 1 else sp.Mul(*bottom)
                if top == [1]:
                    top = []
                top.append(sp.Pow(denominator, -1))
            return top[0] if len(top) == 1 else sp.Mul(*top)


def _cancel_plan(term):
    """Work out what cancels in one product (see _cancel_product).

    Returns None when nothing cancels. Otherwise returns the _Fraction with
    factor exponents already reduced, the factor exponents from before, the
    magnitudes the integer numbers top and bottom reduce to, and whether the
    result is negative.
    """
    frac = _Fraction(term)
    exps_before = ([e for _, e in frac.top], [e for _, e in frac.bottom])
    cancelled = False
    for d in frac.bottom:
        for n in frac.top:
            if n[1] and d[1] and _evaluated(n[0]) == _evaluated(d[0]):
                k = min(n[1], d[1])
                n[1] -= k
                d[1] -= k
                cancelled = True

    # Numbers cancel pairwise by their common factor; signs are pooled.
    tops = [n for n in frac.top_numbers if n.is_Integer]
    bottoms = [n for n in frac.bottom_numbers if n.is_Integer]
    negative = sum(bool(n < 0) for n in tops + bottoms) % 2
    tops, bottoms = [int(abs(n)) for n in tops], [int(abs(n)) for n in bottoms]
    for i in range(len(bottoms)):
        for j in range(len(tops)):
            g = sp.igcd(tops[j], bottoms[i])
            if g > 1:
                tops[j] //= g
                bottoms[i] //= g
                cancelled = True
    if not cancelled:
        return None
    return frac, exps_before, tops, bottoms, negative


def _cancel_product(term):
    """Cancel what matches top and bottom: (x+1)(x+2)/(x+1) -> x+2, 4/6 -> 2/3.

    Factors only cancel when they match as written; nothing is factored or
    expanded, and numbers on the same level are not multiplied together.
    Returns None when there is nothing to cancel.
    """
    plan = _cancel_plan(term)
    if plan is None:
        return None
    frac, _, tops, bottoms, negative = plan
    frac.top_numbers = [sp.Integer(n) for n in tops if n != 1] + [
        n for n in frac.top_numbers if not n.is_Integer
    ]
    frac.bottom_numbers = [sp.Integer(n) for n in bottoms if n != 1] + [
        n for n in frac.bottom_numbers if not n.is_Integer
    ]
    if negative:
        if frac.top_numbers:
            frac.top_numbers[0] = -frac.top_numbers[0]
        else:
            frac.top_numbers = [sp.Integer(-1)]
    return frac.build()


def _multiply_product(term):
    """Multiply the plain numbers in a product: 3·4 -> 12, 2·3x -> 6x.

    Numbers on top are multiplied together, and so are numbers on the
    bottom, but top and bottom are left for cancel to deal with.
    Returns None when there is nothing to multiply.
    """
    frac = _Fraction(term)
    if len(frac.top_numbers) < 2 and len(frac.bottom_numbers) < 2:
        return None
    for side in ("top_numbers", "bottom_numbers"):
        numbers = getattr(frac, side)
        if len(numbers) > 1:
            value = sp.Mul(*numbers)
            setattr(frac, side, [] if value == 1 and side == "bottom_numbers" else [value])
    return frac.build()


def _per_product(fn):
    """Apply fn to every product in an expression, innermost first."""

    def walk(expr):
        if not expr.args:
            return expr
        with sp.evaluate(False):
            rebuilt = expr.func(*(walk(a) for a in expr.args))
        if isinstance(rebuilt, sp.Mul) or (
            isinstance(rebuilt, sp.Pow) and rebuilt.is_number
        ):
            return fn(rebuilt) or rebuilt
        return rebuilt

    return walk


cancel_common_factors = _per_product(_cancel_product)
multiply_numbers = _per_product(_multiply_product)


# ---------------------------------------------------------------- highlights
# LaTeX for the moment before a power-up lands: like terms in matching
# colours, cancelled factors struck through. Only the top level of each side
# is marked up; anything deeper is printed as usual.

MARK_COLORS = ["#ff3fa4", "#3ff3ff", "#ffe23f", "#ff8c3f", "#a6ff4d", "#b78cff"]
CANCEL_COLOR = "#ff3fa4"


def _terms(expr):
    if not isinstance(expr, sp.Add):
        return [expr]
    return [t for a in expr.args for t in _terms(a)]


def _join_terms(pieces):
    """pieces: (term, latex or None, colour or None). Signs are pulled out
    like the stock _print_Add does."""
    out = []
    for i, (term, tex, color) in enumerate(pieces):
        op = "+"
        if i and tex is None and term.could_extract_minus_sign():
            op, term = "-", -term
        if tex is None:
            tex = to_latex(term)
        elif i and tex.startswith("-"):
            op, tex = "-", tex[1:].lstrip()
        if color:
            tex = rf"{{\color{{{color}}}{{{tex}}}}}"
            op = rf"\mathbin{{\color{{{color}}}{{{op}}}}}"
        out.append(tex if i == 0 else f"{op} {tex}")
    return " ".join(out)


def _combine_marks(side):
    terms = _terms(side)
    keys = [_split_term(t)[1] for t in terms]
    repeated = [k for k in dict.fromkeys(keys) if keys.count(k) > 1]
    if not repeated:
        return None
    colors = {k: MARK_COLORS[i % len(MARK_COLORS)] for i, k in enumerate(repeated)}
    return _join_terms([(t, None, colors.get(k)) for t, k in zip(terms, keys)])


def _marked_fraction(term):
    plan = _cancel_plan(term)
    if plan is None:
        return None
    frac, (top_exps, bottom_exps), tops, bottoms, _ = plan

    def struck(tex, left=None, top=True):
        tex = rf"\cancel{{{tex}}}"
        if left is not None:
            tex = rf"\overset{{{left}}}{{{tex}}}" if top else rf"\underset{{{left}}}{{{tex}}}"
        return rf"{{\color{{{CANCEL_COLOR}}}{tex}}}"

    def numbers(values, after, top):
        out, j = [], 0
        for v in values:
            tex = to_latex(v)
            if v.is_Integer:
                left = after[j]
                j += 1
                if left != abs(v):
                    tex = struck(tex, None if left == 1 else left, top)
            out.append(("number", tex))
        return out

    def factors(pairs, before, top):
        out = []
        for (base, exp), was in zip(pairs, before):
            tex = to_latex(base if was == 1 else sp.Pow(base, was, evaluate=False))
            if was == 1 and isinstance(base, (sp.Add, sp.Mul)):
                tex = rf"\left({tex}\right)"
            if exp != was:
                left = None if exp == 0 else to_latex(
                    base if exp == 1 else sp.Pow(base, exp, evaluate=False)
                )
                tex = struck(tex, left, top)
            out.append(("factor", tex))
        return out

    def row(items):
        parts = []
        for i, (kind, tex) in enumerate(items):
            if i and kind == "number":
                parts.append(r"\cdot")
            parts.append(tex)
        return " ".join(parts)

    top = row(numbers(frac.top_numbers, tops, True) + factors(frac.top, top_exps, True))
    bottom = row(numbers(frac.bottom_numbers, bottoms, False) + factors(frac.bottom, bottom_exps, False))
    top = top or "1"
    return rf"\frac{{{top}}}{{{bottom}}}" if bottom else top


def _cancel_marks(side):
    terms = _terms(side)
    marked = []
    for t in terms:
        sign = ""
        if isinstance(t, sp.Mul) and t.args[0] == -1 and len(t.args) > 1:
            # Keep "- 6/3" as a subtraction rather than marking up "-6".
            sign, t = "-", t.args[1] if len(t.args) == 2 else sp.Mul(*t.args[1:], evaluate=False)
        m = _marked_fraction(t) if isinstance(t, (sp.Mul, sp.Pow)) else None
        marked.append(sign + m if m else None)
    if not any(marked):
        return None
    pieces = [(t, m, None) for t, m in zip(terms, marked)]
    return _join_terms(pieces)


MARKERS = {"combine": _combine_marks, "cancel": _cancel_marks}


def highlight(expr_id, kind):
    """LaTeX showing what a power-up is about to do, or '' if there's no picture."""
    expr = _get(expr_id)
    mark = MARKERS.get(kind)
    if mark is None:
        return ""
    sides = [expr.lhs, expr.rhs] if isinstance(expr, sp.Equality) else [expr]
    marked = [mark(s) for s in sides]
    if not any(marked):
        return ""
    return " = ".join(m or to_latex(s) for s, m in zip(sides, marked))


def _variables(expr):
    return sorted({s.name for s in expr.free_symbols})


def _is_tidy(expr):
    """No power-up would change it: 4/2, 3·4 and 2x + x aren't tidy yet."""
    latex = to_latex(expr)
    return all(
        to_latex(fn(expr)) == latex
        for fn in (combine_like_terms, cancel_common_factors, multiply_numbers)
    )


def _is_solved(expr, target=None):
    """y = ... or ... = y, with no y on the other side and nothing left to tidy.

    A number on the other side must be a plain one (x = 4, not x = 4/2).
    Without a target, the equation's only variable is the target.
    """
    if not isinstance(expr, sp.Equality):
        return False
    if target is None:
        names = _variables(expr)
        if len(names) != 1:
            return False
        target = names[0]
    for var, val in ((expr.lhs, expr.rhs), (expr.rhs, expr.lhs)):
        if not (isinstance(var, sp.Symbol) and var.name == target):
            continue
        if val.is_number:
            value = _evaluated(val)
            plain = to_latex(val).replace(" ", "") == to_latex(value).replace(" ", "")
            if (value.is_Rational or value.is_Float) and plain:
                return True
        elif target not in _variables(val) and _is_tidy(val):
            return True
    return False


TRANSFORMS = {
    "combine": combine_like_terms,
    "cancel": cancel_common_factors,
    "multiply": multiply_numbers,
    "simplify": lambda e: sp.simplify(_evaluated(e)),
    "distribute": lambda e: sp.expand(_evaluated(e)),
    "factor": lambda e: sp.factor(_evaluated(e)),
}
LABELS = {
    "combine": "combine like terms",
    "cancel": "cancel common factors",
    "multiply": "multiply numbers",
}


# ---------------------------------------------------------------- public API


def parse_problem(text):
    expr = _parse(text)
    return {"id": _save(expr), "latex": to_latex(expr), "variables": _variables(expr)}


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


def options(expr_id, target=None):
    """Which of the arcade-mode buttons would change this step, and is it
    solved for target (a variable name)?"""
    expr = _get(expr_id)
    latex = to_latex(expr)
    return {
        "combine": to_latex(_per_side(expr, combine_like_terms)) != latex,
        "cancel": to_latex(_per_side(expr, cancel_common_factors)) != latex,
        "multiply": to_latex(_per_side(expr, multiply_numbers)) != latex,
        "solved": _is_solved(expr, target),
    }


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

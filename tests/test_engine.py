import pathlib
import sys

import pytest
import sympy as sp

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "py"))

import engine  # noqa: E402
from engine import UserError  # noqa: E402

x = sp.Symbol("x", real=True)


@pytest.fixture(autouse=True)
def _reset():
    engine.reset()


def expr_of(result):
    return engine._store[result["id"]]


# ---------------------------------------------------------------- parsing


def test_parse_ascii_keeps_input_unevaluated():
    r = engine.parse_problem("2x+x+1")
    assert r["latex"] == "2 x + x + 1"


def test_parse_equation():
    r = engine.parse_problem("2x+1=5")
    assert r["latex"] == "2 x + 1 = 5"
    assert isinstance(expr_of(r), sp.Equality)


def test_parse_power_and_implicit_mult():
    assert engine.parse_problem("3(x+1)^2")["latex"] == r"3 \left(x + 1\right)^{2}"


def test_parse_latex():
    r = engine.parse_problem(r"\frac{x}{2}+1=3")
    assert sp.simplify(_ev(expr_of(r).lhs) - (x / 2 + 1)) == 0


def test_variables_are_real():
    r = engine.parse_problem("x+y")
    assert all(s.is_real for s in expr_of(r).free_symbols)


@pytest.mark.parametrize(
    "text,msg",
    [
        ("", "get started"),
        ("(x+1", "parentheses"),
        ("x+1)", "without a matching"),
        ("x=1=2", "one '='"),
        ("x+=3", "Couldn't read"),
        ("=3", "empty side"),
    ],
)
def test_parse_errors(text, msg):
    with pytest.raises(UserError, match=msg):
        engine.parse_problem(text)


# ---------------------------------------------------------------- ops


def _ev(e):
    return engine._evaluated(e)


def test_add_both_sides_is_not_simplified():
    r = engine.parse_problem("2x+x=5")
    r = engine.apply_op(r["id"], "+1")
    assert r["latex"] == "2 x + x + 1 = 5 + 1"
    assert r["label"] == r"+\,1"


def test_subtract_and_divide_solve_linear():
    r = engine.parse_problem("2x+1=5")
    r = engine.apply_op(r["id"], "-1")
    assert r["latex"] == "2 x + 1 - 1 = 5 - 1"
    r = engine.apply_op(r["id"], "/2")
    r = engine.transform(r["id"], "simplify")
    assert r["latex"] == "x = 2"


def test_subtract_expression():
    r = engine.parse_problem("3x")
    r = engine.apply_op(r["id"], "-(x+1)")
    assert r["latex"] == r"3 x - \left(x + 1\right)"


def test_divide_by_expression():
    r = engine.parse_problem("x^2-1=0")
    r = engine.apply_op(r["id"], "/(x+1)")
    assert r["label"] == r"\div\,\left(x + 1\right)"
    assert sp.simplify(_ev(expr_of(r).lhs) - (x - 1)) == 0


def test_multiply_and_power():
    r = engine.parse_problem("x+1")
    assert engine.apply_op(r["id"], "*2")["latex"] == r"2 \left(x + 1\right)"
    assert engine.apply_op(r["id"], "^2")["latex"] == r"\left(x + 1\right)^{2}"


def test_unicode_operators():
    r = engine.parse_problem("x")
    assert engine.apply_op(r["id"], "÷2")["label"] == r"\div\,2"
    assert engine.apply_op(r["id"], "− 3")["label"] == r"-\,3"


@pytest.mark.parametrize(
    "op,msg",
    [
        ("", "Type a step"),
        ("2", "Start with"),
        ("+", "after"),
        ("/0", "divide by zero"),
        ("+(x", "parentheses"),
    ],
)
def test_op_errors(op, msg):
    r = engine.parse_problem("x")
    with pytest.raises(UserError, match=msg):
        engine.apply_op(r["id"], op)


def test_old_ids_survive_for_undo():
    a = engine.parse_problem("x=1")
    b = engine.apply_op(a["id"], "+1")
    c = engine.apply_op(a["id"], "*3")  # branching from an older step works
    assert b["id"] != c["id"]
    assert engine._store[a["id"]] == expr_of(a)


# ---------------------------------------------------------------- buttons


def test_simplify_combines_like_terms():
    r = engine.parse_problem("2x+x+1+1")
    assert engine.transform(r["id"], "simplify")["latex"] == "3 x + 2"


def test_simplify_power_of_power():
    r = engine.parse_problem("(x^3)^2")
    assert engine.transform(r["id"], "simplify")["latex"] == "x^{6}"


def test_simplify_log_exp():
    r = engine.parse_problem("log(e^x)")
    assert engine.transform(r["id"], "simplify")["latex"] == "x"


def test_distribute():
    r = engine.parse_problem("3x(2x+1)")
    r = engine.transform(r["id"], "distribute")
    assert _ev(expr_of(r)) == 6 * x**2 + 3 * x
    assert r["label"] == r"\text{distribute}"


def test_factor():
    r = engine.parse_problem("6x^2+3x")
    r = engine.transform(r["id"], "factor")
    assert expr_of(r) == 3 * x * (2 * x + 1)


def test_buttons_apply_per_side():
    r = engine.parse_problem("2(x+1)=4x+2x")
    r = engine.transform(r["id"], "distribute")
    assert r["latex"] == "2 x + 2 = 6 x"


# ---------------------------------------------------------------- preview


def test_preview():
    assert engine.preview("x^2=4") == "x^{2} = 4"
    assert engine.preview("/(x+1)", "op") == r"\div\,\left(x + 1\right)"
    assert engine.preview("(x+", "problem") == ""

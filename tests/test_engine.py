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


def test_products_print_unambiguously():
    r = engine.parse_problem("3x=6")
    assert engine.apply_op(r["id"], "*x")["latex"] == r"x \left(3 x\right) = x \cdot 6"


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


@pytest.mark.parametrize(
    "text, expected",
    [
        ("3x^2+2x^2+x", "5 x^{2} + x"),
        ("2x+3x+1", "5 x + 1"),
        ("x+2y+3x-y", "4 x + y"),
        ("xy+2yx", "3 x y"),
        ("x/2+x/2", "x"),
        ("3x-3x", "0"),
        ("x-2x", "- x"),
        # Only like terms are touched: no distributing, cancelling or log rules.
        ("2(x+1)+3", r"2 \left(x + 1\right) + 3"),
        ("log(e^x)+x+x", r"\log{\left(e^{x} \right)} + 2 x"),
        ("(x^3)^2+x", r"\left(x^{3}\right)^{2} + x"),
        ("x/x+1", r"\frac{x}{x} + 1"),
        # ...but sums inside brackets are combined too.
        ("(2x+3x)^2", r"\left(5 x\right)^{2}"),
        ("3x(2x+3x)", r"3 x \left(5 x\right)"),
    ],
)
def test_combine_like_terms(text, expected):
    r = engine.parse_problem(text)
    assert engine.transform(r["id"], "combine")["latex"] == expected


def test_combine_like_terms_is_lighter_than_simplify():
    r = engine.parse_problem("3x^2+2x^2+x")
    assert engine.transform(r["id"], "simplify")["latex"] == r"x \left(5 x + 1\right)"
    r = engine.transform(r["id"], "combine")
    assert r["label"] == r"\text{combine like terms}"


def test_combine_like_terms_per_side():
    r = engine.parse_problem("2x+x+1=5+1")
    assert engine.transform(r["id"], "combine")["latex"] == "3 x + 1 = 6"


def test_combine_like_terms_with_nothing_to_combine():
    r = engine.parse_problem("x+1")
    assert engine.transform(r["id"], "combine")["latex"] == r["latex"]


# ---------------------------------------------------------------- preview


def test_preview():
    assert engine.preview("x^2=4") == "x^{2} = 4"
    assert engine.preview("/(x+1)", "op") == r"\div\,\left(x + 1\right)"
    assert engine.preview("(x+", "problem") == ""


# ---------------------------------------------------------------- arcade mode


def _steps(start, *steps):
    """Run a problem through ops ('+1') and buttons ('!cancel'); return the last result."""
    r = engine.parse_problem(start)
    for s in steps:
        r = engine.transform(r["id"], s[1:]) if s[0] == "!" else engine.apply_op(r["id"], s)
    return r


@pytest.mark.parametrize(
    "start,steps,expected",
    [
        ("2x=4", ["/2"], "x = 2"),
        ("x/3=4", ["*3"], r"x = 3 \cdot 4"),
        ("x=3/6", [], r"x = \frac{1}{2}"),
        ("2x=-4", ["/(-4)"], r"-\frac{x}{2} = 1"),
        ("-2x=6", ["/-2"], "x = -3"),
        ("6x=4", ["/6"], r"x = \frac{2}{3}"),
        ("2x/3=4", ["*3/2"], r"x = 3 \cdot 2"),
        ("(x+1)(x+2)/(x+1)", [], "x + 2"),
        ("x^3/x", [], "x^{2}"),
    ],
)
def test_cancel_common_factors(start, steps, expected):
    r = _steps(start, *steps, "!cancel")
    assert r["latex"] == expected
    assert r["label"] == r"\text{cancel common factors}"


@pytest.mark.parametrize(
    "start,steps,expected",
    [
        ("x/3=4", ["*3", "!cancel"], "x = 12"),
        ("x=2*3*x", [], "x = 6 x"),
        ("2*3*x/(4*5)", [], r"\frac{6 x}{20}"),
        ("x/4=-3", ["*4", "!cancel"], "x = -12"),
    ],
)
def test_multiply_numbers(start, steps, expected):
    r = _steps(start, *steps, "!multiply")
    assert r["latex"] == expected
    assert r["label"] == r"\text{multiply numbers}"


def test_negative_numbers_are_single_numbers():
    # -2x/-2 has nothing to multiply, and 6/(-2) mustn't sprout a -1 factor.
    r = _steps("-2x=6", "/-2")
    assert engine.options(r["id"])["multiply"] is False
    assert _steps("-2x=6", "/-2", "!cancel")["latex"] == "x = -3"


@pytest.mark.parametrize(
    "start,steps,expected",
    [
        ("-x=5", ["*(-1)", "!multiply"], "x = -5"),
        ("-2x=6", ["*(-1)", "!multiply", "/2", "!cancel"], "x = -3"),
        ("-x=5", ["/(-1)", "!cancel"], "x = -5"),
        ("x/1=5", ["!cancel"], "x = 5"),
        ("1*x=5", ["!multiply"], "x = 5"),
        ("-3x=5", ["/(-3)", "!cancel"], r"x = -\frac{5}{3}"),
    ],
)
def test_solving_with_minus_one(start, steps, expected):
    r = _steps(start, *steps)
    assert r["latex"] == expected
    assert engine.options(r["id"], "x")["solved"] is True


def test_minus_a_negative_prints_with_brackets():
    assert _steps("-x=5", "*(-1)")["latex"] == r"-\left(- x\right) = \left(-1\right) 5"


def test_multiply_numbers_leaves_fractions_for_cancel():
    r = engine.parse_problem("6/3")
    assert engine.options(r["id"])["multiply"] is False
    assert engine.options(r["id"])["cancel"] is True


def test_cancel_leaves_sums_alone():
    # (2x+4)/2 needs factoring first; cancel doesn't factor.
    r = engine.parse_problem("(2x+4)/2")
    assert engine.options(r["id"])["cancel"] is False


def test_options_track_the_solve():
    r = engine.parse_problem("2x+1=5")
    assert engine.options(r["id"]) == {
        "combine": False, "cancel": False, "multiply": False,
        "distribute_step": False, "factor_out": False, "solved": False,
    }
    r = _steps("2x+1=5", "-1")
    assert engine.options(r["id"])["combine"] is True
    r = _steps("2x+1=5", "-1", "!combine", "/2")
    assert engine.options(r["id"])["cancel"] is True
    r = _steps("2x+1=5", "-1", "!combine", "/2", "!cancel")
    assert engine.options(r["id"]) == {
        "combine": False, "cancel": False, "multiply": False,
        "distribute_step": False, "factor_out": False, "solved": True,
    }


@pytest.mark.parametrize(
    "text,solved",
    [("x=4", True), ("4=x", True), ("x=-2/3", True), ("x=2.5", True),
     ("x=4/2", False), ("2x=4", False), ("x=y", False), ("x+1", False)],
)
def test_solved(text, solved):
    assert engine.options(engine.parse_problem(text)["id"])["solved"] is solved


def test_reciprocals_print_as_fractions():
    assert _steps("3x=1", "/3")["latex"] == r"\frac{3 x}{3} = \frac{1}{3}"
    assert _steps("x=1", "/(x+1)")["latex"] == r"\frac{x}{x + 1} = \frac{1}{x + 1}"


@pytest.mark.parametrize(
    "start,expected",
    [
        ("3(x+1)", r"3 x + 3 \cdot 1"),
        ("x(y-1)", "x y - x"),
        ("-2(x-3)", r"- 2 x + \left(-2\right) \left(-3\right)"),
        ("5-2(x+1)", r"5 - 2 x - 2 \cdot 1"),
        ("3(x+1)/2", r"\frac{3 x + 3 \cdot 1}{2}"),
        # one bracket at a time
        ("2(3(x+1)+1)", r"2 \left(3 \left(x + 1\right)\right) + 2 \cdot 1"),
    ],
)
def test_distribute_step(start, expected):
    r = engine.transform(engine.parse_problem(start)["id"], "distribute_step")
    assert r["latex"] == expected
    assert r["label"] == r"\text{distribute}"


def test_distribute_then_multiply_numbers():
    assert _steps("-2(x-3)=4", "!distribute_step", "!multiply")["latex"] == "- 2 x + 6 = 4"


def test_distribute_not_offered_for_a_plain_fraction():
    # (7-2x)/3 has nothing multiplying the bracket.
    r = engine.parse_problem("y=(7-2x)/3")
    assert engine.options(r["id"], "y")["distribute_step"] is False


@pytest.mark.parametrize(
    "start,expected",
    [
        ("6x+3", r"3 \left(2 x + 1\right)"),
        ("2x+4", r"2 \left(x + 2\right)"),
        ("-2x-4", r"- 2 \left(x + 2\right)"),
        ("ay+by", r"y \left(a + b\right)"),
        ("x^2+3x", r"x \left(x + 3\right)"),
        ("(8+2a)/4", r"\frac{2 \left(4 + a\right)}{4}"),
    ],
)
def test_factor_out(start, expected):
    r = engine.transform(engine.parse_problem(start)["id"], "factor_out")
    assert r["latex"] == expected
    assert r["label"] == r"\text{factor}"


def test_factor_only_pulls_out_a_common_factor():
    # No difference-of-squares or trinomial factoring, and nothing to pull out here.
    for text in ["x^2-1", "x^2+3x+2", "2x+3"]:
        assert engine.options(engine.parse_problem(text)["id"])["factor_out"] is False


def test_solve_for_y_by_factoring():
    r = _steps("ay+by=c", "!factor_out", "/(a+b)", "!cancel")
    assert r["latex"] == r"y = \frac{c}{a + b}"
    assert engine.options(r["id"], "y")["solved"] is True


def test_parse_lists_variables():
    assert engine.parse_problem("3y+2x=7")["variables"] == ["x", "y"]
    assert engine.parse_problem("2+3=5")["variables"] == []


@pytest.mark.parametrize(
    "text,target,solved",
    [
        ("y=(7-2x)/3", "y", True),
        ("(7-2x)/3=y", "y", True),
        ("y=7/3-2x/3", "y", True),
        ("y=6x/3", "y", False),  # cancel first
        ("y=2x+x", "y", False),  # combine first
        ("y=2y+1", "y", False),  # y on both sides
        ("x=7-3y", "y", False),  # solved for the wrong letter
        ("x=7-3y", "x", True),
        ("y=4", "y", True),
        ("y=4/2", "y", False),
    ],
)
def test_solved_for_a_chosen_variable(text, target, solved):
    r = engine.parse_problem(text)
    assert engine.options(r["id"], target)["solved"] is solved


def test_solve_for_y_start_to_finish():
    r = _steps("3y+2x=7", "-2x", "!combine", "/3", "!cancel")
    assert r["latex"] == r"y = \frac{7 - 2 x}{3}"
    assert engine.options(r["id"], "y")["solved"] is True


def test_highlight_colours_like_terms():
    r = _steps("3x-7=2x+5", "-2x")
    tex = engine.highlight(r["id"], "combine")
    assert tex.count(r"\color{#ff3fa4}") == 6  # 3x, -2x on each side (sign + term)
    assert "- 7" in tex and "+ 5" in tex  # lone terms stay plain


def test_highlight_strikes_cancelled_factors():
    tex = engine.highlight(_steps("6x=4", "/6")["id"], "cancel")
    assert tex.count(r"\cancel{6}") == 3  # 6x/6 twice, plus 4/6 -> 2/3
    assert r"\overset{2}{\cancel{4}}" in tex
    assert r"\underset{3}{\cancel{6}}" in tex


def test_highlight_keeps_subtraction_outside_the_fraction():
    tex = engine.highlight(engine.parse_problem("2x/2-6/3=1")["id"], "cancel")
    assert r"} - \frac{" in tex


def test_highlight_is_empty_when_nothing_to_show():
    r = engine.parse_problem("2x+1=5")
    assert engine.highlight(r["id"], "combine") == ""
    assert engine.highlight(r["id"], "cancel") == ""
    assert engine.highlight(r["id"], "multiply") == ""

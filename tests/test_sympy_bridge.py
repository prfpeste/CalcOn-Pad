"""Tests for mathlib/sympy_bridge.py (the eval-free AST->SymPy bridge).

Runs directly against ast_to_sympy() instead of only through
core.context.eval_line(), so a failure here points precisely at the
bridge itself rather than at some other spot in the larger evaluation
pipeline.
"""

import sympy as sp

from mathlib.sympy_bridge import ast_to_sympy
from parsing.parser import parse


def build(text, var_ns=None, user_vars=None, mode="numeric"):
    ast = parse(text)
    return ast_to_sympy(ast, var_ns or {}, user_vars or set(), mode)


class TestBasicArithmetic:
    def test_addition_and_precedence(self):
        assert build("2+3*4") == 14

    def test_power(self):
        assert build("2^10") == 1024

    def test_division_stays_exact(self):
        assert build("1/3") == sp.Rational(1, 3)

    def test_unary_minus(self):
        assert build("-5") == -5


class TestIdentifierResolution:
    def test_numeric_mode_resolves_assigned_variable(self):
        assert build("x", var_ns={"x": 7}) == 7

    def test_numeric_mode_unassigned_stays_symbolic(self):
        assert build("q") == sp.Symbol("q")

    def test_display_mode_uses_fresh_symbol_even_if_assigned(self):
        # Display mode should show the RAW FORMULA, not the value.
        result = build("L", var_ns={"L": 5}, user_vars={"L"}, mode="display")
        assert result == sp.Symbol("L")

    def test_known_constant_pi(self):
        assert build("π") == sp.pi

    def test_infinity_placeholder(self):
        assert build("__calcpad_infty__") == sp.oo

    def test_imaginary_placeholder(self):
        assert build("__calcpad_imag__") == sp.I


class TestFunctionWhitelist:
    def test_known_function_is_evaluated(self):
        assert build("sqrt(16)") == 4

    def test_unknown_function_becomes_symbolic_placeholder(self):
        result = build("banana(1,2)")
        assert result == sp.Function("banana")(1, 2)
        # Make sure this is REALLY just a placeholder -- not an
        # evaluated numeric value.
        assert not result.is_number

    def test_integrate_is_numeric_in_numeric_mode(self):
        x = sp.Symbol("x")
        result = build("integrate(x, x)", var_ns={"x": sp.Symbol("x")})
        assert result == x**2 / 2

    def test_integrate_stays_unevaluated_in_display_mode(self):
        result = build("integrate(x, x)", mode="display")
        assert isinstance(result, sp.Integral)


class TestQuantities:
    def test_simple_quantity(self):
        from sympy.physics.units import kilogram
        assert build("5'kg") == 5 * kilogram

    def test_degc_conversion(self):
        from sympy.physics.units import kelvin
        assert build("20'degC") == sp.Float("293.15") * kelvin

    def test_compound_unit(self):
        from sympy.physics.units import meter, second
        assert build("5'm/s") == 5 * meter / second


class TestListAndTupleLiterals:
    def test_bracket_list_becomes_python_list(self):
        assert build("[1,2,3]") == [1, 2, 3]

    def test_nested_bracket_list(self):
        assert build("[[1,2],[3,4]]") == [[1, 2], [3, 4]]

    def test_paren_comma_list_becomes_python_list(self):
        # e.g. "(x, 0, 5)" in integrate(f, (x,0,5))
        result = build("(1,2,3)")
        assert result == [1, 2, 3]

    def test_plain_parenthesized_expr_is_unaffected(self):
        # Without a comma, "(" stays a plain grouping, not a list literal.
        assert build("(2+3)*4") == 20

    def test_matrix_via_nested_list(self):
        result = build("mat([[1,2],[3,4]])")
        assert result == sp.Matrix([[1, 2], [3, 4]])


class TestSubscript:
    def test_list_indexing(self):
        assert build("lst[1]", var_ns={"lst": [10, 20, 30]}) == 20

    def test_chained_indexing(self):
        assert build("m[0][1]", var_ns={"m": [[1, 2], [3, 4]]}) == 2

    def test_matrix_indexing(self):
        M = sp.Matrix([[1, 2], [3, 4]])
        assert build("M[0]", var_ns={"M": M}) == 1

    def test_expression_as_index(self):
        assert build("lst[1+1]", var_ns={"lst": [10, 20, 30]}) == 30


class TestSecurityInvariant:
    def test_dunder_function_name_is_never_called(self):
        # "__import__" is not in the whitelist -> must stay a pure
        # placeholder, must NEVER actually be called.
        result = build("__import__(1)")
        assert result == sp.Function("__import__")(1)

    def test_eval_and_exec_are_not_whitelisted(self):
        assert build("eval(1)") == sp.Function("eval")(1)
        assert build("exec(1)") == sp.Function("exec")(1)

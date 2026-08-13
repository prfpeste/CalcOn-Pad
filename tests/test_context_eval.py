"""
Regression tests for the core pipeline (EvaluationContext.eval_line() ->
format_computation_result()).

Each test class corresponds to a concrete bug or feature fixed during
development. Goal: if a future change to core/context.py,
core/formatter.py, or mathlib/units.py breaks one of these already-fixed
cases again, it should show up IMMEDIATELY -- not only at the next
manual check by the user.
"""

import pytest
import sympy as sp


# ---------------------------------------------------------------------
# Crash fix: "5'kg + 3'kg" (two added unit literals)
# ---------------------------------------------------------------------
class TestAdditionOfTwoUnitLiterals:
    """The legacy text-based unit expansion used to scan past a second
    "'" as well as past "+"/"-" -> a broken reconstructed expression ->
    a SymPy token error ("unterminated string literal"). The whole line
    crashed instead of computing "8 kg"."""

    def test_does_not_raise(self, ctx, run):
        # Should not (or no longer) crash.
        run("5'kg + 3'kg", ctx)

    def test_correct_result(self, ctx, run_content):
        assert run_content("5'kg + 3'kg", ctx) == r"8\,\mathrm{kg}"

    def test_also_works_with_minus(self, ctx, run_content):
        # Same bug class, "-" instead of "+" as the boundary.
        assert run_content("5'kg - 3'kg", ctx) == r"2\,\mathrm{kg}"


# ---------------------------------------------------------------------
# Unary sign directly before a number + degC marker
# ---------------------------------------------------------------------
class TestUnaryMinusWithDegC:
    """"-7'degC" used to be treated as a binary operator and produced
    -280.15 K instead of the correct 266.15 K (-7 degC = 266.15 K)."""

    def test_bare_negative_degc_keeps_its_unit(self, ctx, run_content):
        # A bare literal assignment/line without "|unit": keeps the
        # entered unit, so no Kelvin conversion is shown here.
        assert run_content("-7'degC", ctx) == r"-7\,^\circ\mathrm{C}"

    def test_parenthesized_negative_degc_converts_correctly(self, ctx, run_content):
        # "(-7)'degC" was already computed CORRECTLY before the fix
        # (parenthesis tracking worked), only the formula DISPLAY was
        # broken.
        content = run_content("(-7)'degC", ctx)
        assert content == r"-7\,^\circ\mathrm{C} = 266.15\,\mathrm{K}"

    def test_unary_minus_matches_parenthesized_result(self, ctx):
        # Both spellings must lead to the same numeric value.
        _, _, _, _, val_unary, _ = ctx.eval_line("-7'degC")
        ctx2 = type(ctx)()
        _, _, _, _, val_paren, _ = ctx2.eval_line("(-7)'degC")
        assert sp.simplify(val_unary - val_paren) == 0


# ---------------------------------------------------------------------
# log() bug: the formula display disappeared for log(...)
# ---------------------------------------------------------------------
class TestLogFormulaDisplay:
    """The old eval-based display path injected an evaluate=False
    keyword for "log" that the custom _log_base_10() function didn't
    accept -> TypeError -> silent fallback -> only the result was shown,
    no input formula."""

    def test_formula_is_shown_alongside_result(self, ctx, run_content):
        content = run_content("log(1000)", ctx)
        assert content == r"\log\left(1000\right) = 3"

    def test_ln_still_works(self, ctx, run_content):
        # Regression guard for the related function (not part of the
        # actual bug, but the same code path family).
        content = run_content("ln(exp(2))", ctx)
        assert "=" in content
        assert content.endswith("2")


# ---------------------------------------------------------------------
# solve() bug: the formula display disappeared for solve(Eq(...)) + "|unit"
# ---------------------------------------------------------------------
class TestSolveFormulaDisplay:
    """Same bug class as the log() bug: solve(), a normal Python
    function, was actually EXECUTED while building the display form,
    producing a result with no free symbols -> the formula was wrongly
    suppressed. Fix: the decision is based on _is_bare_literal_input()
    (a plain text check on raw_expr) instead of on expr_sym/SymPy."""

    def test_formula_shown_for_solve_without_unit(self, ctx, run_content):
        content = run_content("x = solve(Eq(x^2 - 5*x + 6, 0), x)", ctx)
        assert content.startswith("x = ")
        assert "solve" in content or r"\operatorname{solve}" in content
        assert content.count("=") >= 2  # "x = <formula> = <result>"

    def test_eq_renders_as_equation_not_generic_call(self, ctx, run_content):
        # A bonus improvement in the same change: Eq(a, b) -> "a = b"
        # instead of \operatorname{Eq}(a, b).
        content = run_content("x = solve(Eq(x^2 - 5*x + 6, 0), x)", ctx)
        assert r"\operatorname{Eq}" not in content


# ---------------------------------------------------------------------
# Bare-literal assignment keeps the entered unit
# ---------------------------------------------------------------------
class TestBareLiteralKeepsEnteredUnit:
    """"110'degC" (or "x = 5'kN") used to automatically show the base-SI
    conversion (e.g. 5'kN -> 5000 N). Now: if no explicit "|unit" is
    given, the ENTERED unit is used as the desired_unit."""

    def test_assignment_with_degc_keeps_degc(self, ctx, run_content):
        assert run_content("T = 110'degC", ctx) == r"T = 110\,^\circ\mathrm{C}"

    def test_assignment_with_kilonewton_keeps_kilonewton(self, ctx, run_content):
        # Bonus side effect of the same change.
        assert run_content("x = 5'kN", ctx) == r"x = 5\,\mathrm{kN}"

    def test_bare_line_without_assignment_also_keeps_unit(self, ctx, run_content):
        assert run_content("110'degC", ctx) == r"110\,^\circ\mathrm{C}"

    def test_explicit_desired_unit_still_wins(self, ctx, run_content):
        # "|unit" still takes priority over automatically keeping the
        # entered unit.
        content = run_content("x = 5'kN | N", ctx)
        assert "N" in content
        assert "kN" not in content


# ---------------------------------------------------------------------
# pi/I collision and the same bug class (placeholders for ∞/i)
# ---------------------------------------------------------------------
class TestConstantVsUserVariableCollision:
    """The constant-override map (pi, I, oo, E -> \\pi, i, \\infty, e)
    used to collide with same-named user variables (e.g. "I" for
    electric current was wrongly rendered as the imaginary unit). Fix:
    overrides only apply to names that AREN'T a user's own variable
    (ctx.user_vars)."""

    def test_user_variable_i_is_not_rendered_as_imaginary_unit(self, ctx, run):
        run("I = 5", ctx)
        content = run("z = 3 + 2*I", ctx)["content"]
        # "I" (uppercase, user variable) must appear as the variable
        # "I", not as the imaginary unit "i".
        assert "2 \\cdot I" in content or "2I" in content
        assert content != r"z = 3 + 2 \cdot i = 3.0 + 2.0 i"

    def test_imaginary_literal_still_works_without_collision(self, ctx, run_content):
        # Without a user variable "I"/"ⅈ", the imaginary unit must still
        # render correctly as "i".
        content = run_content("z = 3 + 2*ⅈ", ctx)
        assert content == r"z = 3 + 2 \cdot i = 3.0 + 2.0 i"

    def test_infinity_placeholder_renders_as_infty_not_raw_text(self, ctx, run_content):
        # The __calcpad_infty__ placeholder (from normalize_identifiers())
        # was initially missing from the override map -> raw placeholder
        # text showed up in the formula instead of "\infty".
        content = run_content("a = 3 + 2*∞", ctx)
        assert "__calcpad" not in content
        assert r"\infty" in content


# ---------------------------------------------------------------------
# Comma-index variables (e.g. m_{x,1})
# ---------------------------------------------------------------------
class TestCommaIndexVariables:
    """Variable names with a comma-separated index used to collide with
    the function-argument separator syntax (SymPy interpreted "m_{x,1}"
    as a tuple). Fix: a dedicated mangling step in
    normalize_identifiers() converts it to a safe identifier before
    parsing."""

    def test_simple_comma_index_does_not_raise(self, ctx, run):
        run("m_{x,1} = 7", ctx)

    def test_multiple_comma_index_does_not_raise(self, ctx, run):
        run("T_{i,j,k} = 2", ctx)

    def test_comma_index_value_is_correct(self, ctx):
        var, *_ , val, _ = ctx.eval_line("m_{x,1} = 7")
        assert float(val) == pytest.approx(7)

    def test_comma_survives_in_rendered_subscript(self, ctx, run_content):
        content = run_content("m_{x,1} = 7", ctx)
        assert "x,1" in content


# ---------------------------------------------------------------------
# Bare unit names are NEVER auto-resolved anymore. The evaluation
# environment no longer injects unit names directly (only the "'"
# marker route resolves units). An unassigned identifier like "s" or
# "L" now behaves exactly like any other unknown variable (e.g. "q"):
# it stays symbolic instead of silently being interpreted as a unit.
# This was an explicit user request -- exactly the point of the "'"
# marker.
# ---------------------------------------------------------------------
class TestBareUnitNamesNeverAutoResolve:
    def test_undefined_normal_variable_stays_symbolic(self, ctx, run_content):
        # Reference behavior: this is how EVERY unknown variable should
        # behave -- including one that happens to be named like a unit.
        assert run_content("x = q * 5", ctx) == r"x = q \cdot 5 = 5 \cdot q"

    def test_undefined_unit_named_variable_now_behaves_the_same(self, ctx, run_content):
        # Before: "5 s" (silently interpreted as seconds). Now: stays
        # symbolic, exactly like "q" above -- no more special-casing for
        # names that happen to collide with a unit.
        assert run_content("x = s * 5", ctx) == r"x = s \cdot 5 = 5 \cdot s"

    @pytest.mark.parametrize("unit_name", ["L", "m", "s", "h", "N", "V", "A", "g", "min"])
    def test_assigned_variable_shadows_same_named_unit(self, ctx, unit_name):
        # Once a name has been explicitly assigned, the user variable
        # ALWAYS wins -- regardless of whether the name also happens to
        # be a unit. This was already the case before; what matters here
        # is that it STAYS the case now that units are no longer
        # injected blindly.
        ctx.eval_line(f"{unit_name} = 2")
        _, _, _, _, val, _ = ctx.eval_line(f"result = {unit_name} * 3")
        assert float(val) == pytest.approx(6)

    def test_l_times_b_regression_from_user_test_suite(self, ctx, run_content):
        # The original find: a test case from the user's test suite
        # (L = 2'm; B = 3'm; A_rect = L * B | m^2) already worked
        # correctly BEFORE this fix (L/B were assigned) -- this test
        # locks that in as a regression guard, independent of the fix
        # above.
        run_content("L = 2'm", ctx)
        run_content("B = 3'm", ctx)
        content = run_content("A_rect = L * B | m^2", ctx)
        assert content == r"A_{\text{rect}} = L \cdot B = 6\,\mathrm{m}^2"


# ---------------------------------------------------------------------
# Fix: "|unit" now also works WITHOUT an assignment on the same line
# (before: "|" splitting only happened in eval_line()'s assignment
# branch). This was the actually desired use case ("F | kN" as a pure
# display conversion of an already-assigned variable) -- it didn't work
# AT ALL before, not just the typo case was affected.
# ---------------------------------------------------------------------
class TestPipeUnitConversionWithoutAssignment:
    def test_previously_assigned_variable_can_be_converted_in_its_own_line(self, ctx, run_content):
        run_content("F = 5000'N", ctx)
        assert run_content("F | kN", ctx) == r"F = 5\,\mathrm{kN}"

    def test_undefined_variable_raises_clear_error_instead_of_crashing(self, ctx, run):
        # No previously defined "F": can't sensibly be converted to kN
        # (a symbolic value with no magnitude) -- this should still
        # fail, but with a clear error message instead of a raw
        # SympifyError/TokenError like before the fix.
        with pytest.raises(ValueError, match="not compatible"):
            run("F | kN", ctx)

    def test_still_works_for_a_plain_literal_without_prior_assignment(self, ctx, run_content):
        # Edge case: a plain numeric literal with "|unit", never
        # assigned -- already worked before (the bare_literal_unit_key
        # path was unaffected), included here only as a regression guard
        # for the rebuilt non-assignment branch of eval_line().
        assert run_content("5000'N | kN", ctx) == r"5\,\mathrm{kN}"


# ---------------------------------------------------------------------
# Fix: a value with a unit AND a real free symbol (e.g. "L*B" if "B"
# was never assigned) was rendered incorrectly. A pre-existing bug in
# split_magnitude_unit()/format_scalar_with_unit() that shows up more
# often after the "bare unit names no longer auto-resolve" fix above
# (undefined variables are now the normal case rather than an
# exception).
# ---------------------------------------------------------------------
class TestMixedUnitAndFreeSymbolValue:
    def test_quantity_times_undefined_symbol(self, ctx, run):
        run("L = 2'm", ctx)
        content = run("A = L*B", ctx)["content"]
        assert content == r"A = L \cdot B = 2\,\mathrm{m} \cdot B"

    def test_squared_quantity_times_undefined_symbol(self, ctx, run):
        run("L = 2'm", ctx)
        content = run("A = L^2 * B", ctx)["content"]
        assert content == r"A = L^{2} \cdot B = 4\,\mathrm{m}^{2} \cdot B"

    def test_pure_quantity_without_free_symbols_is_unaffected(self, ctx, run):
        # Regression guard: the most common case (just a number + unit,
        # no additional free symbol) must NOT change.
        run("L = 2'm", ctx)
        run("B = 3'm", ctx)
        content = run("A_rect = L * B | m^2", ctx)["content"]
        assert content == r"A_{\text{rect}} = L \cdot B = 6\,\mathrm{m}^2"


# ---------------------------------------------------------------------
# Regression from switching to the eval-free SymPy bridge (see
# mathlib/sympy_bridge.py): matrix methods (dot/cross/norm/det/trace/
# rank/inv/T/solve_linear/eigenvals/eigenvects) initially failed in
# DISPLAY mode, because user variables resolve to fresh symbols there
# instead of their real matrix value (see mathlib.sympy_bridge --
# display mode deliberately shows the raw formula, not the final
# result). Fix: the same try/except fallback as before the rewrite --
# if building the display form fails, the already-computed numeric
# value is reused for display too.
# ---------------------------------------------------------------------
class TestMatrixMethodsWorkDespiteDisplayModeFallback:
    def test_dot_product(self, ctx, run):
        run("v1 = vec(1, 2, 3)", ctx)
        run("v2 = vec(4, 5, 6)", ctx)
        content = run("dot(v1, v2)", ctx)["content"]
        assert "32" in content

    def test_determinant(self, ctx, run):
        run("M = mat([[1,2],[3,4]])", ctx)
        content = run("det(M)", ctx)["content"]
        assert "-2" in content

    def test_matrix_inverse_does_not_raise(self, ctx, run):
        run("N = Matrix([[1,2],[3,5]])", ctx)
        run("inv(N)", ctx)

    def test_eigenvals_does_not_raise(self, ctx, run):
        run("A_eig = Matrix([[2,0],[0,3]])", ctx)
        run("eigenvals(A_eig)", ctx)


# ---------------------------------------------------------------------
# Regression: parenthesized comma lists like "(i,1,5)" in
# sum(i,(i,1,5))/integrate(f,(x,0,π)) needed a grammar extension
# (parsing/parser.py -- "(" with a comma becomes a ListLiteral).
# ---------------------------------------------------------------------
class TestTupleArgumentsForSumIntegrate:
    def test_sum_with_tuple_bounds(self, ctx, run):
        content = run("sum(i,(i,1,5))", ctx)["content"]
        assert "15" in content

    def test_integrate_with_tuple_bounds(self, ctx, run):
        content = run("integrate(sin(x), (x, 0, π))", ctx)["content"]
        assert "2" in content


# ---------------------------------------------------------------------
# Regression: a number "0" with a unit ("0'J/kg") wrongly raised
# "Result is not compatible with the requested unit." SymPy simplifies
# "0 * unit" immediately to plain "0" (the unit "falls out"), so the
# compatibility check ALWAYS failed, even though "0" means the same
# trivial thing in any unit. Relevant e.g. for thermodynamic cycles
# where a step has exactly 0 work/heat.
# ---------------------------------------------------------------------
class TestZeroValueWithUnit:
    def test_zero_with_compound_unit(self, ctx, run_content):
        assert run_content("w_23=0'J/kg", ctx) == r"w_{\text{23}} = 0\,\frac{\mathrm{J}}{\mathrm{kg}}"

    def test_zero_with_simple_unit(self, ctx, run_content):
        assert run_content("F = 0'N", ctx) == r"F = 0\,\mathrm{N}"

    def test_zero_with_explicit_desired_unit(self, ctx, run_content):
        assert run_content("x = 0'kg | g", ctx) == r"x = 0\,\mathrm{g}"

    def test_nonzero_value_still_works_normally(self, ctx, run_content):
        # Regression guard: the normal case (a real value != 0) must not
        # change.
        assert run_content("w = 5'J/kg", ctx) == r"w = 5\,\frac{\mathrm{J}}{\mathrm{kg}}"

    def test_zero_as_degc_raises_clear_error(self, ctx, run):
        # degC has an AFFINE zero point (0 K != 0 degC) -- a unitless
        # "0" would be ambiguous here, deliberately stays an error
        # instead of making a (wrong) assumption.
        with pytest.raises(ValueError):
            run("x = 0 | degC", ctx)


# ---------------------------------------------------------------------
# Regression: "sol[0]" (indexing into a solve() result to pick one of
# several solutions) used to raise "Unexpected token 'LBRACKET'" --
# the grammar only supported "[...]" as a fresh list literal, not as
# postfix indexing into an existing expression. Fix: parsing/parser.py
# gained a postfix level between primary and power (see
# parse_postfix()), mathlib/sympy_bridge.py applies plain "[]" item
# access on the already-built value.
# ---------------------------------------------------------------------
class TestSubscriptIndexing:
    def test_picking_one_of_two_solve_results(self):
        from core.engine import evaluate_code

        code = (
            "eq := Eq(b + 6, 5.*b^2)\n"
            "sol_q = solve(eq, b)\n"
            "b_1 = sol_q[0] ; b_2 = sol_q[1]\n"
        )
        results = evaluate_code(code)
        rendered = str(results)
        assert "Error" not in rendered
        assert "-1" in rendered
        assert "1.2" in rendered

    def test_indexed_value_can_be_used_in_further_computation(self, ctx, run):
        run("sol_q = solve(Eq(b + 6, 5.*b^2), b)", ctx)
        run("b_1 = sol_q[0]", ctx)
        content = run("c = b_1 * 2", ctx)["content"]
        assert "-2" in content


# ---------------------------------------------------------------------
# Regression: "abs" was missing from mathlib.functions.COMMON_EVAL_FUNCTIONS
# (the function whitelist the security bridge -- mathlib/sympy_bridge.py --
# resolves calls against). Any name not in that whitelist becomes an
# inert, never-evaluated sp.Function(name)(...) placeholder (by design,
# see module docstring there) -- correct for genuinely unknown names,
# but "abs" is meant to actually run. Symptom: the raw value of a
# negative dimensional quantity stayed wrapped in an unevaluated
# "abs(...)" node instead of being reduced to its magnitude, and
# converting that node to a desired unit ("|MW") made SymPy's own
# dimension checker raise "input arguments for the function must be
# dimensionless" (it doesn't know how an arbitrary unrecognized
# Function propagates dimensions). Fix: map "abs" to sp.Abs in
# COMMON_EVAL_FUNCTIONS (shared by NUMERIC_FUNCTIONS/DISPLAY_FUNCTIONS/
# PLOT_FUNCTIONS), which SymPy's unit system already knows how to
# evaluate/convert.
# ---------------------------------------------------------------------
class TestAbsFunction:
    def test_abs_of_negative_dimensional_value_converts_to_desired_unit(self, ctx, run_content):
        run_content("w = -3411894.41004282'W", ctx)
        content = run_content("P = abs(w) |MW", ctx)
        assert "Error" not in content
        assert "3.4119" in content

    def test_abs_of_negative_dimensionless_value(self, ctx, run_content):
        run_content("x = -5", ctx)
        content = run_content("y = abs(x)", ctx)
        assert content.endswith("= 5")

    def test_abs_raw_formula_still_renders_as_abs(self, ctx, run_content):
        run_content("w = -3411894.41004282'W", ctx)
        content = run_content("P = abs(w) |MW", ctx)
        assert r"\operatorname{abs}" in content or r"\left|" in content


# ---------------------------------------------------------------------
# Regression: "tan" was missing from mathlib.functions.COMMON_EVAL_FUNCTIONS
# too, discovered during the audit that followed the "abs" fix above --
# same root cause, same fix pattern: the UI offers a "tan(x)" button
# (templates/index.html, Functions panel) but the name wasn't in the
# whitelist, so it silently stayed an unevaluated placeholder instead
# of actually computing the tangent.
# ---------------------------------------------------------------------
class TestTanFunction:
    def test_tan_is_actually_evaluated(self, ctx, run_content):
        content = run_content("y = tan(0)", ctx)
        assert content.endswith("= 0")

    def test_tan_matches_sin_over_cos(self, ctx, run_content):
        import math
        content = run_content("y = tan(1)", ctx)
        assert f"{math.tan(1):.4f}" in content

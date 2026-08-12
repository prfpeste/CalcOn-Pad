"""
Security regression tests.

Background: core/context.py originally evaluated numeric input via
sp.sympify(text, locals=env) -- which uses eval() internally. The
following input led to real code execution on the server:

    x = __import__(chr(111)+chr(115)).popen(chr(105)+chr(100)).read()
    -> returned "uid=0(root) gid=0(root) groups=0(root)"

Fix: core/context.py::eval_line() now builds expressions exclusively
via parsing.parser.parse() (our own, safe parser, no eval) +
mathlib.sympy_bridge.ast_to_sympy() (builds the SymPy tree node by
node, function calls only against a fixed whitelist). sympify()/
parse_expr() are no longer called anywhere on user input.

These tests are deliberately VERY concrete (real, historically
successful exploit payloads) rather than just checking "grammar
feature X is rejected" -- if someone in the future reintroduces an
eval()-based path (e.g. as a "quick fix" for a parser gap), this should
catch it immediately.
"""

import pytest

from core.context import EvaluationContext
from core.engine import evaluate_code


# ---------------------------------------------------------------------
# The original, actually successful exploit + variants
# ---------------------------------------------------------------------
class TestNoArbitraryCodeExecution:
    ORIGINAL_EXPLOIT = (
        "x = __import__(chr(111)+chr(115))"
        ".popen(chr(105)+chr(100)).read()"
    )

    RCE_PAYLOADS = [
        # The original exploit that actually worked during this session
        # (returned "uid=0(root)...").
        ORIGINAL_EXPLOIT,
        # Same idea with plain quotes (no chr() detour needed, in case
        # the "'" marker is ever handled differently).
        "x = __import__('os').popen('id').read()",
        # Classic Python sandbox escape via the class hierarchy.
        "x = ().__class__.__bases__[0].__subclasses__()",
        # Direct eval()/exec() call.
        "x = eval(chr(49))",
        "x = exec(chr(49))",
        # File access without import (phrased without getattr).
        "open(chr(47)+chr(101)+chr(116)+chr(99)+chr(47)+chr(112)+chr(97)"
        "+chr(115)+chr(115)+chr(119)+chr(100))",
        # Access to environment/process info.
        "x = globals()",
        "x = vars()",
        "x = getattr(chr(1), chr(2))",
    ]

    @pytest.mark.parametrize("payload", RCE_PAYLOADS)
    def test_payload_never_executes_real_python(self, payload):
        # It doesn't matter whether the line raises an error (because it
        # doesn't fit our grammar) or renders as a purely symbolic,
        # never-executed placeholder -- the only hard requirement is: no
        # trace of real code execution may show up (e.g. a UID/GID
        # output like the original exploit, or any other filesystem/
        # process content).
        results = evaluate_code(payload + "\n")
        rendered = str(results)

        assert "uid=" not in rendered
        assert "gid=" not in rendered
        assert "root" not in rendered

    def test_original_exploit_produces_no_shell_output(self):
        # The original exploit as an explicit standalone test (not just
        # parametrized) -- this is THE case that triggered this whole
        # change.
        results = evaluate_code(self.ORIGINAL_EXPLOIT + "\n")
        rendered = str(results)
        assert "uid=0(root)" not in rendered

    def test_unknown_function_becomes_inert_symbolic_placeholder(self):
        # An unknown function (not in NUMERIC_FUNCTIONS) must NEVER turn
        # into a real Python call -- it becomes a symbolic
        # sp.Function(name)(...) placeholder that never executes. This
        # is the central security invariant of the bridge (see
        # mathlib/sympy_bridge.py).
        ctx = EvaluationContext()
        _, _, _, expr_num, _, _ = ctx.eval_line("eval(1)")
        assert str(expr_num) == "eval(1)"
        assert not isinstance(expr_num, (int, float))

    def test_attribute_access_is_not_part_of_the_grammar(self):
        # "." (method call/attribute access, e.g. "().__class__") simply
        # isn't a token in the lexer -- this is the FIRST line of
        # defense, before the function whitelist even comes into play.
        # Expected: a clear error line, not a result like "1" (which
        # would be a successful .bit_length() call).
        results = evaluate_code("x = (1).bit_length()\n")
        rendered = str(results)
        assert "Error" in rendered

    def test_subscript_cannot_reach_attribute_access(self):
        # "[]" (added for picking a value out of a solve() result, e.g.
        # "sol[0]") is plain item access, never a way to reach "."
        # -- confirm the two don't combine into something exploitable.
        results = evaluate_code("x = ().__class__[0]\n")
        rendered = str(results)
        assert "Error" in rendered
        assert "uid=" not in rendered
        assert "root" not in rendered


# ---------------------------------------------------------------------
# The plot path (eval_plot_bound()/resolve_plot_expression()) was
# separately vulnerable -- its own regression tests.
# ---------------------------------------------------------------------
class TestPlotPathIsAlsoSafe:
    def test_malicious_plot_bound_does_not_execute(self):
        results = evaluate_code(
            "plot(x, x, __import__(chr(111)+chr(115)), 5)\n"
        )
        rendered = str(results)
        assert "uid=" not in rendered
        assert "root" not in rendered

    def test_malicious_plot_expression_does_not_execute(self):
        results = evaluate_code(
            "plot(__import__(chr(111)+chr(115)), x, -5, 5)\n"
        )
        rendered = str(results)
        assert "uid=" not in rendered
        assert "root" not in rendered


# ---------------------------------------------------------------------
# No more eval()/sympify() on user input -- static check.
# ---------------------------------------------------------------------
class TestNoSympifyOnUserInputRemains:
    def test_context_module_does_not_import_sympify_parsing(self):
        # sp.sympify()/parse_expr() must no longer be applied to RAW
        # USER TEXT anywhere in core/context.py. sp.sympify() itself may
        # of course still be importable (as a module attribute) -- what
        # matters is that it's never CALLED anymore.
        import inspect

        import core.context as context_module

        source = inspect.getsource(context_module)
        assert "sympify(" not in source
        assert "parse_expr(" not in source

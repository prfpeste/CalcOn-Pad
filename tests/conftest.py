import pytest

from core.context import EvaluationContext
from core.formatter import format_computation_result


@pytest.fixture
def ctx():
    """Fresh EvaluationContext per test (no shared state between tests)."""
    return EvaluationContext()


def eval_and_format(line: str, context: EvaluationContext, symbolic_only: bool = False) -> dict:
    """Runs a single CalcOnPad line end to end, exactly like
    core/engine.py would for a normal line: eval_line() ->
    format_computation_result(). Returns the resulting
    {"type": "latex", "content": ...} dict.

    Deliberately NOT a test of the Flask route (see test_app.py for a
    real HTTP smoke test), but the core pipeline at the Python level:
    fast, no server, but still "real" (no mocking).
    """
    var, raw, expr_sym, expr_num, val, desired_unit = context.eval_line(line)
    return format_computation_result(var, raw, expr_sym, val, desired_unit, symbolic_only, context)


def content_of(line: str, context: EvaluationContext, symbolic_only: bool = False) -> str:
    """Convenience wrapper: returns just the LaTeX content string."""
    return eval_and_format(line, context, symbolic_only)["content"]


@pytest.fixture
def run():
    """Fixture version of eval_and_format(), for tests that want to call
    the function directly as 'run(line, ctx)'."""
    return eval_and_format


@pytest.fixture
def run_content():
    """Fixture version of content_of()."""
    return content_of

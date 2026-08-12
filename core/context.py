from dataclasses import dataclass, field

import sympy as sp

from mathlib.functions import NUMERIC_FUNCTIONS
from mathlib.sympy_bridge import ast_to_sympy
from mathlib.units import (
    DESIRED_UNIT_MAP,
    bare_literal_unit_key,
    is_dimensionless_number,
    normalize_identifiers,
    normalize_numeric_quantity,
)
from parsing.parser import parse


def split_top_level(text: str, delimiter: str) -> list[str]:
    parts = []
    current = []
    depth = 0
    quote = None

    for char in text:
        if quote:
            current.append(char)
            if char == quote:
                quote = None
            continue

        if char == '"':
            current.append(char)
            quote = char
            continue

        if char in "([{":
            depth += 1
            current.append(char)
            continue

        if char in ")]}":
            depth = max(0, depth - 1)
            current.append(char)
            continue

        if char == delimiter and depth == 0:
            part = "".join(current).strip()
            if part:
                parts.append(part)
            current = []
            continue

        current.append(char)

    tail = "".join(current).strip()
    if tail:
        parts.append(tail)

    return parts


@dataclass
class EvaluationContext:
    var_ns: dict = field(default_factory=lambda: dict(NUMERIC_FUNCTIONS))
    user_vars: set = field(default_factory=set)
    sym_exprs: dict = field(default_factory=dict)

    def parse_assignment(self, rhs_raw: str):
        desired_unit = None

        if "|" in rhs_raw:
            rhs_core, desired_name = rhs_raw.split("|", 1)
            rhs_core = rhs_core.strip()
            desired_name = desired_name.strip()

            if desired_name:
                if desired_name not in DESIRED_UNIT_MAP:
                    raise ValueError(f"Unknown desired unit '{desired_name}'")
                desired_unit = DESIRED_UNIT_MAP[desired_name]

            return rhs_core, desired_unit

        return rhs_raw, desired_unit

    def eval_line(self, line: str):
        line = normalize_identifiers(line.strip())
        if not line:
            return None, None, None, None, None, None

        if "=" in line:
            var_part, rhs_part = line.split("=", 1)
            var_name = var_part.strip()
            rhs_core, desired_unit = self.parse_assignment(rhs_part.strip())

            if desired_unit is None:
                bare_unit_name = bare_literal_unit_key(rhs_core)
                if bare_unit_name is not None and bare_unit_name in DESIRED_UNIT_MAP:
                    desired_unit = DESIRED_UNIT_MAP[bare_unit_name]

            ast = parse(rhs_core)
            expr_num = ast_to_sympy(ast, self.var_ns, self.user_vars, mode="numeric")

            try:
                # Display mode can fail where numeric mode doesn't:
                # matrix methods like dot()/det()/inv() expect real
                # sp.Matrix objects, but display mode only provides fresh
                # symbols for user variables (see mathlib.sympy_bridge --
                # deliberate, so the "raw formula" shows variable names,
                # not their value). In that case just reuse the already-
                # computed value for display too, instead of failing the
                # whole line.
                expr_disp = ast_to_sympy(ast, self.var_ns, self.user_vars, mode="display")
            except Exception:
                expr_disp = expr_num

            value = normalize_numeric_quantity(expr_num)
            stored_value = is_dimensionless_number(value)

            self.var_ns[var_name] = value if stored_value is None else stored_value
            self.user_vars.add(var_name)
            self.sym_exprs[var_name] = expr_num

            return var_name, rhs_core, expr_disp, expr_num, value, desired_unit

        line_core, desired_unit = self.parse_assignment(line)

        ast = parse(line_core)
        expr_num = ast_to_sympy(ast, self.var_ns, self.user_vars, mode="numeric")
        value = normalize_numeric_quantity(expr_num)

        try:
            expr_disp = ast_to_sympy(ast, self.var_ns, self.user_vars, mode="display")
        except Exception:
            expr_disp = expr_num

        if desired_unit is None:
            bare_unit_name = bare_literal_unit_key(line_core)
            if bare_unit_name is not None and bare_unit_name in DESIRED_UNIT_MAP:
                desired_unit = DESIRED_UNIT_MAP[bare_unit_name]

        return None, line_core, expr_disp, expr_num, value, desired_unit

    def parse_plot_call(self, stripped: str):
        inner = stripped[5:-1]
        args = split_top_level(normalize_identifiers(inner), ",")
        if len(args) < 2:
            raise ValueError("plot(f, x, [xmin, xmax]) expected.")
        return args

    def eval_plot_bound(self, expr: str):
        ast = parse(normalize_identifiers(expr.strip()))
        return sp.N(ast_to_sympy(ast, self.var_ns, self.user_vars, mode="plot"))

    def resolve_plot_expression(self, expr_text: str):
        expr_text = normalize_identifiers(expr_text.strip())

        if expr_text in self.sym_exprs:
            return self.sym_exprs[expr_text]

        ast = parse(expr_text)
        return ast_to_sympy(ast, self.var_ns, self.user_vars, mode="plot")

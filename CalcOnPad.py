#!/usr/bin/env python3
# Flask-based symbolic calculator with unit support and simple plotting

import base64
import io
import re
import sys
import threading
import time
import webbrowser
from dataclasses import dataclass, field
from functools import lru_cache

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import sympy as sp
from flask import Flask, render_template, request
from sympy import latex
from sympy.parsing.sympy_parser import parse_expr
from sympy.physics.units import (
    A, J, K, L, N, Pa, R, V, W, atm, bar, cd, centi, hour, kg, km,
    liter, milli, minute, mol, m, ohm, s,
    convert_to as sympy_convert_to,
)

app = Flask(__name__)
sp.init_printing()

UNIT_TOKEN_PREFIX = "__unit_"
VAR_SYMBOL_PREFIX = "__varsym_"
BASE_UNITS = (m, kg, s, A, K, mol, cd)

DEFAULT_INPUT = (
    '"CalcOn Pad Version 1.0.1"\n'
    '"A simple tool to perform engineering calculations, based on Sympy"\n'
    "\n"
    '"Example:"\n'
    "a = 5'm/s^2 ; m = 10'kg\n"
    "F = m * a\n"
    "\n"
    '"by P.Stein - HTWG Konstanz"\n'
)

UNIT_NS = {
    "m": m,
    "mm": milli * m,
    "cm": centi * m,
    "km": km,

    "s": s,
    "ms": milli * s,
    "min": minute,
    "h": hour,

    "kg": kg,
    "g": milli * kg,
    "to": 1000 * kg,

    "N": N,
    "kN": 1000 * N,

    "J": J,
    "kJ": 1000 * J,
    "MJ": 1_000_000 * J,
    "GJ": 1_000_000_000 * J,

    "W": W,
    "kW": 1000 * W,
    "MW": 1_000_000 * W,
    "GW": 1_000_000_000 * W,

    "Pa": Pa,
    "kPa": 1000 * Pa,
    "MPa": 1_000_000 * Pa,
    "bar": bar,
    "atm": atm,

    "A": A,
    "V": V,
    "Ohm": ohm,

    "K": K,
    "degC": K,

    "mol": mol,
    "kmol": 1000 * mol,

    "cd": cd,

    "L": L,
    "liter": liter,

    "Hz": 1 / s,
    "rpm": 1 / minute,

    "deg": sp.pi / 180,
    "rad": 1,

    "R": R,

    "Ws": J,
    "Wh": 3600 * J,
    "kWh": 3_600_000 * J,
    "MWh": 3_600_000_000 * J,
}
UNIT_TOKEN_NS = {
    f"{UNIT_TOKEN_PREFIX}{name}": value
    for name, value in UNIT_NS.items()
}
UNIT_NAME_SET = frozenset(UNIT_NS.keys())
UNIT_VALUES = tuple(
    unit for unit in UNIT_NS.values()
    if unit != 1 and not unit.is_number
)

GREEK_VARS = {
    "α": r"\alpha", "β": r"\beta", "γ": r"\gamma", "δ": r"\delta",
    "ε": r"\epsilon", "ζ": r"\zeta", "η": r"\eta", "θ": r"\vartheta",
    "ι": r"\iota", "κ": r"\kappa", "λ": r"\lambda", "μ": r"\mu",
    "ν": r"\nu", "ξ": r"\xi", "π": r"\pi", "ρ": r"\rho",
    "σ": r"\sigma", "τ": r"\tau", "υ": r"\upsilon", "φ": r"\varphi",
    "χ": r"\chi", "ψ": r"\psi", "ω": r"\omega", "Γ": r"\Gamma",
    "Δ": r"\Delta", "Λ": r"\Lambda", "Θ": r"\Theta", "Ξ": r"\Xi",
    "Π": r"\Pi", "Σ": r"\Sigma", "Φ": r"\Phi", "Ψ": r"\Psi",
    "Ω": r"\Omega",
}

PRETTY_UNITS = (
    (bar, r"\mathrm{bar}"),
    (atm, r"\mathrm{atm}"),
    (1_000_000 * Pa, r"\mathrm{MPa}"),
    (1000 * Pa, r"\mathrm{kPa}"),
    (Pa, r"\mathrm{Pa}"),

    (1000 * N / (centi * m)**2, r"\frac{\mathrm{kN}}{\mathrm{cm}^{2}}"),
    (1000 * N / (m**2), r"\frac{\mathrm{kN}}{\mathrm{m}^{2}}"),
    (N / (milli * m)**2, r"\frac{\mathrm{N}}{\mathrm{mm}^{2}}"),
    (N / (centi * m)**2, r"\frac{\mathrm{N}}{\mathrm{cm}^{2}}"),
    (N / (m**2), r"\frac{\mathrm{N}}{\mathrm{m}^{2}}"),

    (1000 * N, r"\mathrm{kN}"),
    (N, r"\mathrm{N}"),

    (1_000_000_000 * J, r"\mathrm{GJ}"),
    (3_600_000_000 * J, r"\mathrm{MWh}"),
    (1_000_000 * J, r"\mathrm{MJ}"),
    (1000 * J, r"\mathrm{kJ}"),
    (J, r"\mathrm{J}"),

    (1_000_000_000 * W, r"\mathrm{GW}"),
    (1_000_000 * W, r"\mathrm{MW}"),
    (1000 * W, r"\mathrm{kW}"),
    (W, r"\mathrm{W}"),

    (km, r"\mathrm{km}"),
    (m, r"\mathrm{m}"),
    ((centi * m)**2, r"\mathrm{cm}^{2}"),
    ((milli * m)**2, r"\mathrm{mm}^{2}"),
    ((centi * m)**3, r"\mathrm{cm}^{3}"),
    ((milli * m)**3, r"\mathrm{mm}^{3}"),
    (centi * m, r"\mathrm{cm}"),
    (milli * m, r"\mathrm{mm}"),

    (hour, r"\mathrm{h}"),
    (minute, r"\mathrm{min}"),
    (s, r"\mathrm{s}"),
    (milli * s, r"\mathrm{ms}"),

    (1000 * kg, r"\mathrm{t}"),
    (kg, r"\mathrm{kg}"),
    (milli * kg, r"\mathrm{g}"),

    (1000 * mol, r"\mathrm{kmol}"),
    (mol, r"\mathrm{mol}"),

    (K, r"\mathrm{K}"),
    (V, r"\mathrm{V}"),
    (A, r"\mathrm{A}"),
    (ohm, r"\mathrm{\Omega}"),

    (1 / s, r"\mathrm{Hz}"),
    (1 / minute, r"\mathrm{rpm}"),

    (1000 * W / (m**2 * K), r"\frac{\mathrm{kW}}{\mathrm{m}^{2}\,\mathrm{K}}"),
    (W / (m**2 * K), r"\frac{\mathrm{W}}{\mathrm{m}^{2}\,\mathrm{K}}"),
    (1000 * W / (m * K), r"\frac{\mathrm{kW}}{\mathrm{m}\,\mathrm{K}}"),
    (W / (m * K), r"\frac{\mathrm{W}}{\mathrm{m}\,\mathrm{K}}"),

    (1000 * W / (m**2), r"\frac{\mathrm{kW}}{\mathrm{m}^{2}}"),
    (W / (m**2), r"\frac{\mathrm{W}}{\mathrm{m}^{2}}"),
    (W / m, r"\frac{\mathrm{W}}{\mathrm{m}}"),

    (1000 * J / (kg * K), r"\frac{\mathrm{kJ}}{\mathrm{kg}\,\mathrm{K}}"),
    (J / (kg * K), r"\frac{\mathrm{J}}{\mathrm{kg}\,\mathrm{K}}"),
    (1000 * J / mol, r"\frac{\mathrm{kJ}}{\mathrm{mol}}"),
    (J / mol, r"\frac{\mathrm{J}}{\mathrm{mol}}"),

    (1000 * J / kg, r"\frac{\mathrm{kJ}}{\mathrm{kg}}"),
    (J / kg, r"\frac{\mathrm{J}}{\mathrm{kg}}"),

    (3_600_000 * J / kg, r"\frac{\mathrm{kWh}}{\mathrm{kg}}"),
    (3600 * J / kg, r"\frac{\mathrm{Wh}}{\mathrm{kg}}"),
    (3_600_000 * J / (kg * K), r"\frac{\mathrm{kWh}}{\mathrm{kg}\,\mathrm{K}}"),
    (3600 * J / (kg * K), r"\frac{\mathrm{Wh}}{\mathrm{kg}\,\mathrm{K}}"),

    (1000 * J / (m**3), r"\frac{\mathrm{kJ}}{\mathrm{m}^{3}}"),
    (J / (m**3), r"\frac{\mathrm{J}}{\mathrm{m}^{3}}"),
    (3_600_000 * J / (m**3), r"\frac{\mathrm{kWh}}{\mathrm{m}^{3}}"),
    (3600 * J / (m**3), r"\frac{\mathrm{Wh}}{\mathrm{m}^{3}}"),

    (m**2 / s, r"\frac{\mathrm{m}^{2}}{\mathrm{s}}"),
    (m**2, r"\mathrm{m}^{2}"),
    (m**3, r"\mathrm{m}^{3}"),
)

DESIRED_UNIT_MAP = {
    "m": (r"\mathrm{m}", m, 1),
    "mm": (r"\mathrm{mm}", m, 0.001),
    "cm": (r"\mathrm{cm}", m, 0.01),
    "km": (r"\mathrm{km}", m, 1000),

    "m^2": (r"\mathrm{m}^2", m**2, 1),
    "cm^2": (r"\mathrm{cm}^2", m**2, 0.0001),
    "mm^2": (r"\mathrm{mm}^2", m**2, 0.000001),

    "m^3": (r"\mathrm{m}^3", m**3, 1),
    "cm^3": (r"\mathrm{cm}^3", m**3, 0.000001),
    "mm^3": (r"\mathrm{mm}^3", m**3, 0.000000001),

    "s": (r"\mathrm{s}", s, 1),
    "ms": (r"\mathrm{ms}", s, 0.001),
    "min": (r"\mathrm{min}", s, 60),
    "h": (r"\mathrm{h}", s, 3600),

    "kg": (r"\mathrm{kg}", kg, 1),
    "g": (r"\mathrm{g}", kg, 0.001),
    "to": (r"\mathrm{t}", kg, 1000),

    "mol": (r"\mathrm{mol}", mol, 1),
    "kmol": (r"\mathrm{kmol}", mol, 1000),

    "N": (r"\mathrm{N}", N, 1),
    "kN": (r"\mathrm{kN}", N, 1000),

    "N/m^2": (r"\frac{\mathrm{N}}{\mathrm{m}^{2}}", Pa, 1),
    "N/cm^2": (r"\frac{\mathrm{N}}{\mathrm{cm}^{2}}", Pa, 10_000),
    "N/mm^2": (r"\frac{\mathrm{N}}{\mathrm{mm}^{2}}", Pa, 1_000_000),
    "kN/m^2": (r"\frac{\mathrm{kN}}{\mathrm{m}^{2}}", Pa, 1000),
    "kN/cm^2": (r"\frac{\mathrm{kN}}{\mathrm{cm}^{2}}", Pa, 10_000_000),

    "J": (r"\mathrm{J}", J, 1),
    "kJ": (r"\mathrm{kJ}", J, 1000),
    "MJ": (r"\mathrm{MJ}", J, 1_000_000),
    "GJ": (r"\mathrm{GJ}", J, 1_000_000_000),

    "Ws": (r"\mathrm{Ws}", J, 1),
    "Wh": (r"\mathrm{Wh}", J, 3600),
    "kWh": (r"\mathrm{kWh}", J, 3_600_000),
    "MWh": (r"\mathrm{MWh}", J, 3_600_000_000),

    "W": (r"\mathrm{W}", W, 1),
    "kW": (r"\mathrm{kW}", W, 1000),
    "MW": (r"\mathrm{MW}", W, 1_000_000),
    "GW": (r"\mathrm{GW}", W, 1_000_000_000),

    "Pa": (r"\mathrm{Pa}", Pa, 1),
    "kPa": (r"\mathrm{kPa}", Pa, 1000),
    "MPa": (r"\mathrm{MPa}", Pa, 1_000_000),
    "bar": (r"\mathrm{bar}", Pa, 100_000),
    "atm": (r"\mathrm{atm}", Pa, 101325),

    "K": (r"\mathrm{K}", K, 1),
    "degC": (r"^\circ\mathrm{C}", K, 1),

    "Hz": (r"\mathrm{Hz}", 1 / s, 1),
    "rpm": (r"\mathrm{rpm}", 1 / s, sp.Rational(1, 60)),
    "deg": (r"^\circ", 1, sp.pi / 180),
    "rad": (r"\mathrm{rad}", 1, 1),

    "W/(m^2*K)": (r"\frac{\mathrm{W}}{\mathrm{m}^{2}\,\mathrm{K}}", W / (m**2 * K), 1),
    "kW/(m^2*K)": (r"\frac{\mathrm{kW}}{\mathrm{m}^{2}\,\mathrm{K}}", W / (m**2 * K), 1000),

    "W/(m*K)": (r"\frac{\mathrm{W}}{\mathrm{m}\,\mathrm{K}}", W / (m * K), 1),
    "kW/(m*K)": (r"\frac{\mathrm{kW}}{\mathrm{m}\,\mathrm{K}}", W / (m * K), 1000),

    "W/m": (r"\frac{\mathrm{W}}{\mathrm{m}}", W / m, 1),
    "W/m^2": (r"\frac{\mathrm{W}}{\mathrm{m}^{2}}", W / (m**2), 1),
    "kW/m^2": (r"\frac{\mathrm{kW}}{\mathrm{m}^{2}}", W / (m**2), 1000),

    "J/(kg*K)": (r"\frac{\mathrm{J}}{\mathrm{kg}\,\mathrm{K}}", J / (kg * K), 1),
    "kJ/(kg*K)": (r"\frac{\mathrm{kJ}}{\mathrm{kg}\,\mathrm{K}}", J / (kg * K), 1000),
    "Wh/(kg*K)": (r"\frac{\mathrm{Wh}}{\mathrm{kg}\,\mathrm{K}}", J / (kg * K), 3600),
    "kWh/(kg*K)": (r"\frac{\mathrm{kWh}}{\mathrm{kg}\,\mathrm{K}}", J / (kg * K), 3_600_000),

    "J/kg": (r"\frac{\mathrm{J}}{\mathrm{kg}}", J / kg, 1),
    "kJ/kg": (r"\frac{\mathrm{kJ}}{\mathrm{kg}}", J / kg, 1000),
    "Wh/kg": (r"\frac{\mathrm{Wh}}{\mathrm{kg}}", J / kg, 3600),
    "kWh/kg": (r"\frac{\mathrm{kWh}}{\mathrm{kg}}", J / kg, 3_600_000),

    "J/mol": (r"\frac{\mathrm{J}}{\mathrm{mol}}", J / mol, 1),
    "kJ/mol": (r"\frac{\mathrm{kJ}}{\mathrm{mol}}", J / mol, 1000),

    "J/m^3": (r"\frac{\mathrm{J}}{\mathrm{m}^{3}}", J / (m**3), 1),
    "kJ/m^3": (r"\frac{\mathrm{kJ}}{\mathrm{m}^{3}}", J / (m**3), 1000),
    "Wh/m^3": (r"\frac{\mathrm{Wh}}{\mathrm{m}^{3}}", J / (m**3), 3600),
    "kWh/m^3": (r"\frac{\mathrm{kWh}}{\mathrm{m}^{3}}", J / (m**3), 3_600_000),
}

UNIT_NAMES_REGEX = "|".join(sorted((re.escape(name) for name in UNIT_NS), key=len, reverse=True))
UNIT_PATTERN = re.compile(
    rf"(?P<num>\d+(\.\d+)?|\b\w+\b)\s*'(?P<unit>{UNIT_NAMES_REGEX})"
)


def my_solve(*args, **kwargs):
    result = sp.solve(*args, **kwargs)
    if isinstance(result, list) and len(result) == 1 and not isinstance(result[0], dict):
        return result[0]
    return result


def _log_base_10(x, b=10):
    return sp.log(x, b)


def _vec(*args):
    return sp.Matrix(args)


def _transpose(matrix):
    return matrix.T


def _det(matrix):
    return matrix.det()


def _inv(matrix):
    return matrix.inv()


def _dot(a, b):
    return a.dot(b)


def _cross(a, b):
    return a.cross(b)


def _norm(a):
    return a.norm()


def _solve_linear(A, b):
    return A.LUsolve(b)


def _rank(A):
    return sp.Integer(A.rank())


def _trace(A):
    return A.trace()


COMMON_EVAL_FUNCTIONS = {
    "sp": sp,
    "π": sp.pi,
    "pi": sp.pi,
    "__calcpad_infty__": sp.oo,
    "__calcpad_imag__": sp.I,
    "sin": sp.sin,
    "cos": sp.cos,
    "asin": sp.asin,
    "acos": sp.acos,
    "atan": sp.atan,
    "atan2": sp.atan2,
    "sinh": sp.sinh,
    "cosh": sp.cosh,
    "tanh": sp.tanh,
    "asinh": sp.asinh,
    "acosh": sp.acosh,
    "atanh": sp.atanh,
    "exp": sp.exp,
    "ln": sp.log,
    "log": _log_base_10,
    "sqrt": sp.sqrt,
    "symbols": sp.symbols,
    "Eq": sp.Eq,
    "solve": my_solve,
    "nsolve": sp.nsolve,
    "vec": _vec,
    "mat": sp.Matrix,
    "eye": sp.eye,
    "zeros": sp.zeros,
    "ones": sp.ones,
    "det": _det,
    "inv": _inv,
    "T": _transpose,
    "dot": _dot,
    "cross": _cross,
    "norm": _norm,
    "solve_linear": _solve_linear,
    "eigenvals": lambda A: A.eigenvals(),
    "eigenvects": lambda A: A.eigenvects(),
    "rank": _rank,
    "trace": _trace,
}

NUMERIC_FUNCTIONS = {
    **COMMON_EVAL_FUNCTIONS,
    "integrate": sp.integrate,
    "diff": sp.diff,
    "sum": sp.summation,
    "summe": sp.summation,
    "prod": sp.product,
    "produkt": sp.product,
    "lim": sp.limit,
    "x": sp.Symbol("x"),
    "y": sp.Symbol("y"),
    "t_sym": sp.Symbol("t"),
}

DISPLAY_FUNCTIONS = {
    **COMMON_EVAL_FUNCTIONS,
    "integrate": sp.Integral,
    "diff": sp.Derivative,
    "sum": sp.Sum,
    "summe": sp.Sum,
    "prod": sp.Product,
    "produkt": sp.Product,
    "lim": sp.Limit,
    "x": sp.Symbol("x"),
    "y": sp.Symbol("y"),
    "t_sym": sp.Symbol("t"),
}

PLOT_FUNCTIONS = {
    **COMMON_EVAL_FUNCTIONS,
    "integrate": sp.Integral,
    "diff": sp.Derivative,
    "sum": sp.Sum,
    "summe": sp.Sum,
    "prod": sp.Product,
    "produkt": sp.Product,
    "lim": sp.Limit,
    "x": sp.Symbol("x"),
    "y": sp.Symbol("y"),
    "t_sym": sp.Symbol("t"),
}


def normalize_identifiers(text: str) -> str:
    return (
        text.replace("ϑ", "θ")
            .replace("∞", "__calcpad_infty__")
            .replace("ⅈ", "__calcpad_imag__")
    )


def normalize_power_ops(expr: str) -> str:
    return expr.replace("^", "**") if "^" in expr else expr


def _replace_unit_names_in_expr(unit_expr: str) -> str:
    result = []
    i = 0
    n = len(unit_expr)

    while i < n:
        ch = unit_expr[i]

        if ch.isalpha() or ch == "_":
            j = i + 1
            while j < n and (unit_expr[j].isalnum() or unit_expr[j] == "_"):
                j += 1

            name = unit_expr[i:j]
            if name not in UNIT_NS:
                raise ValueError(f"Unknown unit '{name}'")

            result.append(f"{UNIT_TOKEN_PREFIX}{name}")
            i = j
            continue

        if ch == "^":
            result.append("**")
        else:
            result.append(ch)

        i += 1

    return "".join(result)
    

def expand_units(expr: str) -> str:
    result = []
    i = 0
    n = len(expr)

    while i < n:
        ch = expr[i]

        if ch != "'":
            result.append(ch)
            i += 1
            continue

        if not result:
            raise ValueError("Missing magnitude before unit marker \"'\".")

        j = i + 1
        depth = 0

        while j < n:
            c = expr[j]

            if c == "(":
                depth += 1
            elif c == ")":
                if depth == 0:
                    break
                depth -= 1
            elif depth == 0 and c in ";=,":
                break
            elif depth == 0 and c.isspace():
                k = j
                while k < n and expr[k].isspace():
                    k += 1
                if k >= n or expr[k] in ";=,":
                    break

            j += 1

        unit_expr = expr[i + 1:j].strip()
        if not unit_expr:
            raise ValueError("Missing unit after unit marker \"'\".")

        if unit_expr == "degC":
            # linken Operanden vor dem Apostroph zurückholen
            left = []
            k = len(result) - 1
            paren_depth = 0

            while k >= 0:
                c = result[k]

                if c == ")":
                    paren_depth += 1
                elif c == "(":
                    paren_depth -= 1

                if paren_depth == 0 and c in "=;,":
                    break

                if paren_depth == 0 and c in "+-*/":
                    break

                left.append(c)
                k -= 1

            left_expr = "".join(reversed(left)).strip()
            if not left_expr:
                raise ValueError("Missing magnitude before unit marker \"'degC\".")

            del result[k + 1:]
            result.append(f"(({left_expr}) + 273.15) * {UNIT_TOKEN_PREFIX}K")
        else:
            unit_expr = _replace_unit_names_in_expr(unit_expr)
            result.append(f" * ({unit_expr})")

        i = j

    return "".join(result)


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


@lru_cache(maxsize=4096)
def _convert_to_cached(expr, frozen_target):
    real_target = list(frozen_target) if isinstance(frozen_target, tuple) else frozen_target
    return sympy_convert_to(expr, real_target)


def freeze_target(target):
    return tuple(target) if isinstance(target, list) else target


def convert_to_cached(expr, target):
    return _convert_to_cached(expr, freeze_target(target))



@lru_cache(maxsize=4096)
def _expr_to_latex_cached(expr, user_vars_key):
    symbol_names = {}
    free_symbols = getattr(expr, "free_symbols", set())

    for sym in free_symbols:
        if sym in UNIT_VALUES:
            continue
        sym_name = str(sym)
        if sym_name.startswith(VAR_SYMBOL_PREFIX):
            sym_name = sym_name[len(VAR_SYMBOL_PREFIX):]
        symbol_names[sym] = var_to_latex(sym_name)

    for name in user_vars_key:
        sym = sp.Symbol(name)
        if sym not in UNIT_VALUES:
            symbol_names[sym] = var_to_latex(name)

    return latex(
        expr,
        mul_symbol=r"\cdot",
        symbol_names=symbol_names,
    ).replace(r"\cdot", r"\cdot{}")


def expr_to_latex(expr, user_vars):
    return _expr_to_latex_cached(expr, tuple(sorted(user_vars)))


def split_magnitude_unit(expr):
    if not hasattr(expr, "has") or not expr.has(*UNIT_VALUES):
        return expr, 1

    if isinstance(expr, sp.Mul):
        mag_factors = []
        unit_factors = []
        for factor in expr.args:
            if factor.has(*UNIT_VALUES):
                unit_factors.append(factor)
            else:
                mag_factors.append(factor)
        magnitude = sp.Mul(*mag_factors) if mag_factors else 1
        unit = sp.Mul(*unit_factors) if unit_factors else 1
        return magnitude, unit

    return 1, expr


def format_magnitude_decimal(mag, rel_tol=1e-4):
    try:
        mag_num = sp.N(mag)
    except Exception:
        mag_num = mag

    if getattr(mag_num, "is_real", False):
        try:
            value = float(mag_num)

            if value == 0:
                return "0"

            absval = abs(value)

            use_sci = absval < 1e-3 or absval >= 1e4

            sig_digits = max(1, int(sp.ceiling(-sp.log(rel_tol, 10))))

            if use_sci:
                sci = f"{value:.{sig_digits - 1}e}"
                base, exp = sci.split("e")
                base = base.rstrip("0").rstrip(".")
                exp_int = int(exp)
                return rf"{base}\cdot 10^{{{exp_int}}}"

            decimals = max(0, sig_digits - 1 - int(sp.floor(sp.log(absval, 10))))
            fixed = f"{value:.{decimals}f}".rstrip("0").rstrip(".")

            return "0" if fixed in {"-0", "-0.0", ""} else fixed

        except Exception:
            pass

    return latex(mag)

def format_scalar_with_unit(expr):
    try:
        value_for_output = convert_to_cached(expr, BASE_UNITS)
    except Exception:
        value_for_output = expr

    mag, unit = split_magnitude_unit(value_for_output)
    mag_str = format_magnitude_decimal(mag)

    try:
        unit_simpl = convert_to_cached(unit, BASE_UNITS)
    except Exception:
        unit_simpl = unit

    if unit == 1 or not getattr(unit_simpl, "has", lambda *args: False)(*UNIT_VALUES):
        return mag_str

    return rf"{mag_str}\,{unit_to_pretty_latex(unit)}"

def var_to_latex(var_name: str) -> str:
    if var_name.startswith(VAR_SYMBOL_PREFIX):
        var_name = var_name[len(VAR_SYMBOL_PREFIX):]

    var_name = normalize_identifiers(var_name)

    if var_name.startswith("Δ") and "_" not in var_name:
        base = var_name[1:]
        if base in GREEK_VARS:
            return r"\Delta" + GREEK_VARS[base]

    if "_" not in var_name:
        return GREEK_VARS.get(var_name, var_name)

    base, index = var_name.split("_", 1)
    base = normalize_identifiers(base)
    index = normalize_identifiers(index)

    if base.startswith("Δ") and base[1:] in GREEK_VARS:
        base_latex = r"\Delta" + GREEK_VARS[base[1:]]
    else:
        base_latex = GREEK_VARS.get(base, base)

    if index in GREEK_VARS:
        return rf"{base_latex}{GREEK_VARS[index]}"

    if "_" in index:
        index_base, index_suffix = index.split("_", 1)
        index_base = normalize_identifiers(index_base)
        index_base_latex = GREEK_VARS.get(index_base, index_base)
        safe_suffix = index_suffix.replace("\\", r"\\").replace("_", r"\_")
        return rf"{base_latex}{index_base_latex}_{{\text{{{safe_suffix}}}}}"

    safe_index = index.replace("\\", r"\\").replace("_", r"\_")
    return rf"{base_latex}_{{\text{{{safe_index}}}}}"


def has_only_units_and_numbers(expr):
    free_symbols = getattr(expr, "free_symbols", set())
    return all(sym in UNIT_VALUES for sym in free_symbols)


def unit_to_pretty_latex(unit):
    for candidate, latex_str in PRETTY_UNITS:
        try:
            ratio = convert_to_cached(unit / candidate, BASE_UNITS)
            if not ratio.has(*UNIT_VALUES) and ratio == 1:
                return latex_str
        except Exception:
            continue

    try:
        unit_base = convert_to_cached(unit, BASE_UNITS)
    except Exception:
        unit_base = unit
    return latex(unit_base)


def is_dimensionless_number(val):
    try:
        val_simpl = convert_to_cached(val, BASE_UNITS)
    except Exception:
        val_simpl = val

    if isinstance(val_simpl, (list, tuple, dict)):
        return None

    mag, unit = split_magnitude_unit(val_simpl)
    if unit != 1:
        return None
    if bool(getattr(mag, "is_number", False)):
        return sp.N(mag)
    return None


def make_safe_text_latex(text: str) -> str:
    return text.replace("\\", r"\\").replace("_", r"\_")


def error_to_latex(prefix: str, exc: Exception) -> str:
    safe = f"{prefix} -- {exc}".replace("\\", r"\\").replace("_", r"\_")
    return rf"\text{{{safe}}}"


@dataclass
class EvaluationContext:
    var_ns: dict = field(default_factory=lambda: dict(NUMERIC_FUNCTIONS))
    user_vars: set = field(default_factory=set)
    sym_exprs: dict = field(default_factory=dict)

    def make_eval_env(self, mode: str = "numeric") -> dict:
        if mode == "numeric":
            base = NUMERIC_FUNCTIONS
        elif mode == "display":
            base = DISPLAY_FUNCTIONS
        elif mode == "plot":
            base = PLOT_FUNCTIONS
        else:
            raise ValueError(f"Unknown mode: {mode}")

        env = {}
        env.update(UNIT_NS)
        env.update(UNIT_TOKEN_NS)
        env.update(base)

        if mode == "numeric":
            env.update(self.var_ns)
        else:
            for name in self.user_vars:
                if name == "sol":
                    continue
                env[name] = sp.Symbol(name)

        for name in UNIT_NS:
            token = f"{VAR_SYMBOL_PREFIX}{name}"
            env[token] = sp.Symbol(token)

        return env

    def protect_assigned_unit_name(self, rhs: str, var_name: str, env: dict) -> str:
        if var_name not in UNIT_NS:
            return rhs

        token = f"{VAR_SYMBOL_PREFIX}{var_name}"
        env[token] = sp.Symbol(token)

        return re.sub(
            rf"(?<=\(|,)\s*{re.escape(var_name)}\s*(?=,|\))",
            token,
            rhs,
        )

    def prepare_expression(self, expr: str) -> str:
        prepared = normalize_identifiers(expr.strip())
        prepared = normalize_power_ops(prepared)
        prepared = expand_units(prepared)
        return prepared

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
            return None, None, None, None, None

        env_num = self.make_eval_env("numeric")
        env_display = self.make_eval_env("display")

        if "=" in line:
            var_part, rhs_part = line.split("=", 1)
            var_name = var_part.strip()
            rhs_core, desired_unit = self.parse_assignment(rhs_part.strip())

            rhs_for_num = self.protect_assigned_unit_name(rhs_core, var_name, env_num)
            rhs_for_display = self.protect_assigned_unit_name(rhs_core, var_name, env_display)

            prepared_num = self.prepare_expression(rhs_for_num)
            prepared_display = self.prepare_expression(rhs_for_display)

            expr_num = sp.sympify(prepared_num, locals=env_num)
            try:
                expr_disp = parse_expr(prepared_display, local_dict=env_display, evaluate=False)
            except Exception:
                expr_disp = expr_num

            value = expr_num
            stored_value = is_dimensionless_number(value)
            self.var_ns[var_name] = value if stored_value is None else stored_value
            self.user_vars.add(var_name)
            self.sym_exprs[var_name] = expr_num

            return var_name, expr_disp, expr_num, value, desired_unit

        prepared_num = self.prepare_expression(line)
        expr_num = sp.sympify(prepared_num, locals=env_num)

        try:
            expr_disp = parse_expr(prepared_num, local_dict=env_display, evaluate=False)
        except Exception:
            expr_disp = expr_num

        return None, expr_disp, expr_num, expr_num, None

    def parse_plot_call(self, stripped: str):
        inner = stripped[5:-1]
        args = split_top_level(normalize_identifiers(inner), ",")
        if len(args) < 2:
            raise ValueError("plot(f, x, [xmin, xmax]) expected.")
        return args

    def eval_plot_bound(self, expr: str):
        env = self.make_eval_env("plot")
        prepared = self.prepare_expression(expr)
        return sp.N(sp.sympify(prepared, locals=env))

    def resolve_plot_expression(self, expr_text: str):
        expr_text = normalize_power_ops(normalize_identifiers(expr_text))
        if expr_text in self.sym_exprs:
            return self.sym_exprs[expr_text]

        env = self.make_eval_env("plot")
        prepared = self.prepare_expression(expr_text)
        return sp.sympify(prepared, locals=env)


def create_plot(expr_sym, var_symbol, x_min=-10, x_max=10, num_points=400):
    f_num = sp.lambdify(var_symbol, expr_sym, "numpy")
    xs = np.linspace(float(x_min), float(x_max), num_points)
    ys = f_num(xs)

    fig, ax = plt.subplots(figsize=(4, 3), dpi=100)
    ax.plot(xs, ys)
    ax.grid(True)
    ax.set_xlabel(str(var_symbol))
    ax.set_ylabel(f"f({var_symbol})")

    buf = io.BytesIO()
    fig.tight_layout()
    fig.savefig(buf, format="png")
    plt.close(fig)
    buf.seek(0)

    img_base64 = base64.b64encode(buf.read()).decode("ascii")
    return "data:image/png;base64," + img_base64


def render_plain_text_item(text: str) -> dict:
    if text.startswith("!"):
        return {"type": "latex", "content": text[1:]}
    return {"type": "latex", "content": rf"\text{{{make_safe_text_latex(text)}}}"}


def format_computation_result(var, expr_sym, val, desired_unit, symbolic_only, ctx: EvaluationContext):
    if isinstance(val, (list, tuple)) and not any(isinstance(x, (list, tuple, dict, sp.MatrixBase)) for x in val):
        latex_expr = r"\left[" + ", ".join(format_scalar_with_unit(x) for x in val) + r"\right]"
        if var is None:
            return {"type": "latex", "content": latex_expr}
        return {"type": "latex", "content": rf"{var_to_latex(var)} = {latex_expr}"}

    if isinstance(val, (dict, sp.MatrixBase)) or isinstance(expr_sym, (list, tuple, dict, sp.MatrixBase)):
        latex_expr = latex(val)
        if var is None:
            return {"type": "latex", "content": latex_expr}
        return {"type": "latex", "content": rf"{var_to_latex(var)} = {latex_expr}"}

    latex_expr = expr_to_latex(expr_sym, ctx.user_vars)

    if symbolic_only:
        if var is None:
            return {"type": "latex", "content": latex_expr}
        return {"type": "latex", "content": rf"{var_to_latex(var)} = {latex_expr}"}

    only_units_and_numbers = has_only_units_and_numbers(expr_sym)

    if desired_unit is not None:
        unit_label, base_unit, factor = desired_unit
        try:
            val_base = convert_to_cached(val, base_unit)
        except Exception as exc:
            raise ValueError(f"Conversion to desired unit failed: {exc}") from exc

        compat_check = convert_to_cached(val / base_unit, BASE_UNITS)
        if getattr(compat_check, "has", lambda *args: False)(*UNIT_VALUES):
            raise ValueError(
                f"Desired unit '{unit_label}' is not dimensionally compatible with the expression."
            )

        mag_base, _ = split_magnitude_unit(val_base)

        if base_unit == K and unit_label.startswith(r"^\circ"):
            mag = mag_base - 273.15
        else:
            mag = mag_base / factor

        mag_with_unit = rf"{format_magnitude_decimal(mag)}\,{unit_label}"
    else:
        try:
            value_for_output = convert_to_cached(val, BASE_UNITS)
        except Exception:
            value_for_output = val

        mag, unit = split_magnitude_unit(value_for_output)
        mag_str = format_magnitude_decimal(mag)

        try:
            unit_simpl = convert_to_cached(unit, BASE_UNITS)
        except Exception:
            unit_simpl = unit

        if unit == 1 or not unit_simpl.has(*UNIT_VALUES):
            mag_with_unit = mag_str
        else:
            mag_with_unit = rf"{mag_str}\,{unit_to_pretty_latex(unit)}"

    if var is None:
        return {"type": "latex", "content": rf"{latex_expr} = {mag_with_unit}"}

    var_latex = var_to_latex(var)
    if only_units_and_numbers:
        return {"type": "latex", "content": rf"{var_latex} = {mag_with_unit}"}
    return {"type": "latex", "content": rf"{var_latex} = {latex_expr} = {mag_with_unit}"}


def merge_latex_items(block_items):
    merged = []
    current_parts = []

    for item in block_items:
        if item["type"] == "latex":
            current_parts.append(item["content"])
            continue

        if current_parts:
            merged.append({"type": "latex", "content": r" \quad ".join(current_parts)})
            current_parts = []

        merged.append(item)

    if current_parts:
        merged.append({"type": "latex", "content": r" \quad ".join(current_parts)})

    return merged


def evaluate_code(user_input: str):
    ctx = EvaluationContext()
    results = []

    for line_no, raw_line in enumerate(user_input.splitlines(), start=1):
        parts = split_top_level(raw_line, ";")
        if not parts:
            results.append([{"type": "spacer"}])
            continue

        block_items = []

        for part in parts:
            stripped = part.strip()
            if not stripped or stripped.startswith("#"):
                continue

            if stripped.startswith('"') and stripped.endswith('"') and len(stripped) >= 2:
                block_items.append(render_plain_text_item(stripped[1:-1]))
                continue

            if stripped.startswith("plot(") and stripped.endswith(")"):
                try:
                    args = ctx.parse_plot_call(stripped)
                    func_expr = ctx.resolve_plot_expression(args[0])
                    var_symbol = sp.Symbol(normalize_identifiers(args[1]))
                    x_min = ctx.eval_plot_bound(args[2]) if len(args) >= 3 else -10
                    x_max = ctx.eval_plot_bound(args[3]) if len(args) >= 4 else 10
                    block_items.append({
                        "type": "plot",
                        "src": create_plot(func_expr, var_symbol, x_min, x_max),
                    })
                except Exception as exc:
                    block_items.append({
                        "type": "latex",
                        "content": rf"\text{{{make_safe_text_latex(f'Error while plotting: {exc}')}}}",
                    })
                continue

            try:
                symbolic_only = False
                line_for_eval = stripped
                if ":=" in stripped:
                    symbolic_only = True
                    line_for_eval = stripped.replace(":=", "=", 1)

                var, expr_sym, expr_num, val, desired_unit = ctx.eval_line(line_for_eval)
                if expr_sym is None or val is None:
                    continue

                block_items.append(
                    format_computation_result(
                        var=var,
                        expr_sym=expr_sym,
                        val=val,
                        desired_unit=desired_unit,
                        symbolic_only=symbolic_only,
                        ctx=ctx,
                    )
                )
            except Exception as exc:
                block_items.append({
                    "type": "latex",
                    "content": error_to_latex(f"Error in line {line_no}: {stripped}", exc),
                })

        if block_items:
            results.append(merge_latex_items(block_items))

    return results


@app.route("/", methods=["GET", "POST"])
def index():
    user_input = DEFAULT_INPUT
    results = []

    if request.method == "POST":
        user_input = request.form.get("code", "")
        results = evaluate_code(user_input)

    return render_template("index.html", code=user_input, results=results)


def run_server(open_browser: bool, debug: bool):
    if open_browser:
        def _run():
            app.run(host="127.0.0.1", port=5000, debug=debug)

        thread = threading.Thread(target=_run, daemon=True)
        thread.start()
        time.sleep(1)
        webbrowser.open("http://127.0.0.1:5000")
        thread.join()
    else:
        app.run(host="127.0.0.1", port=5000, debug=debug)


if __name__ == "__main__":
    frozen = getattr(sys, "frozen", False)
    if frozen:
        run_server(open_browser=True, debug=False)
    else:
        run_server(open_browser=False, debug=True)

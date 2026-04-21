#!/usr/bin/env python3
# Flask-based symbolic calculator with unit support and simple plotting

import threading
import webbrowser
import time
import re
import io
import base64
import os
import math


from flask import Flask, render_template, request

import sympy as sp
from sympy.physics.units import (
    m, s, kg, N, J, A, K, mol, cd,
    km, hour, minute, V, W, ohm,
    kilo,
    Pa, bar, atm,
    liter, L,
    R,
    convert_to,
)
from sympy import latex
from sympy.abc import alpha, beta, gamma, delta, lamda, epsilon, zeta, eta, theta, phi, psi, omega

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


def solve1(expr, var):
    sols = sp.solve(expr, var)
    if not sols:
        raise ValueError("No solution found")
    return sols[0]


app = Flask(__name__)
sp.init_printing()

# known units as names
unit_ns = {
    'm': m,
    's': s,
    'kg': kg,
    'N': N,
    'J': J,
    'A': A,
    'K': K,
    'mol': mol,
    'cd': cd,
    'km': km,
    'h': hour,
    'min': minute,
    'V': V,
    'W': W,
    'Ohm': ohm,
    'Pa': Pa,
    'bar': bar,
    'atm': atm,
    'L': L,
    'liter': liter,
    'R': R,
    'degC': K,
}

GREEK_VARS = {
    "alpha": r"\alpha",
    "beta": r"\beta",
    "gamma": r"\gamma",
    "delta": r"\delta",
    "Delta": r"\Delta",
    "lamda": r"\lambda",
    "epsilon": r"\epsilon",
    "zeta": r"\zeta",
    "eta": r"\eta",
    "theta": r"\vartheta",
    "phi": r"\varphi",
    "psi": r"\psi",
    "omega": r"\omega",
}

# environment for numeric evaluation
base_var_ns = {
    'sp': sp,
    'pi': sp.pi,
    'sin': sp.sin,
    'cos': sp.cos,
    'exp': sp.exp,
    'log': sp.log,
    'sqrt': sp.sqrt,
    'symbols': sp.symbols,
    'integrate': sp.integrate,
    'diff': sp.diff,
    'x': sp.symbols('x'),
    'y': sp.symbols('y'),
    't_sym': sp.symbols('t'),
    'Eq': sp.Eq,
    'solve': sp.solve,
    'solve1': solve1,
}
var_ns = dict(base_var_ns)
user_vars = set()
sym_exprs = {}
reserved_names = set(unit_ns.keys())

# preferred target units (if no explicit target unit is given)
preferred_units = [
    N,
    J,
    W,
    Pa, bar, atm,
    V, A, ohm,
]
BASE_UNITS = [m, kg, s, A, K, mol, cd]


# explicit desired units that can be specified via "| unit"
# structure: name: (name, base_unit, factor)
# factor = how many base units correspond to 1 of the desired unit
desired_unit_map = {
    "J":    (r"\mathrm{J}",    J,    1),
    "kJ":   (r"\mathrm{kJ}",   J,   1000),
    "MJ":   (r"\mathrm{MJ}",   J,   1_000_000),
    "Ws":   (r"\mathrm{Ws}",   J,    1),
    "Wh":   (r"\mathrm{Wh}",   J,    3600),
    "kWh":  (r"\mathrm{kWh}",  J,    3_600_000),
    "N":    (r"\mathrm{N}",    N,    1),
    "W":    (r"\mathrm{W}",    W,    1),
    "kW":   (r"\mathrm{kW}",   W,    1000),
    "MW":   (r"\mathrm{MW}",   W,    1_000_000),
    "Pa":   (r"\mathrm{Pa}",   Pa,   1),
    "bar":  (r"\mathrm{bar}",  Pa,   100_000),
    "m^2":  (r"\mathrm{m}^2",  m**2, 1),
    "cm^2": (r"\mathrm{cm}^2", m**2, 0.0001),
    "m^3":  (r"\mathrm{m}^3",  m**3, 1),
    "W/(m^2*K)": ( r"\frac{\mathrm{W}}{\mathrm{m}^{2}\,\mathrm{K}}", W/(m**2*K), 1),
    "W/(m*K)": (r"\frac{\mathrm{W}}{\mathrm{m}\,\mathrm{K}}", W/(m*K), 1),
    "J/(kg*K)": (r"\frac{\mathrm{J}}{\mathrm{kg}\,\mathrm{K}}", J/(kg*K), 1),
    "degC": (r"^\circ\mathrm{C}", K, 1),
}

# apostrophe syntax for units, e.g. 10'J, 3's, 5'm etc.
unit_names = "|".join(re.escape(u) for u in unit_ns.keys())
unit_pattern = re.compile(rf"(?P<num>\d+(\.\d+)?|\b\w+\b)\s*'(?P<unit>{unit_names})")


def expand_units(expr: str) -> str:
    def repl(m):
        num = m.group("num")
        unit = m.group("unit")
        if "." not in num:
            num = num + ".0"
        if unit == "degC":
            return f"({num} + 273.15) * K"
        return f"{num} * {unit}"

    return unit_pattern.sub(repl, expr)


def split_magnitude_unit(expr):
    expr = sp.simplify(expr)

    if not expr.has(*unit_ns.values()):
        return expr, 1

    if isinstance(expr, sp.Mul):
        mag_factors = []
        unit_factors = []
        for f in expr.args:
            if f.has(*unit_ns.values()):
                unit_factors.append(f)
            else:
                mag_factors.append(f)
        mag = sp.Mul(*mag_factors) if mag_factors else 1
        unit = sp.Mul(*unit_factors) if unit_factors else 1
        return mag, unit

    return 1, expr


def format_magnitude_decimal(mag, digits=3):
    try:
        mag_num = sp.N(mag)
    except Exception:
        mag_num = mag

    if mag_num.is_real:
        try:
            fval = float(mag_num)
            s = f"{fval:.{digits}f}"
            s = s.rstrip('0').rstrip('.')
            return s
        except Exception:
            pass

    return latex(mag)



def var_to_latex(var_name: str) -> str:
    # greek variable names without index
    if '_' not in var_name:
        if var_name in GREEK_VARS:
            return GREEK_VARS[var_name]
        return var_name

    # variable names with index, e.g. phi_1, alpha_tot, delta_theta, delta_theta_1
    base, index = var_name.split('_', 1)

    if base in GREEK_VARS:
        base_latex = GREEK_VARS[base]
    else:
        base_latex = base

    if index in GREEK_VARS:
        index_latex = GREEK_VARS[index]
        return rf"{base_latex}{index_latex}"

    if '_' in index:
        index_base, index_suffix = index.split('_', 1)
        if index_base in GREEK_VARS:
            index_base_latex = GREEK_VARS[index_base]
        else:
            index_base_latex = index_base

        safe_suffix = index_suffix.replace("\\", r"\\").replace("_", r"\_")
        return rf"{base_latex}{index_base_latex}_{{\text{{{safe_suffix}}}}}"

    safe_index = index.replace("\\", r"\\").replace("_", r"\_")
    return rf"{base_latex}_{{\text{{{safe_index}}}}}"


def eval_line(line: str):
    """
    Evaluate a single input line.

    Returns:
      - var:          variable name or None
      - expr_sym:     symbolic SymPy expression
      - expr_num:     numeric SymPy expression
      - val:          simplified result (including units)
      - desired_unit: tuple (name, base_unit, factor) or None
    """
    global sym_exprs
    line = line.strip()
    if not line:
        return None, None, None, None, None

    desired_unit = None

    # environment for numeric evaluation
    env = {}
    env.update(unit_ns)
    env.update(var_ns)

    # environment for symbolic representation
    env_syms = {}
    env_syms.update(unit_ns)
    env_syms.update({
        'pi': sp.pi,
        'sin': sp.sin,
        'cos': sp.cos,
        'exp': sp.exp,
        'integrate': sp.Integral,
        'diff': sp.Derivative,
        'sqrt': sp.sqrt,
        'symbols': sp.symbols,
        'x': sp.symbols('x'),
        'y': sp.symbols('y'),
        't_sym': sp.symbols('t'),
        'Eq': sp.Eq,
    })
    for name in user_vars:
        env_syms[name] = sp.Symbol(name)

    if '=' in line:
        var_part, rhs_part = line.split('=', 1)
        var = var_part.strip()
        rhs_raw = rhs_part.strip()

        if var in reserved_names:
            raise NameError(f"'{var}' is reserved as a unit and cannot be used as a variable.")

        # parse desired unit to the right of "|"
        if '|' in rhs_raw:
            rhs_core, desired = rhs_raw.split('|', 1)
            rhs_core = rhs_core.strip()
            desired_name = desired.strip()
            if desired_name:
                if desired_name not in desired_unit_map:
                    raise ValueError(f"Unknown desired unit '{desired_name}'")
                desired_unit = desired_unit_map[desired_name]
        else:
            rhs_core = rhs_raw

        rhs_expanded = expand_units(rhs_core)

        expr_num = sp.sympify(rhs_expanded, locals=env)
        val = sp.simplify(expr_num)

        expr_sym = sp.sympify(rhs_expanded, locals=env_syms)

        var_ns[var] = val
        user_vars.add(var)

        sym_exprs[var] = expr_sym

        return var, expr_sym, expr_num, val, desired_unit

    else:
        line_expanded = expand_units(line)
        expr_num = sp.sympify(line_expanded, locals=env)
        val = sp.simplify(expr_num)
        expr_sym = sp.sympify(line_expanded, locals=env_syms)
        return None, expr_sym, expr_num, val, None


def create_plot(expr_sym, var_symbol, x_min=-10, x_max=10, num_points=400):
    """Create a plot and return it as a Base64 data URL (data:image/png;...)."""
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


@app.route("/", methods=["GET", "POST"])
def index():
    default_input = (
        '"Example calculation with units"\n'
        "v = 10'm/s ; t = 3's\n"
        "m_a = 10'kg\n"
        "F = m_a * v / t\n"
        "lamda = 5'W/(m*K)\n"
        "\n"
        '"Symbolic"\n'
        "f = x^2\n"
        "diff(f, x)\n"
        "integrate(f, (x, 0, 5))\n"
        "plot(f, x, -5, 5)\n"
        "\n"
        '"Equation solver"\n'
        "x = 3\n"
        "y = 20\n"
        "z = solve1(Eq(y, 3*x + z^2), z)\n"
    )

    user_input = default_input
    # list of blocks; each block is a list of items (dicts)
    results = []

    if request.method == "POST":
        global var_ns, user_vars, sym_exprs
        var_ns = dict(base_var_ns)
        user_vars = set()
        sym_exprs = {}

        user_input = request.form.get("code", "")
        lines = user_input.splitlines()
        line_no = 0

        for raw in lines:
            line_no += 1
            parts = [p.strip() for p in raw.split(';') if p.strip()]
            if not parts:
                continue

            # list of {"type": "...", ...} for this input line
            block_items = []

            for part in parts:
                stripped = part.strip()

                if not stripped or stripped.startswith("#"):
                    continue

                # text lines in double quotes
                if (stripped.startswith('"') and stripped.endswith('"')
                        and len(stripped) >= 2):
                    text = stripped[1:-1]

                    if text.startswith("!"):
                        raw_latex = text[1:]
                        block_items.append({
                            "type": "latex",
                            "content": raw_latex,
                        })
                        continue

                    safe_text = (
                        text
                        .replace("\\", r"\\")
                        .replace("_", r"\_")
                    )
                    block_items.append({
                        "type": "latex",
                        "content": rf"\text{{{safe_text}}}",
                    })
                    continue

                # ---------------- plot command ----------------
                if stripped.startswith("plot(") and stripped.endswith(")"):
                    try:
                        inner = stripped[5:-1]
                        args = [a.strip() for a in inner.split(",")]

                        if len(args) < 2:
                            raise ValueError("plot(f, x, [xmin, xmax]) expected.")

                        # symbolic environment, same as in eval_line()
                        env_syms = {}
                        env_syms.update(unit_ns)
                        env_syms.update({
                            'pi': sp.pi,
                            'sin': sp.sin,
                            'cos': sp.cos,
                            'exp': sp.exp,
                            'integrate': sp.Integral,
                            'diff': sp.Derivative,
                            'sqrt': sp.sqrt,
                            'symbols': sp.symbols,
                            'x': sp.symbols('x'),
                            'y': sp.symbols('y'),
                            't_sym': sp.symbols('t'),
                            'Eq': sp.Eq,
                        })
                        for name in user_vars:
                            env_syms[name] = sp.Symbol(name)

                        func_name = args[0]

                        # if this is a defined variable and we have a symbolic expression for it
                        if func_name in sym_exprs:
                            f_expr = sym_exprs[func_name]
                        else:
                            # otherwise parse expression directly (e.g. plot(x^2, x, -5, 5))
                            f_expr = sp.sympify(func_name, locals=env_syms)

                        var_symbol = sp.Symbol(args[1])

                        if len(args) >= 3:
                            x_min = sp.N(sp.sympify(args[2], locals=env_syms))
                        else:
                            x_min = -10
                        if len(args) >= 4:
                            x_max = sp.N(sp.sympify(args[3], locals=env_syms))
                        else:
                            x_max = 10

                        img_data = create_plot(f_expr, var_symbol, x_min, x_max)
                        block_items.append({
                            "type": "plot",
                            "src": img_data,
                        })
                    except Exception as e:
                        safe_err = (
                            f"Error while plotting: {str(e)}"
                            .replace("\\", r"\\")
                            .replace("_", r"\_")
                        )
                        block_items.append({
                            "type": "latex",
                            "content": rf"\text{{{safe_err}}}",
                        })
                    continue
                # -------------- end plot command --------------

                # regular computation lines
                try:
                    var, expr_sym, expr_num, val, desired_unit = eval_line(stripped)
                    if expr_sym is None or val is None:
                        continue

                    if isinstance(val, (list, tuple, dict)) or isinstance(expr_sym, (list, tuple, dict)):
                        latex_expr = latex(val)
                        if var is not None:
                            var_latex = var_to_latex(var)
                            full_latex = rf"{var_latex} = {latex_expr}"
                        else:
                            full_latex = latex_expr

                        block_items.append({
                            "type": "latex",
                            "content": full_latex,
                        })
                        continue

                    val_conv = val

                    if desired_unit is not None:
                        unit_label, base_unit, factor = desired_unit
                        try:
                            val_base = sp.simplify(convert_to(val, base_unit))
                        except Exception as e:
                            raise ValueError(
                                f"Conversion to desired unit failed: {e}"
                            )

                        mag_base, unit_base = split_magnitude_unit(val_base)

                        # Dimensionscheck: unit_base/base_unit muss dimensionslos sein
                        ratio = sp.simplify(unit_base / base_unit)
                        if ratio.has(*unit_ns.values()):
                            raise ValueError(
                                f"Desired unit '{unit_label}' is not dimensionally compatible with the expression."
                            )

                        # special case: absolute temperature in K -> °C
                        if base_unit == K and unit_label.startswith("^\circ"):
                            mag = sp.simplify(mag_base - 273.15)
                        else:
                            mag = sp.simplify(mag_base / factor)

                        mag_str = format_magnitude_decimal(mag, digits=3)
                        mag_with_unit = rf"{mag_str}\,{unit_label}"

                        symbol_names = {}
                        for name in user_vars:
                            sym = sp.Symbol(name)
                            symbol_names[sym] = var_to_latex(name)

                        latex_expr = latex(
                            expr_sym,
                            mul_symbol="\\cdot",
                            symbol_names=symbol_names,
                        ).replace("\\cdot", "\\cdot{}")

                        only_units_and_numbers = True
                        for s in expr_sym.free_symbols:
                            if s not in unit_ns.values():
                                only_units_and_numbers = False
                                break

                        if var is not None:
                            var_latex = var_to_latex(var)
                            if only_units_and_numbers:
                                full_latex = rf"{var_latex} = {mag_with_unit}"
                            else:
                                full_latex = rf"{var_latex} = {latex_expr} = {mag_with_unit}"
                        else:
                            full_latex = rf"{latex_expr} = {mag_with_unit}"

                        block_items.append({
                            "type": "latex",
                            "content": full_latex,
                        })
                        continue

                    # automatic conversion to preferred units
                    if val.has(*unit_ns.values()):
                        for u in preferred_units:
                            try:
                                cand = sp.simplify(convert_to(val, u))
                                if cand.has(u):
                                    val_conv = cand
                                    break
                            except Exception:
                                pass

                    val = val_conv

                    try:
                        val = sp.simplify(convert_to(val, BASE_UNITS))
                    except Exception:
                        pass

                    symbol_names = {}
                    for name in user_vars:
                        sym = sp.Symbol(name)
                        symbol_names[sym] = var_to_latex(name)

                    latex_expr = latex(
                        expr_sym,
                        mul_symbol="\\cdot",
                        symbol_names=symbol_names,
                    ).replace("\\cdot", "\\cdot{}")

                    mag, unit = split_magnitude_unit(val)
                    mag_str = format_magnitude_decimal(mag, digits=3)

                    if unit == 1:
                        mag_with_unit = mag_str
                    else:
                        latex_unit = latex(unit)
                        mag_with_unit = rf"{mag_str}\,{latex_unit}"

                    only_units_and_numbers = True
                    for s in expr_sym.free_symbols:
                        if s not in unit_ns.values():
                            only_units_and_numbers = False
                            break

                    if var is not None:
                        var_latex = var_to_latex(var)
                        if only_units_and_numbers:
                            full_latex = rf"{var_latex} = {mag_with_unit}"
                        else:
                            full_latex = rf"{var_latex} = {latex_expr} = {mag_with_unit}"
                    else:
                        full_latex = rf"{latex_expr} = {mag_with_unit}"

                    block_items.append({
                        "type": "latex",
                        "content": full_latex,
                    })

                except Exception as e:
                    err1 = f"Error in line {line_no}: {stripped}"
                    err2 = str(e)
                    safe_err = (
                        f"{err1} -- {err2}"
                        .replace("\\", r"\\")
                        .replace("_", r"\_")
                    )
                    block_items.append({
                        "type": "latex",
                        "content": rf"\text{{{safe_err}}}",
                    })

            merged_items = []
            current_latex_parts = []

            for item in block_items:
                if item["type"] == "latex":
                    current_latex_parts.append(item["content"])
                else:
                    # if LaTeX was accumulated before, flush it as one item
                    if current_latex_parts:
                        merged_items.append({
                            "type": "latex",
                            "content": " \\quad ".join(current_latex_parts),
                        })
                        current_latex_parts = []
                    # keep plot or other item types as-is
                    merged_items.append(item)

            # append remaining LaTeX parts at the end
            if current_latex_parts:
                merged_items.append({
                    "type": "latex",
                    "content": " \\quad ".join(current_latex_parts),
                })

            block_items = merged_items

            if block_items:
                results.append(block_items)

    return render_template("index.html", code=user_input, results=results)

def run_server():
    """Run the Flask development server (debug disabled for PyInstaller builds)."""
    app.run(host="127.0.0.1", port=5000, debug=False)

if __name__ == "__main__":
    # Start server in a background thread
    t = threading.Thread(target=run_server, daemon=True)
    t.start()

    # Give the server a moment to start
    time.sleep(1)

    # Open the application in the default web browser
    webbrowser.open("http://127.0.0.1:5000")

    # Keep the main thread alive so the program does not exit immediately
    t.join()

__version__ = "0.9.3"

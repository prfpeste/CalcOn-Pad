import base64
import io

import matplotlib
matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import sympy as sp


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

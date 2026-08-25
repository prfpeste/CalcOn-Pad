import io
import os
import sys
import zipfile

from flask import Flask, Response, render_template, request

from core.engine import DEFAULT_INPUT, evaluate_code
from core.latex_export import build_latex_document
from core.safe_runner import DEFAULT_TIMEOUT_SECONDS, run_with_timeout
from mathlib.units import make_safe_text_latex

DEFAULT_PRECISION = "0.01"
DEFAULT_FONT_SIZE = "14"

_FONT_SIZE_MIN_PX = 10
_FONT_SIZE_MAX_PX = 40


def _resource_base_path() -> str:
    """Directory templates/ and static/ live under.

    When running from source, that's simply this file's directory. When
    frozen into a single executable (PyInstaller --onefile), everything
    bundled via --add-data is extracted at startup into a temporary
    directory exposed as sys._MEIPASS -- resources must be looked up
    there instead, or Flask silently fails to find templates/static and
    the packaged app shows a blank/unstyled page.
    """
    if getattr(sys, "frozen", False):
        return getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(sys.executable)))
    return os.path.dirname(os.path.abspath(__file__))


def _parse_precision_to_rel_tol(raw_precision: str) -> float:
    """Converts the text from the rounding-precision field (a percent
    value, e.g. "0.01" for 0.01%) into a rel_tol for
    mathlib.units.format_magnitude_decimal() (e.g. 0.0001).

    Falls back to the previous default (0.01% == 1e-4) on invalid/
    empty/non-positive input -- the RAW input still stays in the field
    (see index()), only the actual rounding used for the computation
    falls back.
    """
    try:
        precision_percent = float(raw_precision)
        if precision_percent <= 0:
            raise ValueError("Precision must be positive.")
    except (TypeError, ValueError):
        return 1e-4

    return precision_percent / 100


def _parse_font_size_px(raw_font_size: str) -> int:
    """Converts the text from the font-size field into a validated pixel
    value for the result container's inline style.

    Falls back to the default on invalid input, like the rounding
    precision. Also clamped to a sane range (10-40px): this field lands
    directly in a style="..." attribute in the template, so a hard
    number is needed here rather than arbitrary text -- this protects
    both against broken layout (e.g. "9999") and against anything other
    than a number ever reaching the style attribute.
    """
    try:
        font_size = float(raw_font_size)
        if font_size <= 0:
            raise ValueError("Font size must be positive.")
    except (TypeError, ValueError):
        return int(DEFAULT_FONT_SIZE)

    return max(_FONT_SIZE_MIN_PX, min(_FONT_SIZE_MAX_PX, round(font_size)))


def _read_calc_form(form) -> tuple[str, str, str, float]:
    """Reads code/precision/font_size from a POST form, with the same
    fallback rules as index() -- shared by index() and export_latex()
    so e.g. the rounding used for the export exactly matches what's
    currently shown on screen.
    """
    user_input = form.get("code", "")
    precision = form.get("precision", DEFAULT_PRECISION).strip() or DEFAULT_PRECISION
    font_size = form.get("font_size", DEFAULT_FONT_SIZE).strip() or DEFAULT_FONT_SIZE
    rel_tol = _parse_precision_to_rel_tol(precision)

    return user_input, precision, font_size, rel_tol


def _evaluate_code_safely(user_input: str, rel_tol: float):
    """Like core.engine.evaluate_code(), but with a hard time limit
    (see core/safe_runner.py) -- protects the server from an
    intentionally or accidentally very expensive input (a huge symbolic
    integral, a tall power tower, a large matrix, ...) blocking a
    request indefinitely.
    """
    status, value = run_with_timeout(
        evaluate_code, args=(user_input,), kwargs={"rel_tol": rel_tol},
        timeout=DEFAULT_TIMEOUT_SECONDS,
    )

    if status == "ok":
        return value

    if status == "timeout":
        message = (
            f"Timeout: computation took longer than {DEFAULT_TIMEOUT_SECONDS}s "
            "and was aborted."
        )
    else:
        message = f"Computation failed: {value}"

    return [[{"type": "latex", "content": rf"\text{{{make_safe_text_latex(message)}}}"}]]


def create_app():
    base_path = _resource_base_path()
    app = Flask(
        __name__,
        template_folder=os.path.join(base_path, "templates"),
        static_folder=os.path.join(base_path, "static"),
    )

    @app.route("/", methods=["GET", "POST"])
    def index():
        user_input = DEFAULT_INPUT
        precision = DEFAULT_PRECISION
        font_size = DEFAULT_FONT_SIZE
        results = []

        if request.method == "POST":
            user_input, precision, font_size, rel_tol = _read_calc_form(request.form)
            results = _evaluate_code_safely(user_input, rel_tol)

        return render_template(
            "index.html",
            code=user_input,
            results=results,
            precision=precision,
            font_size=font_size,
            font_size_px=_parse_font_size_px(font_size),
        )

    @app.route("/export/latex", methods=["POST"])
    def export_latex():
        user_input, _precision, _font_size, rel_tol = _read_calc_form(request.form)
        results = _evaluate_code_safely(user_input, rel_tol)
        tex, images = build_latex_document(results)

        if not images:
            return Response(
                tex,
                mimetype="application/x-tex",
                headers={
                    "Content-Disposition": "attachment; filename=engipad_export.tex"
                },
            )

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("engipad_export.tex", tex)
            for filename, image_bytes in images:
                zf.writestr(filename, image_bytes)
        buf.seek(0)

        return Response(
            buf.getvalue(),
            mimetype="application/zip",
            headers={
                "Content-Disposition": "attachment; filename=engipad_export.zip"
            },
        )

    return app


app = create_app()

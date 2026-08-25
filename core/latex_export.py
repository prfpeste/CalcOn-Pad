"""Builds a standalone, pdflatex-compilable .tex document from the
results structure produced by core.engine.evaluate_code().

Deliberately NO separate rendering logic: results already contains a
finished LaTeX string per line (the same one shown in the browser via
MathJax's "$$ ... $$" -- see templates/index.html). The export just
wraps these strings in "\\[ ... \\]" (display math) instead of
generating them again -- this guarantees the web view and the export
stay consistent.

Known, deliberately unaddressed limitation: plots are embedded via
\\includegraphics, but only when the document is delivered as a ZIP
(text + PNG files) -- a plain .tex download without image files can't
reference any plots. build_latex_document() therefore always returns
the image files too; the caller (app.py) decides based on that whether
to serve a single .tex or a .zip.
"""

from __future__ import annotations

import base64
import re

_PREAMBLE = r"""\documentclass[11pt]{article}
\usepackage[utf8]{inputenc}
\usepackage[T1]{fontenc}
\usepackage[a4paper,margin=2.5cm]{geometry}
\usepackage{amsmath}
\usepackage{amssymb}
\usepackage{graphicx}

\setlength{\parindent}{0pt}

\begin{document}
"""

_CLOSING = r"""
\end{document}
"""

_DATA_URI_RE = re.compile(r"^data:image/(?P<ext>[a-zA-Z0-9.+-]+);base64,(?P<data>.*)$", re.DOTALL)


def _decode_plot_src(src: str) -> tuple[bytes, str]:
    """Splits a "data:image/png;base64,..." string (see
    mathlib.plotting.create_plot()) into raw image bytes + file
    extension.
    """
    match = _DATA_URI_RE.match(src)
    if not match:
        raise ValueError("Unexpected plot image format (not a data: URI).")

    ext = match.group("ext").split("+")[0]  # e.g. "svg+xml" -> "svg" (unused here, always png)
    return base64.b64decode(match.group("data")), ext


def build_latex_document(results, title: str = "EngiPad Export") -> tuple[str, list[tuple[str, bytes]]]:
    """Builds the .tex source + a list of (filename, image bytes) for
    every plot contained in the results.

    results: the same structure returned by core.engine.evaluate_code()
    -- a list of "blocks" (one per input line), each a list of
    {"type": "latex"|"plot"|"spacer", ...} dicts.
    """
    body_parts: list[str] = []
    images: list[tuple[str, bytes]] = []
    plot_counter = 0

    for block in results:
        block_parts: list[str] = []

        for item in block:
            item_type = item.get("type")

            if item_type == "latex":
                block_parts.append(rf"\[ {item['content']} \]")

            elif item_type == "plot":
                plot_counter += 1
                image_bytes, ext = _decode_plot_src(item["src"])
                filename = f"plot_{plot_counter}.{ext}"
                images.append((filename, image_bytes))
                block_parts.append(
                    "\\begin{center}\n"
                    rf"\includegraphics[width=0.7\linewidth]{{{filename}}}"
                    "\n\\end{center}"
                )

            elif item_type == "spacer":
                block_parts.append(r"\vspace{0.8em}")

        if block_parts:
            body_parts.append("\n".join(block_parts))

    body = "\n\n".join(body_parts)
    tex = _PREAMBLE.replace(
        r"\begin{document}",
        f"% {title}\n\\begin{{document}}",
    ) + body + _CLOSING

    return tex, images

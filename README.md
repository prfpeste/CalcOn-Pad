# CalcOn Pad

CalcOn Pad is a small browser‑based calculation notebook built with Python, Flask, SymPy, and Matplotlib.

It lets you:

- Perform calculations with physical units (`m`, `s`, `kg`, `N`, `J`, `W`, `Pa`, `bar`, `atm`, `V`, `A`, `Ohm`, …)
- Do symbolic math (derivatives, integrals, equations)
- Generate plots directly in the browser
- View results as nicely formatted LaTeX via MathJax
- Load and save calculation files via the web UI

The interface consists of a text editor on the left and a LaTeX/plot output area on the right.


## Features

- Web UI using Flask, HTML/CSS/JavaScript and MathJax
- SymPy integration for
  - symbolic expressions (`diff`, `integrate`, `Eq`, `solve`, `solve1`)
  - numeric evaluation
- Unit system with convenient input:
  - apostrophe syntax for units: `10'J`, `3's`, `5'm`, `10'kg`, `5'W/(m*K)`, …
  - automatic conversion to preferred units (`N`, `J`, `W`, `Pa`, `bar`, `atm`, `V`, `A`, `Ohm`) where possible
  - explicit target units using the `|` syntax (for example `| kWh`, `| bar`)
- Plotting function: `plot(f, x, xmin, xmax)` generates a PNG plot with Matplotlib and shows it in the browser
- Text lines in double quotes are rendered as LaTeX text (for example section headers or comments)
- Greek variable names (`alpha`, `beta`, `phi_1`, …) are automatically converted to the corresponding LaTeX symbols


## Requirements

- Python 3
- Python packages:
  - `flask`
  - `sympy`
  - `matplotlib`
  - `numpy`

Install the dependencies, for example:

```bash
pip install flask sympy matplotlib numpy

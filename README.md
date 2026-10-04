# Description
This repository will contain code for a web-app to help middle and high school students practice algebraic manipulation of algebraic expressions and equations.

## Usage
When the app is loaded you are presented with a prompt that invited you to type in either an algebraic expression or an algebraic equation.

The equation (or expression) is then displayed (via Mathjax), with an input text box below it along with three buttons (distribute, factor, and simplify).
In the prompt you can type in a manipulation.  For example, if you wanted to add one to both side of the equation (or just add one to the algebraic expression), then you would type `+1`.  If you wanted to add $x$ you would type `+x`.  If you wanted to divide both side by $x+1$ you would type `/(x+1)`.  After presenting return, the expression displayed previously moves to the top and is greyed.  In place of the old expression is a new expression (not yet simplified or expanded).

All the computation results are stored locally, there is no backend database.  Refreshing the browser resets everything.

### Distribute/Factor/Simplify Buttons
 - The `simplify` button will do things like combine like terms so $2x+x+1+1$ becomes $3x+2$ or turn $(x^3)^2$ into $x^6$, or even transform $\log(e^x)$ into $x$.

 - The `distribute` button will apply the distributive property to get rid of parenthesis, so $3x(2x+1)$ would become $6x^2 + 3x$.

 - The `factor` button does the (psuedo)-inverse of distribute by turning things like $6x^2 + 3x$ into $3x(2x+1)$.

### Undo
The `undo` button (or ⌘Z / Ctrl+Z) undoes the last step, bringing back the previous expression. You can also click any earlier step in the history to jump back to it.

## How it works
Under the hood, this is nothing more than a Sympy interface, using LaTeX as the language of choice for typing equations. Rendering is done with mathjax.

SymPy runs directly in the browser via [Pyodide](https://pyodide.org) (Python compiled to WebAssembly) inside a Web Worker, so the whole app is a static site with no server. The first visit downloads Python + SymPy (~10–15 MB); the browser caches it afterwards.

```
index.html            the page
css/styles.css        styles (light + dark mode)
js/app.js             UI: history, undo, buttons, live preview
js/engine-client.js   promise wrapper around the worker
js/worker.js          loads Pyodide + SymPy and runs py/engine.py
py/engine.py          the math: parsing, both-sides operations, simplify/distribute/factor
tests/test_engine.py  pytest tests for the math engine
```

## Running locally
The worker needs to be served over http (opening `index.html` as a file won't work):

```sh
python3 -m http.server 8000
# then open http://localhost:8000
```

## Tests
```sh
python3 -m venv .venv && .venv/bin/pip install sympy lark pytest
.venv/bin/pytest tests
```

## Deploying
It's just static files: enable GitHub Pages for the `main` branch (root folder), or drop the folder on any static host.

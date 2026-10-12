# Description
This repository will contain code for a web-app to help middle and high school students practice algebraic manipulation of algebraic expressions and equations.

## Usage
When the app is loaded you are presented with a prompt that invited you to type in either an algebraic expression or an algebraic equation.

The equation (or expression) is then displayed (via Mathjax), with an input text box below it along with four buttons (combine like terms, distribute, factor, and simplify).
In the prompt you can type in a manipulation.  For example, if you wanted to add one to both side of the equation (or just add one to the algebraic expression), then you would type `+1`.  If you wanted to add $x$ you would type `+x`.  If you wanted to divide both side by $x+1$ you would type `/(x+1)`.  After presenting return, the expression displayed previously moves to the top and is greyed.  In place of the old expression is a new expression (not yet simplified or expanded).

All the computation results are stored locally, there is no backend database.  Refreshing the browser resets everything.

### Combine/Distribute/Factor/Simplify Buttons
 - The `combine like terms` button only adds up matching terms, so $3x^2+2x^2+x$ becomes $5x^2+x$. Nothing else changes: $2(x+1)$ isn't distributed and nothing is factored.

 - The `simplify` button will do things like combine like terms so $2x+x+1+1$ becomes $3x+2$ or turn $(x^3)^2$ into $x^6$, or even transform $\log(e^x)$ into $x$.

 - The `distribute` button will apply the distributive property to get rid of parenthesis, so $3x(2x+1)$ would become $6x^2 + 3x$.

 - The `factor` button does the (psuedo)-inverse of distribute by turning things like $6x^2 + 3x$ into $3x(2x+1)$.

### Undo
The `undo` button (or ⌘Z / Ctrl+Z) undoes the last step, bringing back the previous expression. You can also click any earlier step in the history to jump back to it.

## Arcade mode
The **Arcade mode** tab is the same idea, set up for solving equations and styled like a cheap arcade game ("Equation Attack").

Type an equation and the letter to solve for in the **SOLVE FOR** box. With only one letter (like $2x+1=5$) the box can stay blank. With several (like $3y+2x=7$) it's how you say which one you're after. The level is cleared when that letter is alone on one side, the other side doesn't contain it, and no power-up would change that side any more. So $y = \frac{7-2x}{3}$ wins, but $x = \frac{4}{2}$ still needs a cancel.

Instead of typing a step, you press one of four arcade buttons — **add**, **subtract**, **multiply**, **divide** — after typing an amount in the box next to it (Enter in a box presses its button).

Five power-ups light up only when they would change something. Each does one small thing, so students see every step:
 - `combine like terms` works the same as on the main tab.
 - `cancel common factors` cancels what matches on the top and bottom of a fraction, including numbers with a common factor: $\frac{2x}{2}$ becomes $x$ and $\frac{4}{6}$ becomes $\frac{2}{3}$. It never factors first, so $\frac{2x+4}{2}$ stays as it is.
 - `multiply numbers` multiplies plain numbers in the same product: $3\cdot 4$ becomes $12$ and $2\cdot 3x$ becomes $6x$.

Before combine or cancel lands, the screen briefly shows what it's about to do, with a sword-slash sound: like terms light up in matching colours, and cancelled factors get struck through (a partly cancelled number shows what's left, like a 2 above a struck-out 4). Only the top level of each side is marked up.

 - `distribute` multiplies out one set of brackets and nothing more: $3(x+1)$ becomes $3x + 3\cdot 1$ (then multiply numbers gives $3x+3$). Nested brackets open one press at a time.
 - `factor` pulls out the greatest common factor only: $6x+3$ becomes $3(2x+1)$ and $ay+by$ becomes $y(a+b)$, which is handy for solving for $y$. It doesn't do other kinds of factoring, like $x^2-1$.

These are lighter than the Workbench tab's Distribute and Factor buttons, which also tidy everything up along the way. Unlike the other power-ups, distribute and factor each count as a move, and their buttons say "+1 MOVE".

So $\frac{x}{3}=4$ → multiply by 3 → $3\left(\frac{x}{3}\right) = 3\cdot 4$ → cancel → $x = 3\cdot 4$ → multiply numbers → $x = 12$.

When the level is cleared you get **LEVEL CLEAR!** along with your move count. Only the four big buttons, distribute and factor count as moves; the other power-ups are free. Undo and the clickable history work the same as on the main tab. The sound toggle remembers your choice in this browser.

## How it works
Under the hood, this is nothing more than a Sympy interface, using LaTeX as the language of choice for typing equations. Rendering is done with mathjax.

SymPy runs directly in the browser via [Pyodide](https://pyodide.org) (Python compiled to WebAssembly) inside a Web Worker, so the whole app is a static site with no server. The first visit downloads Python + SymPy (~10–15 MB); the browser caches it afterwards.

```
index.html            the page
css/styles.css        styles (light + dark mode)
js/app.js             UI: history, undo, buttons, live preview, tabs
js/arcade.js          Arcade mode UI and sound effects
js/math.js            MathJax rendering helper shared by both tabs
js/engine-client.js   promise wrapper around the worker
js/worker.js          loads Pyodide + SymPy and runs py/engine.py
py/engine.py          the math: parsing, both-sides operations, the buttons, highlights
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

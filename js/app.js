import { createEngine, EngineError } from "./engine-client.js";

const $ = (id) => document.getElementById(id);
const els = {
  bar: $("engine-bar"),
  status: $("engine-status"),
  history: $("history"),
  current: $("current"),
  empty: $("empty"),
  currentLabel: $("current-label"),
  currentMath: $("current-math"),
  form: $("composer"),
  input: $("input"),
  submit: $("submit"),
  preview: $("preview"),
  error: $("error"),
  actions: $("actions"),
  undo: $("undo"),
  newProblem: $("new-problem"),
};

// steps[0] is the original problem; every later step has the label of the
// operation that produced it. The engine keeps every expression by id, so
// undo is purely a client-side pop.
const state = { steps: [], busy: false };

const engine = createEngine({ onProgress: (msg) => (els.status.textContent = msg) });
engine.ready.then(
  () => {
    els.bar.classList.add("is-done");
    refreshPreview();
  },
  (err) => {
    els.bar.classList.add("is-error");
    els.status.textContent = "Couldn't load the math engine. Check your connection and refresh.";
    console.error(err);
  },
);

// ------------------------------------------------------------------ math

const mathReady = new Promise((resolve) => {
  const wait = () => (window.MathJax?.startup?.promise ? MathJax.startup.promise.then(resolve) : setTimeout(wait, 30));
  wait();
});

async function renderMath(el, latex, display = true) {
  await mathReady;
  el.replaceChildren(MathJax.tex2chtml(latex, { display }));
  MathJax.startup.document.clear();
  MathJax.startup.document.updateDocument();
}

// Transform labels arrive as \text{simplify}; show those as plain text.
function labelNode(latex, accent = false) {
  const word = latex.match(/^\\text\{(.*)\}$/)?.[1];
  const cls = `pill${accent ? " pill--accent" : ""}`;
  if (!word) return mathNode(latex, cls, false);
  const el = document.createElement("div");
  el.className = `${cls} pill--text`;
  el.textContent = word;
  return el;
}

function mathNode(latex, className, display = true) {
  const el = document.createElement("div");
  el.className = className;
  renderMath(el, latex, display);
  return el;
}

// ------------------------------------------------------------------ render

function animate(el, name) {
  el.classList.remove(name);
  void el.offsetWidth; // restart the animation
  el.classList.add(name);
}

function render({ direction = "forward" } = {}) {
  const { steps } = state;
  const hasProblem = steps.length > 0;

  els.history.replaceChildren(
    ...steps.slice(0, -1).map((step, i) => {
      const li = document.createElement("li");
      li.className = "history__item";
      if (step.label) li.append(labelNode(step.label));
      const row = document.createElement("button");
      row.type = "button";
      row.className = "history__row";
      row.title = "Go back to this step";
      row.append(mathNode(step.latex, "history__math"));
      row.addEventListener("click", () => revertTo(i));
      li.append(row);
      return li;
    }),
  );

  els.empty.hidden = hasProblem;
  els.currentMath.hidden = !hasProblem;
  els.actions.hidden = !hasProblem;
  els.newProblem.hidden = !hasProblem;
  els.currentLabel.replaceChildren();

  if (hasProblem) {
    const step = steps.at(-1);
    if (step.label) els.currentLabel.append(labelNode(step.label, true));
    renderMath(els.currentMath, step.latex);
    animate(els.current, direction === "back" ? "enter-back" : "enter");
    if (direction === "forward" && els.history.lastElementChild) {
      animate(els.history.lastElementChild, "settle");
    }
  }

  els.input.placeholder = hasProblem ? "Next step: +1, -x, *2, /(x+1), ^2" : "e.g. 2x + 1 = 5";
  els.submit.textContent = hasProblem ? "Apply" : "Start";
  els.undo.disabled = steps.length <= 1;
  setBusy(state.busy);
}

function setBusy(busy) {
  state.busy = busy;
  els.current.classList.toggle("is-busy", busy);
  els.submit.disabled = busy;
  for (const b of els.actions.querySelectorAll("[data-transform]")) b.disabled = busy;
  els.undo.disabled = busy || state.steps.length <= 1;
}

function showError(message) {
  els.error.textContent = message;
  animate(els.form, "shake");
}

function clearError() {
  els.error.textContent = "";
}

// ------------------------------------------------------------------ actions

async function run(fn, ...args) {
  setBusy(true);
  clearError();
  try {
    return await engine.call(fn, ...args);
  } catch (err) {
    showError(err instanceof EngineError ? err.message : "Something went wrong. Try again.");
    if (!(err instanceof EngineError)) console.error(err);
    return null;
  } finally {
    setBusy(false);
  }
}

async function submit(text) {
  if (state.busy) return;
  const current = state.steps.at(-1);
  const result = current
    ? await run("apply_op", current.id, text)
    : await run("parse_problem", text);
  if (!result) return;
  state.steps.push({ id: result.id, latex: result.latex, label: result.label ?? null });
  els.input.value = "";
  els.preview.replaceChildren();
  render();
}

async function applyTransform(kind) {
  const current = state.steps.at(-1);
  if (!current || state.busy) return;
  const result = await run("transform", current.id, kind);
  if (!result) return;
  if (result.latex === current.latex) {
    showError(`Nothing to ${kind} here.`);
    return;
  }
  state.steps.push(result);
  render();
}

function undo() {
  if (state.steps.length <= 1 || state.busy) return;
  state.steps.pop();
  clearError();
  render({ direction: "back" });
}

function revertTo(index) {
  if (state.busy) return;
  state.steps.length = index + 1;
  clearError();
  render({ direction: "back" });
  els.input.focus();
}

function newProblem() {
  state.steps = [];
  els.input.value = "";
  els.preview.replaceChildren();
  clearError();
  render();
  els.input.focus();
}

// ------------------------------------------------------------------ preview

let previewTimer;
let previewSeq = 0;

function refreshPreview() {
  clearTimeout(previewTimer);
  previewTimer = setTimeout(async () => {
    const text = els.input.value.trim();
    const seq = ++previewSeq;
    if (!text) return els.preview.replaceChildren();
    let latex = "";
    try {
      latex = await engine.call("preview", text, state.steps.length ? "op" : "problem");
    } catch {
      /* preview is best-effort */
    }
    if (seq !== previewSeq) return; // a newer keystroke won
    if (latex) renderMath(els.preview, latex, false);
    els.preview.classList.toggle("is-stale", !latex);
  }, 150);
}

// ------------------------------------------------------------------ wiring

els.form.addEventListener("submit", (e) => {
  e.preventDefault();
  const text = els.input.value.trim();
  if (text) submit(text);
});

els.input.addEventListener("input", () => {
  clearError();
  refreshPreview();
});

els.input.addEventListener("keydown", (e) => {
  if (e.key === "Escape") {
    els.input.value = "";
    els.preview.replaceChildren();
    clearError();
  }
});

document.addEventListener("keydown", (e) => {
  // ⌘Z / Ctrl+Z undoes a step, unless the student is undoing typing.
  if ((e.metaKey || e.ctrlKey) && !e.shiftKey && e.key.toLowerCase() === "z") {
    if (document.activeElement === els.input && els.input.value) return;
    e.preventDefault();
    undo();
  }
});

els.actions.addEventListener("click", (e) => {
  const kind = e.target.closest("[data-transform]")?.dataset.transform;
  if (kind) applyTransform(kind);
});

els.undo.addEventListener("click", undo);
els.newProblem.addEventListener("click", newProblem);

$("examples").addEventListener("click", (e) => {
  const example = e.target.closest("[data-example]")?.dataset.example;
  if (example) submit(example);
});

render();

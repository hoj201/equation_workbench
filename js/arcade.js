// Arcade mode: the same engine behind an arcade cabinet. Four big buttons
// (add, subtract, multiply, divide) each with an amount slot, plus power-ups
// that only light up when the engine says they'd do something.

import { EngineError } from "./engine-client.js";
import { renderMath } from "./math.js";

const $ = (id) => document.getElementById(id);

// ------------------------------------------------------------------ sound
// Square-wave blips, the cheaper the better.

const sound = {
  on: true,
  ctx: null,
  play(notes, type = "square") {
    if (!this.on) return;
    try {
      this.ctx ??= new AudioContext();
      let t = this.ctx.currentTime;
      for (const [freq, dur] of notes) {
        const osc = this.ctx.createOscillator();
        const gain = this.ctx.createGain();
        osc.type = type;
        osc.frequency.value = freq;
        gain.gain.setValueAtTime(0.06, t);
        gain.gain.exponentialRampToValueAtTime(0.001, t + dur);
        osc.connect(gain).connect(this.ctx.destination);
        osc.start(t);
        osc.stop(t + dur);
        t += dur * 0.9;
      }
    } catch {
      /* no audio, no problem */
    }
  },
};

// A sword swipe: a burst of noise swept from bright to dull, plus a quick
// falling "shing".
sound.slash = function () {
  if (!this.on) return;
  try {
    this.ctx ??= new AudioContext();
    const t = this.ctx.currentTime;
    const len = Math.floor(this.ctx.sampleRate * 0.25);
    const buf = this.ctx.createBuffer(1, len, this.ctx.sampleRate);
    const data = buf.getChannelData(0);
    for (let i = 0; i < len; i++) data[i] = Math.random() * 2 - 1;
    const noise = this.ctx.createBufferSource();
    noise.buffer = buf;
    const band = this.ctx.createBiquadFilter();
    band.type = "bandpass";
    band.Q.value = 1.2;
    band.frequency.setValueAtTime(6000, t);
    band.frequency.exponentialRampToValueAtTime(700, t + 0.22);
    const gain = this.ctx.createGain();
    gain.gain.setValueAtTime(0.0001, t);
    gain.gain.exponentialRampToValueAtTime(0.35, t + 0.03);
    gain.gain.exponentialRampToValueAtTime(0.001, t + 0.25);
    noise.connect(band).connect(gain).connect(this.ctx.destination);
    noise.start(t);

    const shing = this.ctx.createOscillator();
    const shingGain = this.ctx.createGain();
    shing.type = "triangle";
    shing.frequency.setValueAtTime(2600, t);
    shing.frequency.exponentialRampToValueAtTime(900, t + 0.18);
    shingGain.gain.setValueAtTime(0.05, t);
    shingGain.gain.exponentialRampToValueAtTime(0.001, t + 0.2);
    shing.connect(shingGain).connect(this.ctx.destination);
    shing.start(t);
    shing.stop(t + 0.2);
  } catch {
    /* no audio, no problem */
  }
};

const SFX = {
  move: [[440, 0.06], [660, 0.08]],
  powerup: [[523, 0.06], [659, 0.06], [784, 0.06], [1047, 0.12]],
  undo: [[660, 0.06], [440, 0.1]],
  error: [[140, 0.18]],
  start: [[392, 0.08], [523, 0.08], [659, 0.14]],
  clear: [[523, 0.1], [523, 0.1], [523, 0.1], [698, 0.3], [880, 0.12], [784, 0.12], [1047, 0.4]],
};

try {
  sound.on = localStorage.getItem("arcade-sound") !== "off";
} catch {
  /* private mode */
}

// ------------------------------------------------------------------ module

export function initArcade(engine) {
  const els = {
    view: $("arcade-view"),
    screen: $("b-screen"),
    slash: $("b-slash"),
    moves: $("b-moves"),
    soundBtn: $("b-sound"),
    title: $("b-title"),
    start: $("b-start"),
    problem: $("b-problem"),
    target: $("b-target"),
    goal: $("b-goal"),
    goalVar: $("b-goal-var"),
    play: $("b-play"),
    trail: $("b-trail"),
    label: $("b-label"),
    math: $("b-math"),
    clear: $("b-clear"),
    clearMoves: $("b-clear-moves"),
    error: $("b-error"),
    deck: $("b-deck"),
    undo: $("b-undo"),
    newGame: $("b-new"),
    slots: [...document.querySelectorAll("#b-deck [data-for]")],
    powerups: [...document.querySelectorAll("#b-deck [data-transform]")],
  };

  // Each step: {id, latex, label, move, options: {combine, cancel, multiply, solved}}.
  // move is true for the big arcade buttons; only those count as moves.
  // target is the variable being solved for.
  const state = { steps: [], target: null, busy: false };

  function animate(el, name) {
    el.classList.remove(name);
    void el.offsetWidth;
    el.classList.add(name);
  }

  function labelNode(latex) {
    const el = document.createElement("span");
    el.className = "tag";
    const word = latex.match(/^\\text\{(.*)\}$/)?.[1];
    if (word) el.textContent = word.toUpperCase();
    else {
      el.classList.add("tag--math");
      renderMath(el, latex, false);
    }
    return el;
  }

  function render({ direction = "forward" } = {}) {
    const { steps } = state;
    const current = steps.at(-1);
    const solved = Boolean(current?.options.solved);

    els.title.hidden = Boolean(current);
    els.goal.hidden = !current;
    els.goalVar.textContent = state.target ?? "";
    els.play.hidden = !current;
    els.clear.hidden = !solved;
    els.deck.classList.toggle("is-off", !current || solved);
    const moves = steps.filter((s) => s.move).length;
    els.moves.textContent = String(moves).padStart(2, "0");

    els.trail.replaceChildren(
      ...steps.slice(0, -1).map((step, i) => {
        const li = document.createElement("li");
        const row = document.createElement("button");
        row.type = "button";
        row.className = "trail__row";
        row.title = "Go back to this step";
        if (step.label) row.append(labelNode(step.label));
        const m = document.createElement("div");
        m.className = "trail__math";
        renderMath(m, step.latex);
        row.append(m);
        row.addEventListener("click", () => revertTo(i));
        li.append(row);
        return li;
      }),
    );
    els.trail.scrollTop = els.trail.scrollHeight;

    els.label.replaceChildren();
    if (current) {
      if (current.label) els.label.append(labelNode(current.label));
      renderMath(els.math, current.latex);
      animate(els.math, direction === "back" ? "zap-back" : "zap");
    }

    for (const b of els.powerups) {
      const was = !b.hidden;
      b.hidden = !current || solved || !current.options[b.dataset.transform];
      if (!was && !b.hidden) animate(b, "pop");
    }

    if (solved) {
      els.clearMoves.textContent = `IN ${moves} MOVE${moves === 1 ? "" : "S"}`;
    }
    setBusy(state.busy);
  }

  function setBusy(busy) {
    state.busy = busy;
    const current = state.steps.at(-1);
    const off = busy || !current || current.options.solved;
    for (const b of els.deck.querySelectorAll("[data-op], [data-transform]")) b.disabled = off;
    for (const s of els.slots) s.disabled = !current || current.options.solved;
    els.undo.disabled = busy || state.steps.length <= 1;
    els.newGame.disabled = busy || !current;
  }

  function showError(message) {
    els.error.textContent = message;
    animate(els.screen, "shake");
    sound.play(SFX.error, "sawtooth");
  }

  function clearError() {
    els.error.textContent = "";
  }

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

  // Run fn, then ask which power-ups apply to the result.
  async function step(fn, ...args) {
    const result = await run(fn, ...args);
    if (!result) return null;
    const options = await run("options", result.id, state.target);
    if (!options) return null;
    return { id: result.id, latex: result.latex, label: result.label ?? null, options };
  }

  function push(next, sfx) {
    state.steps.push(next);
    render();
    if (next.options.solved) {
      sound.play(SFX.clear);
      animate(els.clear, "flash");
    } else {
      sound.play(sfx);
    }
  }

  async function startGame(text, target) {
    if (state.busy) return;
    if (!text) return showError("Type an equation first!");
    const parsed = await run("parse_problem", text);
    if (!parsed) return;
    const vars = parsed.variables;
    if (!parsed.latex.includes("=")) return showError("You need an = sign to solve something!");
    if (!target) {
      if (vars.length === 1) target = vars[0];
      else if (!vars.length) return showError("There's no letter to solve for!");
      else {
        showError(`Which letter are we solving for? Type ${vars.join(" or ")} in the SOLVE FOR box.`);
        els.target.focus();
        return;
      }
    } else if (!vars.includes(target)) {
      showError(`There's no ${target} in this equation!`);
      els.target.focus();
      return;
    }
    const options = await run("options", parsed.id, target);
    if (!options) return;
    state.target = target;
    state.steps = [];
    els.problem.value = "";
    els.target.value = "";
    push({ id: parsed.id, latex: parsed.latex, label: null, options }, SFX.start);
    els.slots[0].focus();
  }

  const OP_NAMES = { "+": "add", "-": "subtract", "*": "multiply by", "/": "divide by" };

  async function pressOp(op) {
    const current = state.steps.at(-1);
    if (!current || state.busy) return;
    const slot = els.slots.find((s) => s.dataset.for === op);
    const amount = slot.value.trim();
    if (!amount) {
      showError(`Type what to ${OP_NAMES[op]} in the box first!`);
      slot.focus();
      return;
    }
    const next = await step("apply_op", current.id, `${op}(${amount})`);
    if (!next) return;
    slot.value = "";
    push({ ...next, move: true }, SFX.move);
  }

  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

  // Show what's about to happen (like terms coloured, factors struck out)
  // with a slash, hold it for a beat, then land the result.
  async function pressPowerup(kind) {
    const current = state.steps.at(-1);
    if (!current || state.busy) return;
    const marked = await run("highlight", current.id, kind);
    const next = await step("transform", current.id, kind);
    if (!next) return;
    if (marked) {
      setBusy(true);
      try {
        await renderMath(els.math, marked);
        els.math.classList.add(`is-marking`, `is-marking--${kind}`);
        animate(els.slash, "swipe");
        sound.slash();
        await sleep(1200);
      } finally {
        els.math.classList.remove("is-marking", `is-marking--${kind}`);
        setBusy(false);
      }
    } else {
      sound.slash();
    }
    push(next, SFX.powerup);
  }

  function undo() {
    if (state.steps.length <= 1 || state.busy) return;
    state.steps.pop();
    clearError();
    render({ direction: "back" });
    sound.play(SFX.undo);
  }

  function revertTo(index) {
    if (state.busy) return;
    state.steps.length = index + 1;
    clearError();
    render({ direction: "back" });
    sound.play(SFX.undo);
  }

  function newGame() {
    state.steps = [];
    state.target = null;
    clearError();
    for (const s of els.slots) s.value = "";
    render();
    els.problem.focus();
  }

  function renderSound() {
    els.soundBtn.textContent = sound.on ? "♪ ON" : "♪ OFF";
    els.soundBtn.setAttribute("aria-pressed", String(sound.on));
  }

  // ---------------------------------------------------------------- wiring

  els.start.addEventListener("submit", (e) => {
    e.preventDefault();
    startGame(els.problem.value.trim(), els.target.value.trim());
  });

  $("b-levels").addEventListener("click", (e) => {
    const chip = e.target.closest("[data-level]");
    if (chip) startGame(chip.dataset.level, chip.dataset.target ?? "");
  });

  els.deck.addEventListener("click", (e) => {
    const op = e.target.closest("[data-op]")?.dataset.op;
    if (op) return pressOp(op);
    const kind = e.target.closest("[data-transform]")?.dataset.transform;
    if (kind) pressPowerup(kind);
  });

  for (const slot of els.slots) {
    slot.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        pressOp(slot.dataset.for);
      }
    });
    slot.addEventListener("input", clearError);
  }
  els.problem.addEventListener("input", clearError);
  els.target.addEventListener("input", clearError);

  els.undo.addEventListener("click", undo);
  els.newGame.addEventListener("click", newGame);

  els.soundBtn.addEventListener("click", () => {
    sound.on = !sound.on;
    try {
      localStorage.setItem("arcade-sound", sound.on ? "on" : "off");
    } catch {
      /* private mode */
    }
    renderSound();
  });

  document.addEventListener("keydown", (e) => {
    if (els.view.hidden) return;
    if ((e.metaKey || e.ctrlKey) && !e.shiftKey && e.key.toLowerCase() === "z") {
      if (e.target instanceof HTMLInputElement && e.target.value) return;
      e.preventDefault();
      undo();
    }
  });

  renderSound();
  render();
}

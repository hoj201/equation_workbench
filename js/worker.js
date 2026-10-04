// Runs Pyodide + SymPy off the main thread so the UI never freezes.
// Protocol: main thread posts {reqId, fn, args}; we reply {reqId, result} or
// {reqId, error}. When start-up finishes we post {ready: true} (or {fatal}).

// Pyodide 314+ only runs in module workers, hence the ES import.
import { loadPyodide } from "https://cdn.jsdelivr.net/pyodide/v314.0.7/full/pyodide.mjs";

const DISPATCH = `
import json, engine

PUBLIC = {"parse_problem", "apply_op", "transform", "preview"}

def _dispatch(fn, args_json):
    try:
        if fn not in PUBLIC:
            raise engine.UserError("Unknown request.")
        result = getattr(engine, fn)(*json.loads(args_json))
        return json.dumps({"result": result})
    except engine.UserError as e:
        return json.dumps({"error": str(e)})
    except Exception as e:
        return json.dumps({"error": "Something went wrong: " + type(e).__name__})
`;

async function boot() {
  const progress = (stage) => postMessage({ progress: stage });
  progress("Loading Python…");
  const pyodide = await loadPyodide();
  progress("Loading SymPy…");
  await pyodide.loadPackage(["sympy", "micropip"]);
  progress("Loading the LaTeX reader…");
  await pyodide.pyimport("micropip").install("lark");
  progress("Almost ready…");
  const source = await (await fetch(new URL("../py/engine.py", import.meta.url))).text();
  pyodide.FS.writeFile("/home/pyodide/engine.py", source);
  pyodide.runPython(DISPATCH);
  return pyodide.globals.get("_dispatch");
}

const ready = boot();
ready.then(
  () => postMessage({ ready: true }),
  (err) => postMessage({ fatal: String(err) }),
);

self.onmessage = async ({ data: { reqId, fn, args } }) => {
  try {
    const dispatch = await ready;
    postMessage({ reqId, ...JSON.parse(dispatch(fn, JSON.stringify(args))) });
  } catch (err) {
    postMessage({ reqId, error: String(err) });
  }
};

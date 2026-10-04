// Promise-based wrapper around js/worker.js.
//   await engine.ready;
//   const { id, latex } = await engine.call("parse_problem", "2x+1=5");
// Calls made before the engine is ready are queued by the worker.

export class EngineError extends Error {}

export function createEngine({ onProgress } = {}) {
  const worker = new Worker(new URL("./worker.js", import.meta.url), { type: "module" });
  const pending = new Map();
  let nextId = 0;
  let resolveReady, rejectReady;
  const ready = new Promise((res, rej) => {
    resolveReady = res;
    rejectReady = rej;
  });

  worker.onmessage = ({ data }) => {
    if (data.progress) return onProgress?.(data.progress);
    if (data.ready) return resolveReady();
    if (data.fatal) return rejectReady(new Error(data.fatal));
    const p = pending.get(data.reqId);
    if (!p) return;
    pending.delete(data.reqId);
    if ("error" in data) p.reject(new EngineError(data.error));
    else p.resolve(data.result);
  };

  // Fires if the worker script itself fails to load (e.g. the CDN is down).
  worker.onerror = (e) => rejectReady(new Error(e.message || "Worker failed to load"));

  function call(fn, ...args) {
    const reqId = ++nextId;
    return new Promise((resolve, reject) => {
      pending.set(reqId, { resolve, reject });
      worker.postMessage({ reqId, fn, args });
    });
  }

  return { ready, call };
}

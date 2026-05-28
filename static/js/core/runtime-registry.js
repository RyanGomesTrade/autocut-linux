export const runtime = {
  nodes: new Map(), // entity_id -> DOM Node reference
  meta: new Map(),  // entity_id -> { lastPatch, ts, status, type }
  dirty: new Set()  // entity_ids to be flushed in next RAF
};

/**
 * Registra ou atualiza metadados de uma entidade no runtime.
 * @param {string} id 
 * @param {string} type 
 * @param {object} patch 
 */
export function registerUpdate(id, type, patch) {
  if (!id) return;
  const existing = runtime.meta.get(id);
  
  // Se já existe e o patch é o mesmo, não fazer nada!
  if (existing) {
    const existingJson = JSON.stringify(existing.lastPatch);
    const newJson = JSON.stringify({ ...existing.lastPatch, ...patch });
    if (existingJson === newJson) {
      return;
    }
  }

  const existingData = existing || { type, lastPatch: {} };
  
  // Merge incremental patch into existing data for the registry meta
  const mergedPatch = { ...existingData.lastPatch, ...patch };

  runtime.meta.set(id, {
    ...existingData,
    lastPatch: mergedPatch,
    ts: Date.now(),
    status: patch.status || existingData.status
  });

  runtime.dirty.add(id);
}

/**
 * Orchestrator para batching via RequestAnimationFrame.
 * @param {Function} flushFn Função que sabe como projetar patches no DOM
 */
export function startRuntimeLoop(flushFn) {
  function loop() {
    if (runtime.dirty.size > 0) {
      const batch = Array.from(runtime.dirty);
      runtime.dirty.clear();
      
      for (const id of batch) {
        const meta = runtime.meta.get(id);
        const node = runtime.nodes.get(id);
        flushFn(id, meta, node);
      }
    }
    requestAnimationFrame(loop);
  }
  requestAnimationFrame(loop);
}

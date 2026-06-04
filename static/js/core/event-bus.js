export class EventBus {
  constructor() {
    /** @type {Map<string, Set<Function>>} */
    this.listeners = new Map();
  }

  /**
   * @param {string} type
   * @param {(payload: any, meta: {id?: string, ts?: number}) => void} handler
   */
  on(type, handler) {
    if (!this.listeners.has(type)) this.listeners.set(type, new Set());
    this.listeners.get(type).add(handler);
    return () => this.off(type, handler);
  }

  off(type, handler) {
    const set = this.listeners.get(type);
    if (!set) return;
    set.delete(handler);
    if (set.size === 0) this.listeners.delete(type);
  }

  /**
   * @param {string} type
   * @param {any} payload
   * @param {{id?: string, ts?: number}=} meta
   */
  emit(type, payload, meta = {}) {
    const set = this.listeners.get(type);
    if (!set) return;
    for (const fn of set) {
      try {
        fn(payload, meta);
      } catch (e) {
        // Avoid breaking other listeners
        console.error(`[EventBus] handler error for ${type}:`, e);
      }
    }
  }
}


export class SSEClient {
  constructor({ url, eventBus, withCredentials = false } = {}) {
    this.url = url;
    this.eventBus = eventBus;
    this.withCredentials = withCredentials;
    this.es = null;
  }

  connect() {
    if (!this.url) throw new Error("SSEClient: url is required");
    if (!this.eventBus) throw new Error("SSEClient: eventBus is required");

    this.es = new EventSource(this.url);
    this.es.onmessage = (e) => {
      if (!e.data) return;
      let msg = null;
      try {
        msg = JSON.parse(e.data);
      } catch (err) {
        // Ignore non-JSON keepalives (defensive)
        return;
      }
      if (!msg || !msg.type) return;
      this.eventBus.emit(msg.type, msg.payload, { 
        id: msg.id, 
        ts: msg.ts,
        patch: msg.patch 
      });
    };

    this.es.onerror = () => {
      // EventSource auto-reconnects; we only log here.
      // Components should rely on state transitions, not on connection events.
      console.warn("[SSEClient] connection error; EventSource will retry.");
    };
  }

  close() {
    if (this.es) {
      this.es.close();
      this.es = null;
    }
  }
}


// Bootstrap Attention OS Event-Driven Runtime.
import "/static/app.js";
import { EventBus } from "./core/event-bus.js";
import { SSEClient } from "./core/sse-client.js";
import { runtime, registerUpdate, startRuntimeLoop } from "./core/runtime-registry.js";

const eventBus = new EventBus();

const sse = new SSEClient({
  url: "/stream/events",
  eventBus,
});

// Mapeamento direto: Evento -> Runtime Registry
const eventToType = {
  "JOB_QUEUED": "job",
  "JOB_PROGRESS": "job",
  "JOB_COMPLETED": "job",
  "JOB_ERROR": "job",
  "JOB_PAUSED": "job",
  "JOB_CANCELLED": "job",
  "TREND_CREATED": "trend",
  "TELEMETRY_UPDATE": "telemetry",
  "ALERT_TRIGGERED": "alert"
};

Object.keys(eventToType).forEach(evName => {
  eventBus.on(evName, (payload, { id, patch }) => {
    const data = patch || payload; // Aceita patch ou payload inicial
    registerUpdate(id, eventToType[evName], data);
  });
});

// Debug & Global Access
window.__AttentionOS = { 
  eventBus, 
  runtime, 
  sse,
  // O app.js deve injetar o projetor DOM aqui
  injectProjector: (projectorFn) => startRuntimeLoop(projectorFn)
};

sse.connect();

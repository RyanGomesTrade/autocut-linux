
/* ══════════════════════════════════════════════════════════════════════════
   ATTENTION OS // EVENT-DRIVEN RUNTIME DOM PROJECTOR
   ══════════════════════════════════════════════════════════════════════════ */

console.log("Attention OS: DOM Projector loaded");

let tabListenersAttached = false;
let opsMounted = false;

function _getAttentionOS() {
    return window.__AttentionOS || {};
}

document.addEventListener("DOMContentLoaded", () => {
    const navBtns = Array.from(document.querySelectorAll('.nav-btn[data-tab]'));
    navBtns.forEach(btn => btn.addEventListener('click', () => {
        const tabId = btn.getAttribute('data-tab');
        switchTab(tabId);
    }));

    // Event Delegation Global para botões dinâmicos
    document.addEventListener("click", async (e) => {
        const attention = _getAttentionOS();
        if (!attention) return;

        // Botão +QUEUE
        const queueBtn = e.target.closest("[data-action='queue']");
        if (queueBtn) {
            const trendId = queueBtn.dataset.id;
            queueBtn.disabled = true;
            queueBtn.textContent = "ADDING...";
            attention.eventBus.emit("QUEUE_REQUESTED", { id: trendId });
            setTimeout(() => { queueBtn.disabled = false; queueBtn.textContent = "+ QUEUE"; }, 2000);
        }

        // Botão INVESTIGATE
        const investigateBtn = e.target.closest("[data-action='investigate']");
        if (investigateBtn) {
            const trendId = investigateBtn.dataset.id;
            openInvestigate(trendId);
        }

        // Botão PAUSE
        const pauseBtn = e.target.closest("[data-action='pause']");
        if (pauseBtn) {
            const jobId = pauseBtn.dataset.id;
            pauseBtn.disabled = true;
            pauseBtn.textContent = "PAUSING...";
            attention.eventBus.emit("PAUSE_REQUESTED", { id: jobId });
            setTimeout(() => { pauseBtn.disabled = false; pauseBtn.textContent = "PAUSE"; }, 2000);
        }

        // Botão CANCEL
        const cancelBtn = e.target.closest("[data-action='cancel']");
        if (cancelBtn) {
            const jobId = cancelBtn.dataset.id;
            cancelBtn.disabled = true;
            cancelBtn.textContent = "CANCELLING...";
            attention.eventBus.emit("CANCEL_REQUESTED", { id: jobId });
            setTimeout(() => { cancelBtn.disabled = false; cancelBtn.textContent = "CANCEL"; }, 2000);
        }
    });

    // EventBus → Backend Bridge
    const checkAttentionReady = setInterval(() => {
        const attention = _getAttentionOS();
        if (attention?.injectProjector && attention.eventBus) {
            clearInterval(checkAttentionReady);
            
            attention.eventBus.on("QUEUE_REQUESTED", async ({ id }) => {
                try {
                    const videoId = id.replace('trend_', '');
                    await fetch("/api/queue/add", {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ trend_id: videoId })
                    });
                    // Cancelar timeout anterior, se houver!
                    if (hydrateTimeoutId) {
                        clearTimeout(hydrateTimeoutId);
                    }
                    // Hydrate rápido após 300ms para que os jobs apareçam logo!
                    hydrateTimeoutId = setTimeout(() => hydrateInitialOnce(), 300);
                } catch (err) {
                    console.error("[QUEUE_REQUESTED] Error:", err);
                }
            });

            attention.eventBus.on("PAUSE_REQUESTED", async ({ id }) => {
                try {
                    await fetch("/api/jobs/pause", {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ job_id: id })
                    });
                    // Cancelar timeout anterior, se houver!
                    if (hydrateTimeoutId) {
                        clearTimeout(hydrateTimeoutId);
                    }
                    // Hydrate rápido após 200ms, caso o SSE demore
                    hydrateTimeoutId = setTimeout(() => hydrateInitialOnce(), 200);
                } catch (err) {
                    console.error("[PAUSE_REQUESTED] Error:", err);
                }
            });

            attention.eventBus.on("CANCEL_REQUESTED", async ({ id }) => {
                try {
                    console.log("[CANCEL_REQUESTED] Enviando para backend:", { job_id: id });
                    const response = await fetch("/api/jobs/cancel", {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ job_id: id })
                    });
                    const result = await response.json();
                    console.log("[CANCEL_REQUESTED] Resposta do backend:", result);
                    // Cancelar timeout anterior, se houver!
                    if (hydrateTimeoutId) {
                        clearTimeout(hydrateTimeoutId);
                    }
                    // Hydrate rápido após 200ms, caso o SSE demore
                    hydrateTimeoutId = setTimeout(() => hydrateInitialOnce(), 200);
                } catch (err) {
                    console.error("[CANCEL_REQUESTED] Error:", err);
                }
            });

            attention.injectProjector(projectEntity);
            hydrateInitialOnce();
        }
    }, 100);

    initTerminalTime();
    initStatusIndicators();
});

function openInvestigate(trendId) {
    const attention = _getAttentionOS();
    const meta = attention?.runtime?.meta?.get(trendId);
    if (!meta) return;

    const modal = document.getElementById('modal-inspector');
    if (!modal) return;

    const p = meta.lastPatch;
    const metaEl = document.getElementById('inspector-meta');
    const traceEl = document.getElementById('inspector-trace');
    const titleEl = document.getElementById('inspector-title');

    if (titleEl) titleEl.textContent = `Investigar: ${p.title || trendId}`;
    if (metaEl) {
        metaEl.innerHTML = `
            <p><strong>Score:</strong> ${(p.score * 100).toFixed(0)}</p>
            <p><strong>Relative VPH:</strong> ${p.relative_vph?.toFixed(1) || '--'}x</p>
            <p><strong>Acceleration:</strong> ${p.vph_acceleration?.toFixed(1) || '--'}</p>
        `;
    }
    if (traceEl) traceEl.innerHTML = `<p>Explainability trace mockado (inicial)</p>`;

    modal.classList.add('active');
}

function switchTab(tabId) {
    // Hide all panels
    const allPanels = document.querySelectorAll('.panel');
    allPanels.forEach(p => p.classList.remove('active'));
    // Show target panel
    const targetPanel = document.getElementById(`panel-${tabId}`);
    if (targetPanel) {
        targetPanel.classList.add('active');
    }
    // Update nav state
    const navBtns = Array.from(document.querySelectorAll('.nav-btn[data-tab]'));
    navBtns.forEach(b => b.classList.remove('active'));
    const activeBtn = navBtns.find(b => b.getAttribute('data-tab') === tabId);
    if (activeBtn) activeBtn.classList.add('active');
    // Start/stop appropriate polling
    if (tabId === 'factory') {
        startFactoryPolling();
    } else {
        stopFactoryPolling();
    }
    if (tabId === 'ops') {
        startOpsSSE();
    } else {
        stopOpsSSE();
    }
}

function initTerminalTime() {
    const el = document.getElementById("terminalTime");
    if (!el) return;
    setInterval(() => {
        const now = new Date();
        el.textContent = now.toLocaleTimeString('pt-BR', { hour12: false });
    }, 1000);
}

function initStatusIndicators() {
    // Placeholder for SSE heartbeat integration
    // When we get WORKER_HEARTBEAT events, update #globalStatusIndicator & #globalStatusText
}

function _setVal(id, val) {
    const el = document.getElementById(id);
    if (!el) return;
    if (typeof val === 'number' && !Number.isNaN(val)) el.textContent = val.toFixed(0);
    else el.textContent = val;
}

function _computePipelineCountsFromJobs() {
    const attention = _getAttentionOS();
    const meta = attention?.runtime?.meta;
    if (!meta) return { active_jobs: 0, queue_size: 0, clips_rendered: 0 };

    let active_jobs = 0;
    let queue_size = 0;
    let clips_rendered = 0;
    
    for (const m of meta.values()) {
        if (m.type !== "job") continue;
        const status = m.lastPatch?.status?.toUpperCase();
        if (!status) continue;
        if (status === "PENDING") queue_size += 1;
        if (status === "DONE") clips_rendered += 1;
        if (["PENDING", "DOWNLOADING", "CUTTING", "RENDERING"].includes(status)) active_jobs += 1;
    }
    return { active_jobs, queue_size, clips_rendered };
}

// ── Hydration & Projection ─────────────────────────────────────────────────

// Flag para evitar hidratação duplicada em curto intervalo
let isHydrating = false;
let hydrateTimeoutId = null;

async function hydrateInitialOnce() {
    // Cancelar timeout anterior, se houver!
    if (hydrateTimeoutId) {
        clearTimeout(hydrateTimeoutId);
        hydrateTimeoutId = null;
    }

    if (isHydrating) {
        console.log("[Hydrate] Já está hidratando — pulando.");
        return;
    }
    isHydrating = true;
    console.log("[Hydrate] Iniciando hidratação...");
    try {
        const [jobs, trends] = await Promise.all([
            fetch("/api/ops/jobs").then(r => r.json()),
            fetch("/api/ops/trends").then(r => r.json())
        ]);
        console.log("[Hydrate] Dados recebidos:", { jobsCount: jobs.length, trendsCount: trends.length });
        
        const attention = _getAttentionOS();
        if (attention) {
            // Limpar containers e runtime para evitar duplicatas e remover jobs cancelados
            const jobContainer = document.getElementById("job-queue-list");
            const trendContainer = document.getElementById("trend-monitor-list");
            
            if (jobContainer) {
                jobContainer.innerHTML = '<div class="empty-state">Queue is empty...</div>';
            }
            if (trendContainer) {
                trendContainer.innerHTML = '<div class="empty-state">No trends detected...</div>';
            }
            
            attention.runtime.nodes.clear();
            attention.runtime.meta.clear();
            
            jobs.forEach(job => {
                console.log("[Hydrate] Emitindo JOB_QUEUED para job:", job.job_id);
                attention.eventBus.emit("JOB_QUEUED", job, { id: `job_${job.job_id}` });
            });
            trends.forEach(trend => {
                attention.eventBus.emit("TREND_CREATED", {
                    title: trend.title,
                    url: trend.url,
                    score: trend.final_viral_score,
                    relative_vph: trend.relative_vph,
                    vph_acceleration: trend.vph_acceleration,
                    last_scanned: trend.last_scanned
                }, { id: `trend_${trend.video_id}` });
            });
        }
        console.log("[Hydrate] Hidratação concluída com sucesso!");
    } catch (e) {
        console.warn("Hydrate failed (event-only fallback active):", e);
    } finally {
        isHydrating = false;
    }
}

function projectEntity(id, meta, node) {
    if (!meta) return;

    const { type, lastPatch: p } = meta;

    // Se o job está cancelado, remover da UI
    if (type === "job" && p.status && ["cancelled", "done", "completed"].includes(p.status.toLowerCase())) {
        if (node && node.parentNode) {
            node.parentNode.removeChild(node);
            window.__AttentionOS.runtime.nodes.delete(id);
            window.__AttentionOS.runtime.meta.delete(id);
        }
        return;
    }

    // Se o node NÃO existir, criar um novo!
    if (!node) {
        const newNode = createBaseNode(id, type, p);
        if (newNode) {
            window.__AttentionOS.runtime.nodes.set(id, newNode);
            attachNodeToDOM(type, newNode);
            node = newNode;
        } else {
            return;
        }
    }

    // Se o node EXISTIR, só atualizamos as propriedades — NÃO recriamos!
    updateNodeProperties(node, type, p);

    if (type === "job" || type === "trend") {
            const counts = _computePipelineCountsFromJobs();
            _setVal("val-active", counts.active_jobs);
            _setVal("val-queue", counts.queue_size);
            _setVal("val-rendered", counts.clips_rendered);
            
            if (type === "trend") {
                const trendsCount = Array.from(window.__AttentionOS.runtime.meta.values())
                    .filter(m => m.type === "trend").length;
                _setVal("val-trending", trendsCount);
            }

            // Atualiza visualização dos stages do pipeline
            const allSteps = document.querySelectorAll('.viz-step');
            allSteps.forEach(step => step.classList.remove('active'));

            const metaMap = window.__AttentionOS.runtime?.meta;
            if (metaMap) {
                const jobMetas = Array.from(metaMap.values()).filter(m => m.type === "job");
                const statuses = jobMetas.map(m => m.lastPatch?.status?.toUpperCase());
                if (statuses.includes("RENDERING")) {
                    document.getElementById('step-render')?.classList.add('active');
                } else if (statuses.includes("PENDING")) {
                    document.getElementById('step-queue')?.classList.add('active');
                } else if (statuses.includes("DONE")) {
                    document.getElementById('step-upload')?.classList.add('active');
                }
            }
        }
}

function createBaseNode(id, type, p) {
    if (type === "job") {
        const root = document.createElement("div");
        root.className = "job-item";
        root.setAttribute("data-job-id", id);
        root.style.display = "flex";
        root.style.flexDirection = "column";
        root.style.gap = "10px";
        root.style.padding = "12px";
        root.style.borderBottom = "1px solid var(--border)";
        root.innerHTML = `
            <div style="display:flex; justify-content:space-between; align-items:center;">
                <div class="job-info" style="display:flex; flex-direction:column;">
                    <div class="job-title" style="font-family: var(--mono); font-weight: bold;">${p.video_id || id}</div>
                    <div class="job-meta" style="font-size:11px; color: var(--text-3);">
                        Stage: <span class="job-stage" style="color: var(--amber);">${p.stage || 'QUEUED'}</span>
                        <span style="margin-left:12px;">Worker: <span class="job-worker" style="color: var(--text-2);">${p.worker || '—'}</span></span>
                    </div>
                </div>
                <div style="display:flex; flex-direction:column; align-items:flex-end; gap:4px;">
                    <div class="job-status-badge status-${p.status ? p.status.toLowerCase() : 'pending'}" style="font-size:11px; padding:4px 10px;">
                        ${p.status ? p.status.toUpperCase() : 'PENDING'}
                    </div>
                    <div class="action-group" style="display:flex; gap:4px;">
                        <button class="btn-action" data-action="pause" data-id="${id}" style="font-size:11px; padding:4px 8px;">PAUSE</button>
                        <button class="btn-action danger" data-action="cancel" data-id="${id}" style="font-size:11px; padding:4px 8px;">CANCEL</button>
                    </div>
                </div>
            </div>
            <div style="display:flex; flex-direction:column; gap:6px;">
                <div style="display:flex; justify-content:space-between; font-family: var(--mono); font-size:11px; color: var(--text-3);">
                    <span>Progresso: <span class="job-progress-text">${p.progress ? (p.progress * 100).toFixed(0) + '%' : '0%'}</span></span>
                    <span>ETA: <span class="job-eta">${p.eta ? p.eta + 's' : '—'}</span></span>
                </div>
                <div style="width:100%; height:8px; background: var(--bg2); border: 1px solid var(--border);">
                    <div class="job-progress-bar" style="width:${p.progress ? (p.progress * 100).toFixed(0) + '%' : '0%'}; height:100%; background: var(--green); transition: width 0.3s ease;"></div>
                </div>
            </div>
        `;
        return root;
    }
    if (type === "trend") {
        const root = document.createElement("div");
        root.className = "trend-item";
        root.setAttribute("data-video-id", id);
        root.style.display = "flex";
        root.style.justifyContent = "space-between";
        root.style.alignItems = "center";
        root.innerHTML = `
            <div>
                <div class="trend-title">${p.title || id}</div>
                <div class="trend-stats">
                    <span class="stat-pill high">VPH: ${p.relative_vph ? p.relative_vph.toFixed(1) + 'x' : '--'}</span>
                    <span class="stat-pill med">ACC: ${p.vph_acceleration ? p.vph_acceleration.toFixed(1) : '--'}</span>
                    <span class="stat-pill">SCORE: ${p.score ? (p.score * 100).toFixed(0) : '--'}</span>
                </div>
            </div>
            <div class="action-group" style="display:flex; gap:4px;">
                <button class="btn-action success" data-action="queue" data-id="${id}">+ QUEUE</button>
                <button class="btn-action" data-action="investigate" data-id="${id}">INVESTIGATE</button>
            </div>
        `;
        return root;
    }
    return null;
}

function attachNodeToDOM(type, node) {
    let container = null;
    if (type === "job") container = document.getElementById("job-queue-list");
    if (type === "trend") container = document.getElementById("trend-monitor-list");

    if (container) {
        // Remover qualquer node antigo com o mesmo ID, se existir
        const nodeId = node.getAttribute(`data-${type}-id`);
        if (nodeId) {
            const oldNode = container.querySelector(`[data-${type}-id="${nodeId}"]`);
            if (oldNode && oldNode !== node) {
                oldNode.remove();
            }
        }
        // Adicionar o node
        const empty = container.querySelector('.empty-state');
        if (empty) empty.remove();
        container.appendChild(node);
    }
}

function updateNodeProperties(node, type, p) {
    if (type === "job") {
        const title = node.querySelector('.job-title');
        const stage = node.querySelector('.job-stage');
        const worker = node.querySelector('.job-worker');
        const badge = node.querySelector('.job-status-badge');
        const progressText = node.querySelector('.job-progress-text');
        const progressBar = node.querySelector('.job-progress-bar');
        const eta = node.querySelector('.job-eta');

        if (p.video_id) title.textContent = p.video_id;
        if (p.status) {
            badge.className = `job-status-badge status-${p.status.toLowerCase()}`;
            badge.textContent = p.status.toUpperCase();
        }
        if (p.stage && stage) stage.textContent = p.stage.toUpperCase();
        if (p.worker && worker) worker.textContent = p.worker;
        if (p.progress !== undefined && progressText) {
            progressText.textContent = (p.progress * 100).toFixed(0) + '%';
        }
        if (p.progress !== undefined && progressBar) {
            progressBar.style.width = (p.progress * 100).toFixed(0) + '%';
        }
        if (p.eta !== undefined && eta) {
            eta.textContent = p.eta + 's';
        }
    }
    if (type === "trend") {
        const title = node.querySelector('.trend-title');
        const pills = node.querySelectorAll('.stat-pill');
        if (p.title) title.textContent = p.title;
        if (pills.length >= 3) {
            if (p.relative_vph !== undefined) pills[0].textContent = `VPH: ${p.relative_vph.toFixed(1)}x`;
            if (p.vph_acceleration !== undefined) pills[1].textContent = `ACC: ${p.vph_acceleration.toFixed(1)}`;
            if (p.score !== undefined) pills[2].textContent = `SCORE: ${(p.score * 100).toFixed(0)}`;
        }
    }
    if (type === "telemetry") {
        _renderTelemetryUpdate(p);
    }
}

// ── Empty functions for backward compatibility ──────────────────────────────
function startOpsSSE() { opsMounted = true; }
function stopOpsSSE() { opsMounted = false; }
function _renderTelemetryUpdate(p) { /* todo */ }
function _upsertTrendItem(t) { /* todo */ }
function _upsertJobItem(j) { /* todo */ }
function updateOpsDashboard() { /* todo */ }
function startFactoryPolling() { /* todo */ }
function stopFactoryPolling() { /* todo */ }

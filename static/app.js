/* ==========================================================================
   ATTENTION OS + VIRAL CUTTER PRO // FRONTEND ENGINE (VANILLA JS)
   ========================================================================== */

console.log("Attention OS + Viral Cutter Pro: DOM Projector loaded");

let tabListenersAttached = false;
let opsMounted = false;
let activeSSE = null;
let availableProfiles = [];

function _getAttentionOS() {
    return window.__AttentionOS || {};
}

// --- Funções Globais (Hoisting) para evitar ReferenceError ---
let loadSystemConfig, saveSystemConfig, toggleOllamaFields, toggleWatermarkFields, 
    loadYoutubeProfiles, startTask, startSSE, updateProgress, log, clearLog, 
    syncBatchMeta, addBatchRow, renumberBatchRows, getBatchJobs, setRowStatus, 
    loadBatchQueue, syncBatchProfileSelects, loadNicheCategories, loadResultsGallery,
    loadStrategyParams;
let switchSettingsTab;

document.addEventListener("DOMContentLoaded", () => {
    // ── Tab Manager ────────────────────────────────────────────────────────
    const navBtns = Array.from(document.querySelectorAll('.nav-btn[data-tab]'));
    navBtns.forEach(btn => btn.addEventListener('click', () => {
        const tabId = btn.getAttribute('data-tab');
        switchTab(tabId);
    }));

    // ── Settings Sub-Tab Manager ──────────────────────────────────────────
    const setNavBtns = document.querySelectorAll('.set-nav-btn');
    setNavBtns.forEach(btn => btn.addEventListener('click', () => {
        const setName = btn.getAttribute('data-set');
        switchSettingsTab(setName);
    }));

    switchSettingsTab = function(setName) {
        console.log(`[Settings] Trocando para sub-aba: ${setName}`);
        document.querySelectorAll('.set-nav-btn').forEach(b => b.classList.remove('active'));
        document.querySelectorAll('.set-section').forEach(s => s.classList.remove('active'));
        
        const targetBtn = document.querySelector(`.set-nav-btn[data-set="${setName}"]`);
        const targetSec = document.getElementById(`set-sec-${setName}`);
        
        if (targetBtn) targetBtn.classList.add('active');
        if (targetSec) targetSec.classList.add('active');

        if (setName === 'canais') loadYoutubeProfiles();
    };

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

        // Botão RETRY (Nova Funcionalidade)
        const retryBtn = e.target.closest("[data-action='retry']");
        if (retryBtn) {
            const jobId = retryBtn.dataset.id;
            retryBtn.disabled = true;
            retryBtn.textContent = "RETRYING...";
            await fetch("/api/ops/jobs/control", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ job_id: jobId.replace('job_', ''), action: 'retry' })
            });
            hydrateInitialOnce();
        }

        // Botão DELETE TREND
        const deleteTrendBtn = e.target.closest("[data-action='delete-trend']");
        if (deleteTrendBtn) {
            const trendId = deleteTrendBtn.dataset.id;
            if (confirm("Deseja remover este vídeo do monitor de tendências?")) {
                const videoId = trendId.replace('trend_', '');

                deleteTrendBtn.disabled = true;
                deleteTrendBtn.textContent = "REMOVING...";

                try {
                    console.log("[DELETE] trendId:", trendId, "videoId:", videoId);
                    console.log("[DELETE] URL:", `/api/ops/trends/${videoId}`);

                    const res = await fetch(`/api/ops/trends/${videoId}`, { method: "DELETE" });
                    const text = await res.text(); // lê como texto bruto primeiro
                    console.log("[DELETE] status:", res.status, "body:", text);

                    let data;
                    try {
                        data = JSON.parse(text);
                    } catch {
                        alert("Resposta inválida do servidor:\n" + text.substring(0, 300));
                        deleteTrendBtn.disabled = false;
                        deleteTrendBtn.textContent = "DELETE";
                        return;
                    }

                    if (data.status !== "success") {
                        alert("Erro ao remover: " + data.message);
                        deleteTrendBtn.disabled = false;
                        deleteTrendBtn.textContent = "DELETE";
                        return;
                    }

                    const attention = _getAttentionOS();
                    if (attention) {
                        attention.runtime.nodes.delete(trendId);
                        attention.runtime.meta.delete(trendId);
                    }

                    const node = document.querySelector(`[data-video-id="${trendId}"]`);
                    if (node) node.remove();

                    hydrateInitialOnce();
                } catch (err) {
                    alert("Falha na requisição: " + err.message);
                    deleteTrendBtn.disabled = false;
                    deleteTrendBtn.textContent = "DELETE";
                }
            }
        }

        // Botão COPY TITLE
        if (e.target.closest(".btn-copy-title")) {
            const btn = e.target.closest(".btn-copy-title");
            const text = btn.dataset.text;
            navigator.clipboard.writeText(text);
            
            const oldText = btn.textContent;
            btn.textContent = "COPIED!";
            setTimeout(() => btn.textContent = oldText, 1000);
        }
    });
    
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

            attention.eventBus.on("TITLES_GENERATED", (payload, { id }) => {
                const jobNode = window.__AttentionOS.runtime.nodes.get(id);
                if (jobNode) renderGeneratedTitles(jobNode, payload);
            });

            attention.injectProjector(projectEntity);
            hydrateInitialOnce();
        }
    }, 100);

    // ── Clock ──────────────────────────────────────────────────────────────
    function tick() {
        const d = new Date();
        const el = document.getElementById("terminalTime");
        if (el) {
            el.textContent =
                [d.getHours(), d.getMinutes(), d.getSeconds()]
                    .map(n => String(n).padStart(2, "0")).join(":");
        }
    }
    setInterval(tick, 1000);
    tick();

    // ── Config load / save ─────────────────────────────────────────────────
    loadSystemConfig = async function() {
        try {
            const cfg = await fetch("/api/config").then(r => r.json());
            const g = id => document.getElementById(id);
            const setRadio = (name, val) => {
                const el = document.querySelector(`input[name="${name}"][value="${val}"]`);
                if (el) el.checked = true;
            };

            if (g("inputVideoPath")) g("inputVideoPath").value     = cfg.input || "";
            if (g("selectPreset")) g("selectPreset").value       = cfg.preset || "auto_detect";
            if (g("checkUploadYoutube")) g("checkUploadYoutube").checked = cfg.upload_youtube || false;
            if (g("checkUsePlaywright")) g("checkUsePlaywright").checked = cfg.use_playwright || false;

            // IA & Modelos (Radios)
            setRadio("whisper_model", cfg.whisper_model || "medium");
            setRadio("device", cfg.device || "cpu");
            setRadio("engine", cfg.analysis_engine || "heuristic");
            if (g("inputOllamaModel")) g("inputOllamaModel").value     = cfg.model || "llama3";

            // Cortes & Viral
            if (g("inputTopN")) g("inputTopN").value = cfg.top_n || 10;
            if (g("inputMinScore")) {
                g("inputMinScore").value = cfg.min_score || 40;
                if (g("valMinScore")) g("valMinScore").textContent = cfg.min_score || 40;
                // Feedback em tempo real
                g("inputMinScore").oninput = (e) => { 
                    if(g("valMinScore")) g("valMinScore").textContent = e.target.value; 
                };
            }
            
            if (g("inputMinDuration")) g("inputMinDuration").value = cfg.min_duration || 20;
            if (g("inputMaxDuration")) g("inputMaxDuration").value = cfg.max_duration || 65;
            if (g("checkAutoFrame")) g("checkAutoFrame").checked = cfg.auto_frame || false;

            // Branding (Radios)
            setRadio("wm_mode", cfg.watermark_mode || "none");
            setRadio("wm_pos", cfg.watermark_position || "bottom_right");
            
            if (g("inputWatermarkText")) g("inputWatermarkText").value      = cfg.watermark_text || "";
            if (g("inputWatermarkImage")) g("inputWatermarkImage").value     = cfg.watermark_image || "";

            if (g("selectSubtitleStyle")) g("selectSubtitleStyle").value = cfg.subtitle_style || "high_impact";
            if (g("selectVisualFilter")) g("selectVisualFilter").value  = cfg.visual_filter || "none";
            if (g("inputBgMusic")) g("inputBgMusic").value        = cfg.bg_music || "";
            if (g("inputBgMusicVolume")) {
                g("inputBgMusicVolume").value = cfg.bg_music_volume || 0.15;
                if (g("valBgMusicVolume")) g("valBgMusicVolume").textContent = Math.round((cfg.bg_music_volume || 0.15) * 100) + "%";
                // Feedback em tempo real
                g("inputBgMusicVolume").oninput = (e) => {
                    if(g("valBgMusicVolume")) g("valBgMusicVolume").textContent = Math.round(e.target.value * 100) + "%";
                };
            }

            await loadYoutubeProfiles(cfg.youtube_profile_index);
        } catch (e) {
            log(`[ERRO] Falha ao ler configurações: ${e.message}`, "log-err");
        }
    }
    
    // Alias para compatibilidade com o trigger da aba Branding
    loadStrategyParams = loadSystemConfig;

    saveSystemConfig = async function(silent = false) {
        try {
            // 1. Carrega a configuração atual do servidor para mesclagem
            const currentCfg = await fetch("/api/config").then(r => r.json());
            
            const v = id => { 
                const el = document.getElementById(id); 
                return el ? el.value : null; 
            };
            const c = id => { 
                const el = document.getElementById(id); 
                return el ? el.checked : null; 
            };
            const getRadio = (name) => {
                const el = document.querySelector(`input[name="${name}"]:checked`);
                return el ? el.value : null;
            };

            const updates = {};
            const upd = (key, val) => { if (val !== null) updates[key] = val; };

            // 2. Só atualiza as chaves cujos elementos existem no DOM da aba atual
            upd("input", v("inputVideoPath"));
            upd("preset", v("selectPreset"));
            upd("upload_youtube", c("checkUploadYoutube"));
            upd("use_playwright", c("checkUsePlaywright"));
            
            const ytIdx = v("selectYtProfile");
            if (ytIdx !== null) updates["youtube_profile_index"] = parseInt(ytIdx);

            upd("whisper_model", getRadio("whisper_model"));
            upd("device", getRadio("device"));
            upd("analysis_engine", getRadio("engine"));
            upd("model", v("inputOllamaModel"));

            const topN = v("inputTopN");
            if (topN !== null) updates["top_n"] = parseInt(topN);
            
            const minScore = v("inputMinScore");
            if (minScore !== null) updates["min_score"] = parseFloat(minScore);
            
            if (v("inputMinDuration") !== null) updates["min_duration"] = parseFloat(v("inputMinDuration"));
            if (v("inputMaxDuration") !== null) updates["max_duration"] = parseFloat(v("inputMaxDuration"));
            upd("auto_frame", c("checkAutoFrame"));

            upd("watermark_mode", getRadio("wm_mode"));
            upd("watermark_text", v("inputWatermarkText"));
            upd("watermark_image", v("inputWatermarkImage"));
            upd("watermark_position", getRadio("wm_pos"));

            upd("subtitle_style", v("selectSubtitleStyle"));
            upd("visual_filter", v("selectVisualFilter"));
            upd("bg_music", v("inputBgMusic"));
            if (v("inputBgMusicVolume") !== null) updates["bg_music_volume"] = parseFloat(v("inputBgMusicVolume"));

            // 3. Mescla a config antiga com apenas o que foi alterado na UI
            const config = { ...currentCfg, ...updates };

            const res = await fetch("/api/config", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(config),
            });
            const data = await res.json();
            if (data.status === "success" && !silent) alert("Configurações salvas!");
        } catch (e) {
            alert(`Erro ao salvar: ${e.message}`);
        }
    }

    // Conditional visibility
    const selectAnalysisEngine = document.getElementById("selectAnalysisEngine");
    toggleOllamaFields = function() {
        const wrapper = document.getElementById("ollamaWrapper");
        if (wrapper && selectAnalysisEngine) {
            wrapper.style.display =
                selectAnalysisEngine.value === "ollama" ? "block" : "none";
        }
    }
    if (selectAnalysisEngine) selectAnalysisEngine.addEventListener("change", toggleOllamaFields);

    const selectWatermarkMode = document.getElementById("selectWatermarkMode");
    toggleWatermarkFields = function() {
        if (!selectWatermarkMode) return;
        const m = selectWatermarkMode.value;
        const textWrapper = document.getElementById("watermarkTextWrapper");
        const imgWrapper = document.getElementById("watermarkImageWrapper");
        if (textWrapper) {
            textWrapper.style.display =
                m === "text" || m === "both" ? "block" : "none";
        }
        if (imgWrapper) {
            imgWrapper.style.display =
                m === "image" || m === "both" ? "block" : "none";
        }
    }
    if (selectWatermarkMode) selectWatermarkMode.addEventListener("change", toggleWatermarkFields);

    // Event Delegation para todos os botões de salvar (Config, Branding ou Strategy)
    document.addEventListener("click", (e) => {
        const saveBtn = e.target.closest("#btnSaveConfig, #btnSaveStrategy, #btnSaveBranding");
        if (saveBtn) {
            saveSystemConfig();
        }
    });

    // ── YouTube profiles ───────────────────────────────────────────────────
    loadYoutubeProfiles = async function(activeIndex = 0) {
        console.log("[loadYoutubeProfiles] Carregando perfis do YouTube...");
        try {
            const data = await fetch("/api/youtube/profiles").then(r => r.json());
            availableProfiles = data.profiles || [];
            if (availableProfiles.length === 0) {
                console.warn("[loadYoutubeProfiles] Nenhum perfil do YouTube encontrado. Verifique 'youtube_profiles.json'.");
            }
            ["selectYtProfile", "selectManageProfile"].forEach(selId => {
                console.log(`[loadYoutubeProfiles] Tentando encontrar elemento: ${selId}`);
                const sel = document.getElementById(selId);
                if (!sel) return;
                sel.innerHTML = "";
                availableProfiles.forEach((p, i) => {
                    const opt = Object.assign(document.createElement("option"), {
                        value: i, textContent: p.name, selected: i === activeIndex,
                    });
                    sel.appendChild(opt);
                });
                console.log(`[loadYoutubeProfiles] Elemento ${selId} atualizado com ${availableProfiles.length} perfis.`);
            });
            // Also populate batch panel profile selects
            syncBatchProfileSelects(availableProfiles, activeIndex);
            console.log("[loadYoutubeProfiles] Perfis carregados com sucesso.");
        } catch (e) {
            console.error("Falha ao ler perfis:", e);
        }
    }

    // ── Task execution ─────────────────────────────────────────────────────
    startTask = async function(taskType, extraData = {}) {
        await saveSystemConfig(true);
        try {
            const res  = await fetch("/api/start", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ task_type: taskType, ...extraData }),
            });
            const data = await res.json();
            if (data.status === "success") {
                clearLog();
                log(`[SISTEMA] Tarefa '${taskType.toUpperCase()}' acionada.`, "log-warn");
                startSSE();
                switchTab("monitor");
            } else {
                alert(`Erro: ${data.message}`);
            }
        } catch (e) {
            alert(`Falha: ${e.message}`);
        }
    }

    const btnStartPipeline = document.getElementById("btnStartPipeline");
    if (btnStartPipeline) btnStartPipeline.addEventListener("click", () => startTask("pipeline"));

    const btnDownloadYoutube = document.getElementById("btnDownloadYoutube");
    if (btnDownloadYoutube) btnDownloadYoutube.addEventListener("click", () => {
        const url = document.getElementById("youtubeUrlInput")?.value.trim();
        if (!url) { alert("Insira uma URL do YouTube."); return; }
        startTask("download", { url });
    });

    // ── SSE ────────────────────────────────────────────────────────────────
    startSSE = function() {
        if (activeSSE) activeSSE.close();
        activeSSE = new EventSource("/stream");
        activeSSE.onmessage = e => {
            const d = JSON.parse(e.data);
            if (d.type === "log")    log(d.msg);
            if (d.type === "status") updateProgress(d.percent, d.msg, d.active_task);
        };
        activeSSE.onerror = () => console.warn("SSE error — reconnecting...");
    }

    updateProgress = function(percent, text, activeTask) {
        const chip   = document.getElementById("globalStatusIndicator");
        const chipTx = document.getElementById("globalStatusText");
        if (chip && chipTx) {
            if (activeTask !== "none") {
                chip.className = "status-dot running";
                chipTx.textContent = text.toUpperCase();
            } else {
                chip.className = "status-dot";
                chipTx.textContent = "SISTEMA PRONTO";
            }
        }
        const monitorStatusText = document.getElementById("monitorStatusText");
        const monitorPercentText = document.getElementById("monitorPercentText");
        const monitorProgressBar = document.getElementById("monitorProgressBar");
        if (monitorStatusText) monitorStatusText.textContent = `STATUS: ${text.toUpperCase()}`;
        if (monitorPercentText) monitorPercentText.textContent = `${percent}%`;
        if (monitorProgressBar) monitorProgressBar.style.width = `${percent}%`;
        if (activeTask === "none" && percent === 100) loadResultsGallery();
    }

    // ── Terminal log ───────────────────────────────────────────────────────
    const terminalOutput = document.getElementById("terminalOutput");

    log = function(text, cls = "") {
        if (!terminalOutput) return;
        const div = document.createElement("div");
        div.className = "log-entry";
        if (cls) { div.classList.add(cls); }
        else if (text.includes("[INFO]"))                             div.classList.add("log-ok");
        else if (text.includes("[WARN]") || text.includes("[WARNING]")) div.classList.add("log-warn");
        else if (text.includes("[ERROR]") || text.includes("[CRITICAL]")) div.classList.add("log-err");
        else if (text.includes("[PLAYWRIGHT]"))                        div.classList.add("log-info");
        div.textContent = text;
        terminalOutput.appendChild(div);
        terminalOutput.scrollTop = terminalOutput.scrollHeight;
    }

    clearLog = function() { if (terminalOutput) terminalOutput.innerHTML = ""; }
    const btnClearLog = document.getElementById("btnClearLog");
    if (btnClearLog) btnClearLog.addEventListener("click", clearLog);

    // ── Batch Queue (Table) ────────────────────────────────────────────────
    const batchBody   = document.getElementById("batchTableBody");
    const batchEmpty  = document.getElementById("batchEmpty");
    const batchCount  = document.getElementById("batchRowCount");
    const PRESETS     = ["auto_detect","shorts_blur","podcast_split","tiktok","reels","shorts","landscape","square","social_frame"];

    syncBatchMeta = function() {
        if (!batchBody || !batchEmpty || !batchCount) return;
        const n = batchBody.querySelectorAll("tr").length;
        batchCount.textContent = `${n} job${n !== 1 ? "s" : ""}`;
        batchEmpty.classList.toggle("hidden", n > 0);
    }

    addBatchRow = function(url = "", preset = "shorts_blur", title = "") {
        if (!batchBody) return;
        const rowIndex = batchBody.children.length + 1;
        const tr = document.createElement("tr");

        // Preset select HTML
        const presetOpts = PRESETS.map(p =>
            `<option value="${p}"${p === preset ? " selected" : ""}>${p}</option>`
        ).join("");

        tr.innerHTML = `
            <td class="col-num" style="font-family:var(--mono);color:var(--text-3);font-size:11px;text-align:center">${rowIndex}</td>
            <td class="col-url"><input class="batch-input" type="text" placeholder="https://youtube.com/watch?v=..." value="${url}"></td>
            <td class="col-preset"><select class="batch-select">${presetOpts}</select></td>
            <td class="col-title"><input class="batch-input" type="text" placeholder="OPTIONAL_PREFIX" value="${title}"></td>
            <td class="col-status"><span class="batch-status ${status}">${status.toUpperCase()}</span></td>
            <td class="col-cmd" style="text-align:center"><button class="btn-rm" title="Remover">✕</button></td>
        `;

        tr.querySelector(".btn-rm").addEventListener("click", () => {
            tr.remove();
            renumberBatchRows();
            syncBatchMeta();
        });

        batchBody.appendChild(tr);
        syncBatchMeta();
    }

    renumberBatchRows = function() {
        if (!batchBody) return;
        batchBody.querySelectorAll("tr").forEach((tr, i) => {
            const numCell = tr.querySelector(".col-num");
            if (numCell) numCell.textContent = i + 1;
        });
    }

    getBatchJobs = function() {
        if (!batchBody) return [];
        const jobs = [];
        batchBody.querySelectorAll("tr").forEach(tr => {
            const url    = tr.cells[1]?.querySelector("input")?.value.trim() || "";
            const preset = tr.cells[2]?.querySelector("select")?.value || "auto_detect";
            const title  = tr.cells[3]?.querySelector("input")?.value.trim() || "";
            if (url) jobs.push({ url, preset, title_prefix: title });
        });
        return jobs;
    }

    setRowStatus = function(rowIndex, status) {
        if (!batchBody) return;
        const tr = batchBody.children[rowIndex];
        if (!tr) return;
        const badge = tr.querySelector(".batch-status");
        if (badge) {
            badge.className = `batch-status ${status}`;
            badge.textContent = status.toUpperCase();
        }
        tr.className = status;
    }

    loadBatchQueue = async function() {
        try {
            const d = await fetch("/api/queue").then(r => r.json());
            const content = d.content || "";
            if (batchBody) {
                batchBody.innerHTML = "";
                content.split("\n").forEach(line => {
                    line = line.trim();
                    if (!line || line.startsWith("#")) return;
                    const [urlPart, ...rest] = line.split("#");
                    const url   = urlPart.trim();
                    const title = rest.join("#").trim();
                    if (url) addBatchRow(url, "shorts_blur", title);
                });
            }
            syncBatchMeta();
        } catch (e) { console.error("Falha ao ler queue:", e); }
    }

    // Add row
    const btnAddRow = document.getElementById("btnAddRow");
    if (btnAddRow) btnAddRow.addEventListener("click", () => {
        addBatchRow();
        // Focus last URL input
        if (batchBody) {
            const rows = batchBody.querySelectorAll("tr");
            rows[rows.length - 1]?.querySelector("input")?.focus();
        }
    });

    // Purge all
    const btnPurgeAll = document.getElementById("btnPurgeAll");
    if (btnPurgeAll) btnPurgeAll.addEventListener("click", () => {
        if (!confirm("Limpar todos os jobs da fila?")) return;
        if (batchBody) batchBody.innerHTML = "";
        syncBatchMeta();
    });

    // Export list
    const btnExportList = document.getElementById("btnExportList");
    if (btnExportList) btnExportList.addEventListener("click", async () => {
        const lines = ["# Lista gerada pelo Viral Cutter"];
        if (batchBody) {
            batchBody.querySelectorAll("tr").forEach(tr => {
                const url   = tr.cells[1]?.querySelector("input")?.value.trim();
                const title = tr.cells[3]?.querySelector("input")?.value.trim();
                if (url) lines.push(title ? `${url} # ${title}` : url);
            });
        }
        const content = lines.join("\n");
        try {
            const res = await fetch("/api/queue", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ action: "save", content }),
            });
            const d = await res.json();
            if (d.status === "success") alert("list.txt exportado!");
        } catch (e) { alert(`Falha: ${e.message}`); }
    });

    // Import list
    const btnImportList = document.getElementById("btnImportList");
    if (btnImportList) btnImportList.addEventListener("click", async () => {
        try {
            const d = await fetch("/api/queue").then(r => r.json());
            const content = d.content || "";
            content.split("\n").forEach(line => {
                line = line.trim();
                if (!line || line.startsWith("#")) return;
                const [urlPart, ...rest] = line.split("#");
                const url = urlPart.trim(), title = rest.join("#").trim();
                if (url) addBatchRow(url, "shorts_blur", title);
            });
            syncBatchMeta();
        } catch (e) { alert(`Falha ao importar: ${e.message}`); }
    });

    // Channel ops (batch panel)
    const btnPlaywrightLogin2 = document.getElementById("btnPlaywrightLogin2");
    if (btnPlaywrightLogin2) btnPlaywrightLogin2.addEventListener("click", async () => {
        const profileIndex = parseInt(document.getElementById("batchManageProfile")?.value || 0);
        log("[PLAYWRIGHT] Chamando navegador Chromium...", "log-info");
        switchTab("monitor");
        try {
            const d = await fetch("/api/playwright/login", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ profile_index: profileIndex }),
            }).then(r => r.json());
            if (d.status === "success") log("[PLAYWRIGHT] Browser lançado. Faça login e feche a janela.", "log-ok");
            else alert(d.message);
        } catch (e) { alert(`Falha: ${e.message}`); }
    });

    const btnPlaywrightReset2 = document.getElementById("btnPlaywrightReset2");
    if (btnPlaywrightReset2) btnPlaywrightReset2.addEventListener("click", async () => {
        if (!confirm("Apagar todos os cookies desta conta?")) return;
        const profileIndex = parseInt(document.getElementById("batchManageProfile")?.value || 0);
        try {
            const d = await fetch("/api/playwright/reset", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ profile_index: profileIndex }),
            }).then(r => r.json());
            if (d.status === "success") alert("Sessão resetada!"); else alert(d.message);
        } catch (e) { alert(e.message); }
    });

    // Override startTask for batch to pass jobs from table
    const btnStartBatch = document.getElementById("btnStartBatch");
    if (btnStartBatch) btnStartBatch.addEventListener("click", async () => {
        const jobs = getBatchJobs();
        if (!jobs.length) { alert("Adicione pelo menos um URL à fila."); return; }
        await saveSystemConfig(true);
        try {
            const res = await fetch("/api/start", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    task_type: "batch",
                    jobs,
                    upload_youtube: document.getElementById("batchCheckUpload")?.checked,
                    use_playwright: document.querySelector('[name="batchUploadMethod"]:checked')?.value === "playwright",
                    youtube_profile_index: parseInt(document.getElementById("batchYtProfile")?.value || 0),
                    schedule_hrs: parseInt(document.getElementById("batchScheduleHrs")?.value || 0),
                }),
            });
            const d = await res.json();
            if (d.status === "success") {
                clearLog();
                log(`[SISTEMA] Batch iniciado — ${jobs.length} job(s) na fila.`, "log-warn");
                startSSE();
                switchTab("monitor");
            } else { alert(`Erro: ${d.message}`); }
        } catch (e) { alert(`Falha: ${e.message}`); }
    });

    // Populate batch profile selects
    syncBatchProfileSelects = function(profiles, activeIndex) {
        ["batchYtProfile", "batchManageProfile"].forEach(selId => {
            const sel = document.getElementById(selId);
            if (!sel) return;
            sel.innerHTML = "";
            profiles.forEach((p, i) => {
                const opt = Object.assign(document.createElement("option"), {
                    value: i, textContent: p.name, selected: i === activeIndex,
                });
                sel.appendChild(opt);
            });
        });
    }

    // ── Niche Explorer ─────────────────────────────────────────────────────
    const nicheBody = document.getElementById("nicheTableBody");
    let activeNicheRow = null, selectedNicheId = null;

    loadNicheCategories = async function() {
        try {
            const d = await fetch("/api/niche/categories").then(r => r.json());
            if (nicheBody) {
                nicheBody.innerHTML = "";
                d.categories.forEach(n => {
                    const tr = document.createElement("tr");
                    tr.innerHTML = `
                        <td style="font-family:var(--mono);color:var(--amber)">${n.id}</td>
                        <td style="font-weight:600">${n.name}</td>
                        <td style="color:${n.pay.includes("Very") ? "var(--green)" : "var(--text-2)"}">${n.pay}</td>
                        <td style="color:${n.viral.includes("Extremely") ? "var(--red)" : "var(--amber)"}">${n.viral}</td>
                    `;
                    tr.addEventListener("click", () => {
                        if (activeNicheRow) activeNicheRow.classList.remove("active");
                        tr.classList.add("active");
                        activeNicheRow = tr;
                        selectedNicheId = n.id;
                    });
                    nicheBody.appendChild(tr);
                });
            }
        } catch (e) { console.error("Falha ao carregar nichos:", e); }
    }

    const cardNicheResults = document.getElementById("cardNicheResults");
    const nicheVideosList  = document.getElementById("nicheVideosList");
    const checkAll         = document.getElementById("checkSelectAllNicheVideos");

    const btnConnectNiche = document.getElementById("btnConnectNiche");
    if (btnConnectNiche) btnConnectNiche.addEventListener("click", async () => {
        if (!selectedNicheId) { alert("Selecione um nicho primeiro."); return; }
        const region = document.getElementById("selectNicheRegion")?.value || "BR";
        const count  = parseInt(document.getElementById("selectNicheCount")?.value || 10);
        if (nicheVideosList) nicheVideosList.innerHTML = `<li class="video-item"><span style="color:var(--amber);font-family:var(--mono);font-size:12px">Varrendo APIs do YouTube...</span></li>`;
        if (cardNicheResults) {
            cardNicheResults.style.display = "block";
            cardNicheResults.scrollIntoView({ behavior: "smooth" });
        }
        try {
            const d = await fetch("/api/niche/search", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ region, category_id: selectedNicheId, count }),
            }).then(r => r.json());
            if (nicheVideosList) {
                nicheVideosList.innerHTML = "";
                if (d.status === "success" && d.videos?.length) {
                    d.videos.forEach(v => {
                        const li = document.createElement("li");
                        li.className = "video-item";
                        li.innerHTML = `
                            <label class="check-label">
                                <input type="checkbox" class="check-input niche-video-check" data-url="${v.url}" data-title="${v.title}" data-channel="${v.channel}" checked>
                                <span class="check-box"></span>
                            </label>
                            <div class="video-info">
                                <div class="video-title-text">${v.title}</div>
                                <div class="video-meta">${v.channel.toUpperCase()} &nbsp;|&nbsp; <a href="${v.url}" target="_blank">abrir ↗</a></div>
                            </div>
                        `;
                        nicheVideosList.appendChild(li);
                    });
                } else {
                    nicheVideosList.innerHTML = `<li class="video-item" style="color:var(--red);font-family:var(--mono);font-size:12px">Nenhum vídeo encontrado.</li>`;
                }
            }
        } catch (e) {
            if (nicheVideosList) nicheVideosList.innerHTML = `<li class="video-item" style="color:var(--red)">Falha: ${e.message}</li>`;
        }
    });

    if (checkAll) checkAll.addEventListener("change", () => {
        document.querySelectorAll(".niche-video-check").forEach(c => c.checked = checkAll.checked);
    });

    const btnAppendSelectedToQueue = document.getElementById("btnAppendSelectedToQueue");
    if (btnAppendSelectedToQueue) btnAppendSelectedToQueue.addEventListener("click", async () => {
        const boxes = [...document.querySelectorAll(".niche-video-check:checked")];
        if (!boxes.length) { alert("Nenhum vídeo selecionado."); return; }
        const videos = boxes.map(b => ({
            url: b.dataset.url, title: b.dataset.title, channel: b.dataset.channel,
        }));
        try {
            const d = await fetch("/api/niche/add", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ videos }),
            }).then(r => r.json());
            if (d.status === "success") {
                alert(`${d.added_count} vídeos adicionados à fila!`);
                if (cardNicheResults) cardNicheResults.style.display = "none";
            } else alert(`Erro: ${d.message}`);
        } catch (e) { alert(`Falha: ${e.message}`); }
    });

    // ── Playwright ─────────────────────────────────────────────────────────
    const btnPlaywrightLogin = document.getElementById("btnPlaywrightLogin");
    if (btnPlaywrightLogin) btnPlaywrightLogin.addEventListener("click", async () => {
        const idx = parseInt(document.getElementById("selectManageProfile")?.value || 0);
        log("[PLAYWRIGHT] Chamando navegador Chromium...", "log-info");
        switchTab("monitor");
        try {
            const d = await fetch("/api/playwright/login", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ profile_index: idx }),
            }).then(r => r.json());
            if (d.status === "success") log("[PLAYWRIGHT] Browser lançado. Faça login e feche a janela.", "log-ok");
            else alert(d.message);
        } catch (e) { alert(`Falha: ${e.message}`); }
    });

    const btnPlaywrightReset = document.getElementById("btnPlaywrightReset");
    if (btnPlaywrightReset) btnPlaywrightReset.addEventListener("click", async () => {
        if (!confirm("Apagar todos os cookies desta conta?")) return;
        const idx = parseInt(document.getElementById("selectManageProfile")?.value || 0);
        try {
            const d = await fetch("/api/playwright/reset", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ profile_index: idx }),
            }).then(r => r.json());
            if (d.status === "success") alert("Sessão resetada!");
            else alert(d.message);
        } catch (e) { alert(e.message); }
    });

    // ── Gallery ────────────────────────────────────────────────────────────
    loadResultsGallery = async function() {
        try {
            const d = await fetch("/api/status").then(r => r.json());
            const cuts = d.results || [];
            const gallery = document.getElementById("cardGallery");
            const grid    = document.getElementById("galleryGrid");
            if (!cuts.length) { if (gallery) gallery.style.display = "none"; return; }
            if (gallery) gallery.style.display = "block";
            if (grid) {
                grid.innerHTML = "";
                cuts.forEach(cut => {
                    const filename = cut.file?.split(/[\\/]/).pop() || "corte.mp4";
                    const item = document.createElement("div");
                    item.className = "gallery-item";
                    item.innerHTML = `
                        <h4>${filename}</h4>
                        <p>SCORE: ${cut.final_score?.toFixed(0) ?? "N/A"}</p>
                        <p>TIMING: ${cut.start?.toFixed(0) ?? 0}s — ${cut.end?.toFixed(0) ?? 0}s</p>
                        <a href="file://${cut.file}" class="btn btn-ghost btn-sm" target="_blank" style="text-decoration:none;justify-content:center;">↗ LOCALIZAR</a>
                    `;
                    grid.appendChild(item);
                });
            }
        } catch (e) { console.error("Falha na galeria:", e); }
    }

    // ── Init ───────────────────────────────────────────────────────────────
    async function init() {
        await loadSystemConfig();
        startSSE();
        toggleOllamaFields();
        toggleWatermarkFields();
    }
    init();
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
    console.log(`[Nav] Tentando acessar aba: ${tabId}`);

    // 1. Mapeamento de nomes amigáveis/antigos para IDs internos do Attention OS
    const mapping = {
        "Corte E viral": "factory",
        "corte-viral": "factory",
        "renderização": "batch",
        "renderizacao": "batch",
        "branding": "config",
        "parametros": "config",
        "canais e contas": "youtube",
        "canais-e-contas": "youtube",
        "canais": "youtube"
    };

    // Normaliza o ID usando o mapeamento ou o próprio ID se não houver alias
    const targetId = mapping[tabId] || tabId;
    console.log(`[Nav] ID interno resolvido: ${targetId}`);

    // 2. Esconder todos os painéis (.panel ou .tab-content conforme o HTML)
    const allPanels = document.querySelectorAll('.panel');
    allPanels.forEach(panel => panel.classList.remove('active'));

    // 3. Mostrar o painel alvo (Tenta com o ID resolvido)
    const targetPanel = document.getElementById(`panel-${targetId}`);
    if (targetPanel) {
        targetPanel.classList.add('active');
    } else {
        console.error(`[Nav] Painel não encontrado: panel-${targetId}`);
    }

    // 4. Atualizar estado visual dos botões de navegação
    const navBtns = Array.from(document.querySelectorAll('.nav-btn[data-tab]'));
    navBtns.forEach(btn => btn.classList.remove('active'));
    
    // Procura o botão pelo tabId original ou pelo targetId
    const activeBtn = navBtns.find(btn => 
        btn.getAttribute('data-tab') === tabId || btn.getAttribute('data-tab') === targetId
    );
    if (activeBtn) activeBtn.classList.add('active');
    
    // 5. Gatilhos de carregamento de dados (Restaurados do código que funcionava)
    if (targetId === 'factory' || targetId === 'ops') {
        startFactoryPolling();
        startOpsSSE();
        hydrateInitialOnce();
    } else {
        stopFactoryPolling();
        stopOpsSSE();
    }

    if (targetId === 'batch') loadBatchQueue();
    if (targetId === 'niche') loadNicheCategories();
    if (targetId === 'config') loadSystemConfig();
    if (targetId === 'youtube') loadYoutubeProfiles();
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
    
    // Log para debug
    // console.log("[projectEntity] id:", id, "type:", type, "lastPatch:", p);

    // Se o job está cancelado/concluído (e já enviado), remover da UI
    if (type === "job" && p.status && p.upload_status) {
        const normalizedStatus = String(p.status).toLowerCase().trim();
        const normalizedUploadStatus = String(p.upload_status).toLowerCase().trim();
        console.log("[projectEntity] normalizedStatus:", normalizedStatus, "normalizedUploadStatus:", normalizedUploadStatus);
        if (["cancelled", "failed"].includes(normalizedStatus)) {
            console.log("[projectEntity] Removendo node (status cancelado/falhou):", id);
            if (node && node.parentNode) {
                node.parentNode.removeChild(node);
                window.__AttentionOS.runtime.nodes.delete(id);
                window.__AttentionOS.runtime.meta.delete(id);
            }
            return;
        }
        if (["done", "completed"].includes(normalizedStatus) && ["uploaded", "failed"].includes(normalizedUploadStatus)) {
            console.log("[projectEntity] Removendo node (concluído e upload finalizado):", id);
            if (node && node.parentNode) {
                node.parentNode.removeChild(node);
                window.__AttentionOS.runtime.nodes.delete(id);
                window.__AttentionOS.runtime.meta.delete(id);
            }
            return;
        }
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
                        <span style="margin-left:12px;">Upload: <span class="job-upload-status" style="color: var(--text-2);">${p.upload_status || 'PENDING'}</span></span>
                    </div>
                </div>
                <div style="display:flex; flex-direction:column; align-items:flex-end; gap:4px;">
                    <div class="job-status-badge status-${p.status ? p.status.toLowerCase() : 'pending'}" style="font-size:11px; padding:4px 10px;">
                        ${p.status ? p.status.toUpperCase() : 'PENDING'}
                    </div>
                    <div class="action-group" style="display:flex; gap:4px;">
                        <button class="btn-action success btn-retry hidden" data-action="retry" data-id="${id}">RETRY</button>
                        <button class="btn-action" data-action="pause" data-id="${id}" style="font-size:11px; padding:4px 8px;">PAUSE</button>
                        <button class="btn-action danger" data-action="cancel" data-id="${id}" style="font-size:11px; padding:4px 8px;">CANCEL</button>
                    </div>
                </div>
            </div>
            <div style="display:flex; flex-direction:column; gap:6px;">
                <div style="display:flex; justify-content:space-between; font-family:var(--mono); font-size:11px; color: var(--text-3);">
                    <span>Progresso: <span class="job-progress-text">${p.progress ? (p.progress * 100).toFixed(0) + '%' : '0%'}</span></span>
                    <span>ETA: <span class="job-eta">${p.eta ? p.eta + 's' : '—'}</span></span>
                </div>
                <div style="width:100%; height:8px; background: var(--bg2); border: 1px solid var(--border);">
                    <div class="job-progress-bar" style="width:${p.progress ? (p.progress * 100).toFixed(0) + '%' : '0%'}; height:100%; background: var(--green); transition: width 0.3s ease;"></div>
                </div>
            </div>
            ${p.uploaded_video_id ? `<div style="font-size:11px; color: var(--green);">YouTube ID: ${p.uploaded_video_id}</div>` : ''}
            ${p.upload_error ? `<div style="font-size:11px; color: var(--red);">Upload Error: ${p.upload_error}</div>` : ''}
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
                <button class="btn-action danger" data-action="delete-trend" data-id="${id}">DELETE</button>
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
        const retryBtn = node.querySelector('.btn-retry');
        const progressText = node.querySelector('.job-progress-text');
        const progressBar = node.querySelector('.job-progress-bar');
        const eta = node.querySelector('.job-eta');
        const uploadStatus = node.querySelector('.job-upload-status');
        const metaDiv = node.querySelector('.job-meta');

        if (p.video_id) title.textContent = p.video_id;
        if (p.status) {
            badge.className = `job-status-badge status-${p.status.toLowerCase()}`;
            badge.textContent = p.status.toUpperCase();
            if (retryBtn) {
                // Só mostra retry se falhou
                if (p.status.toUpperCase() === "FAILED") retryBtn.classList.remove('hidden');
                else retryBtn.classList.add('hidden');
            }
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
        if (p.upload_status && uploadStatus) {
            uploadStatus.textContent = p.upload_status.toUpperCase();
            if (p.upload_status.toUpperCase() === "UPLOADING") {
                uploadStatus.style.color = "var(--amber)";
            } else if (p.upload_status.toUpperCase() === "UPLOADED") {
                uploadStatus.style.color = "var(--green)";
            } else if (p.upload_status.toUpperCase() === "FAILED") {
                uploadStatus.style.color = "var(--red)";
            } else {
                uploadStatus.style.color = "var(--text-2)";
            }
        }

        // Atualizar ou adicionar YouTube ID e upload error
        let youtubeIdEl = node.querySelector('.upload-youtube-id');
        let uploadErrorEl = node.querySelector('.upload-error');

        if (p.uploaded_video_id) {
            if (!youtubeIdEl) {
                youtubeIdEl = document.createElement('div');
                youtubeIdEl.className = 'upload-youtube-id';
                youtubeIdEl.style.fontSize = '11px';
                youtubeIdEl.style.color = 'var(--green)';
                node.appendChild(youtubeIdEl);
            }
            youtubeIdEl.textContent = `YouTube ID: ${p.uploaded_video_id}`;
        } else if (youtubeIdEl) {
            youtubeIdEl.remove();
        }

        if (p.upload_error) {
            if (!uploadErrorEl) {
                uploadErrorEl = document.createElement('div');
                uploadErrorEl.className = 'upload-error';
                uploadErrorEl.style.fontSize = '11px';
                uploadErrorEl.style.color = 'var(--red)';
                node.appendChild(uploadErrorEl);
            }
            uploadErrorEl.textContent = `Upload Error: ${p.upload_error}`;
        } else if (uploadErrorEl) {
            uploadErrorEl.remove();
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

/**
 * Injeta visualmente a lista de títulos gerados no card do Job
 */
function renderGeneratedTitles(node, payload) {
    let container = node.querySelector('.generated-titles-area');
    
    // Se não existir o container de títulos no card, cria um
    if (!container) {
        container = document.createElement('div');
        container.className = 'generated-titles-area';
        container.style.marginTop = '12px';
        container.style.padding = '10px';
        container.style.background = 'var(--bg1)';
        container.style.borderTop = '1px solid var(--border)';
        node.appendChild(container);
    }

    const titles = payload.titles || [];
    const best = payload.best_title;

    container.innerHTML = `
        <div style="font-size:10px; color:var(--amber); margin-bottom:8px; font-family:var(--mono);">💡 ATTENTION_TITLE_ENGINE // V1.0</div>
        <div class="titles-list" style="display:flex; flex-direction:column; gap:6px;">
            ${titles.slice(0, 5).map((t, i) => `
                <div style="display:flex; justify-content:space-between; align-items:center; font-size:12px; background:rgba(255,255,255,0.03); padding:4px 8px;">
                    <span style="color:${t.text === best ? 'var(--green)' : 'var(--text-1)'}">${i+1}. ${t.text}</span>
                    <div style="display:flex; gap:10px; align-items:center;">
                        <span style="font-size:10px; color:var(--text-3); font-family:var(--mono);">SC:${(t.score*100).toFixed(0)}</span>
                        <button class="btn-copy-title" data-text="${t.text}" style="background:none; border:1px solid var(--border); color:var(--text-2); font-size:9px; cursor:pointer; padding:2px 6px;">COPY</button>
                    </div>
                </div>
            `).join('')}
        </div>
    `;
}

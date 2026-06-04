/* ==========================================================================
   VIRAL CUTTER PRO // FRONTEND ENGINE (VANILLA JS)
   ========================================================================== */

document.addEventListener("DOMContentLoaded", () => {
    let activeSSE = null;
    let availableProfiles = [];

    // ── Tab Manager ────────────────────────────────────────────────────────
    const navBtns = document.querySelectorAll(".nav-btn");
    const panels  = document.querySelectorAll(".panel");

    function switchTab(tabId) {
        navBtns.forEach(b => b.classList.remove("active"));
        panels.forEach(p => p.classList.remove("active"));
        const btn   = document.querySelector(`.nav-btn[data-tab="${tabId}"]`);
        const panel = document.getElementById(`panel-${tabId}`);
        if (btn)   btn.classList.add("active");
        if (panel) panel.classList.add("active");
        if (tabId === "batch") loadBatchQueue();
        if (tabId === "niche") loadNicheCategories();
    }

    navBtns.forEach(b => b.addEventListener("click", () => switchTab(b.dataset.tab)));

    // ── Clock ──────────────────────────────────────────────────────────────
    function tick() {
        const d = new Date();
        document.getElementById("terminalTime").textContent =
            [d.getHours(), d.getMinutes(), d.getSeconds()]
                .map(n => String(n).padStart(2, "0")).join(":");
    }
    setInterval(tick, 1000);
    tick();

    // ── Config load / save ─────────────────────────────────────────────────
    async function loadSystemConfig() {
        try {
            const cfg = await fetch("/api/config").then(r => r.json());
            const g = id => document.getElementById(id);

            g("inputVideoPath").value     = cfg.input || "";
            g("selectPreset").value       = cfg.preset || "auto_detect";
            g("checkUploadYoutube").checked = cfg.upload_youtube || false;
            g("checkUsePlaywright").checked = cfg.use_playwright || false;

            g("selectWhisperModel").value   = cfg.whisper_model || "medium";
            g("selectDevice").value         = cfg.device || "cpu";
            g("selectAnalysisEngine").value = cfg.analysis_engine || "heuristic";
            g("inputOllamaModel").value     = cfg.model || "llama3";

            g("inputTopN").value        = cfg.top_n || 10;
            g("inputMinScore").value    = cfg.min_score || 40;
            g("inputMinDuration").value = cfg.min_duration || 20;
            g("inputMaxDuration").value = cfg.max_duration || 65;
            g("checkAutoFrame").checked = cfg.auto_frame || false;

            g("selectWatermarkMode").value     = cfg.watermark_mode || "none";
            g("inputWatermarkText").value      = cfg.watermark_text || "";
            g("inputWatermarkImage").value     = cfg.watermark_image || "";
            g("selectWatermarkPosition").value = cfg.watermark_position || "bottom_right";

            g("selectSubtitleStyle").value = cfg.subtitle_style || "high_impact";
            g("selectVisualFilter").value  = cfg.visual_filter || "none";
            g("inputBgMusic").value        = cfg.bg_music || "";
            g("inputBgMusicVolume").value  = cfg.bg_music_volume || 0.15;

            toggleOllamaFields();
            toggleWatermarkFields();
            await loadYoutubeProfiles(cfg.youtube_profile_index);
        } catch (e) {
            log(`[ERRO] Falha ao ler configurações: ${e.message}`, "log-err");
        }
    }

    async function saveSystemConfig(silent = false) {
        const v = id => document.getElementById(id).value;
        const c = id => document.getElementById(id).checked;
        const config = {
            input: v("inputVideoPath"),
            preset: v("selectPreset"),
            upload_youtube: c("checkUploadYoutube"),
            use_playwright: c("checkUsePlaywright"),
            youtube_profile_index: parseInt(v("selectYtProfile") || 0),
            whisper_model: v("selectWhisperModel"),
            device: v("selectDevice"),
            analysis_engine: v("selectAnalysisEngine"),
            model: v("inputOllamaModel"),
            top_n: parseInt(v("inputTopN")),
            min_score: parseFloat(v("inputMinScore")),
            min_duration: parseFloat(v("inputMinDuration")),
            max_duration: parseFloat(v("inputMaxDuration")),
            auto_frame: c("checkAutoFrame"),
            watermark_mode: v("selectWatermarkMode"),
            watermark_text: v("inputWatermarkText"),
            watermark_image: v("inputWatermarkImage"),
            watermark_position: v("selectWatermarkPosition"),
            subtitle_style: v("selectSubtitleStyle"),
            visual_filter: v("selectVisualFilter"),
            bg_music: v("inputBgMusic"),
            bg_music_volume: parseFloat(v("inputBgMusicVolume")),
        };
        try {
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
    function toggleOllamaFields() {
        document.getElementById("ollamaWrapper").style.display =
            selectAnalysisEngine.value === "ollama" ? "block" : "none";
    }
    selectAnalysisEngine.addEventListener("change", toggleOllamaFields);

    const selectWatermarkMode = document.getElementById("selectWatermarkMode");
    function toggleWatermarkFields() {
        const m = selectWatermarkMode.value;
        document.getElementById("watermarkTextWrapper").style.display =
            m === "text" || m === "both" ? "block" : "none";
        document.getElementById("watermarkImageWrapper").style.display =
            m === "image" || m === "both" ? "block" : "none";
    }
    selectWatermarkMode.addEventListener("change", toggleWatermarkFields);

    document.getElementById("btnSaveConfig").addEventListener("click", () => saveSystemConfig());

    // ── YouTube profiles ───────────────────────────────────────────────────
    async function loadYoutubeProfiles(activeIndex = 0) {
        try {
            const data = await fetch("/api/youtube/profiles").then(r => r.json());
            availableProfiles = data.profiles || [];
            ["selectYtProfile", "selectManageProfile"].forEach(selId => {
                const sel = document.getElementById(selId);
                if (!sel) return;
                sel.innerHTML = "";
                availableProfiles.forEach((p, i) => {
                    const opt = Object.assign(document.createElement("option"), {
                        value: i, textContent: p.name, selected: i === activeIndex,
                    });
                    sel.appendChild(opt);
                });
            });
            // Also populate batch panel profile selects
            syncBatchProfileSelects(availableProfiles, activeIndex);
        } catch (e) {
            console.error("Falha ao ler perfis:", e);
        }
    }

    // ── Task execution ─────────────────────────────────────────────────────
    async function startTask(taskType, extraData = {}) {
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

    document.getElementById("btnStartPipeline").addEventListener("click", () => startTask("pipeline"));
    document.getElementById("btnDownloadYoutube").addEventListener("click", () => {
        const url = document.getElementById("youtubeUrlInput").value.trim();
        if (!url) { alert("Insira uma URL do YouTube."); return; }
        startTask("download", { url });
    });

    // ── SSE ────────────────────────────────────────────────────────────────
    function startSSE() {
        if (activeSSE) activeSSE.close();
        activeSSE = new EventSource("/stream");
        activeSSE.onmessage = e => {
            const d = JSON.parse(e.data);
            if (d.type === "log")    log(d.msg);
            if (d.type === "status") updateProgress(d.percent, d.msg, d.active_task);
        };
        activeSSE.onerror = () => console.warn("SSE error — reconnecting...");
    }

    function updateProgress(percent, text, activeTask) {
        const chip   = document.getElementById("globalStatusIndicator");
        const chipTx = document.getElementById("globalStatusText");
        if (activeTask !== "none") {
            chip.className = "status-dot running";
            chipTx.textContent = text.toUpperCase();
        } else {
            chip.className = "status-dot";
            chipTx.textContent = "SISTEMA PRONTO";
        }
        document.getElementById("monitorStatusText").textContent = `STATUS: ${text.toUpperCase()}`;
        document.getElementById("monitorPercentText").textContent = `${percent}%`;
        document.getElementById("monitorProgressBar").style.width = `${percent}%`;
        if (activeTask === "none" && percent === 100) loadResultsGallery();
    }

    // ── Terminal log ───────────────────────────────────────────────────────
    const terminalOutput = document.getElementById("terminalOutput");

    function log(text, cls = "") {
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

    function clearLog() { terminalOutput.innerHTML = ""; }
    document.getElementById("btnClearLog").addEventListener("click", clearLog);

    // ── Batch Queue (Table) ────────────────────────────────────────────────
    const batchBody   = document.getElementById("batchTableBody");
    const batchEmpty  = document.getElementById("batchEmpty");
    const batchCount  = document.getElementById("batchRowCount");
    const PRESETS     = ["auto_detect","shorts_blur","podcast_split","tiktok","reels","shorts","landscape","square","social_frame"];

    function syncBatchMeta() {
        const n = batchBody.querySelectorAll("tr").length;
        batchCount.textContent = `${n} job${n !== 1 ? "s" : ""}`;
        batchEmpty.classList.toggle("hidden", n > 0);
    }

    function addBatchRow(url = "", preset = "shorts_blur", title = "", status = "pending") {
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

    function renumberBatchRows() {
        batchBody.querySelectorAll("tr").forEach((tr, i) => {
            const numCell = tr.querySelector(".col-num");
            if (numCell) numCell.textContent = i + 1;
        });
    }

    function getBatchJobs() {
        const jobs = [];
        batchBody.querySelectorAll("tr").forEach(tr => {
            const url    = tr.cells[1]?.querySelector("input")?.value.trim() || "";
            const preset = tr.cells[2]?.querySelector("select")?.value || "auto_detect";
            const title  = tr.cells[3]?.querySelector("input")?.value.trim() || "";
            if (url) jobs.push({ url, preset, title_prefix: title });
        });
        return jobs;
    }

    function setRowStatus(rowIndex, status) {
        const tr = batchBody.children[rowIndex];
        if (!tr) return;
        const badge = tr.querySelector(".batch-status");
        if (badge) {
            badge.className = `batch-status ${status}`;
            badge.textContent = status.toUpperCase();
        }
        tr.className = status;
    }

    async function loadBatchQueue() {
        try {
            const d = await fetch("/api/queue").then(r => r.json());
            const content = d.content || "";
            batchBody.innerHTML = "";
            content.split("\n").forEach(line => {
                line = line.trim();
                if (!line || line.startsWith("#")) return;
                const [urlPart, ...rest] = line.split("#");
                const url   = urlPart.trim();
                const title = rest.join("#").trim();
                if (url) addBatchRow(url, "shorts_blur", title);
            });
            syncBatchMeta();
        } catch (e) { console.error("Falha ao ler queue:", e); }
    }

    // Add row
    document.getElementById("btnAddRow").addEventListener("click", () => {
        addBatchRow();
        // Focus last URL input
        const rows = batchBody.querySelectorAll("tr");
        rows[rows.length - 1]?.querySelector("input")?.focus();
    });

    // Purge all
    document.getElementById("btnPurgeAll").addEventListener("click", () => {
        if (!confirm("Limpar todos os jobs da fila?")) return;
        batchBody.innerHTML = "";
        syncBatchMeta();
    });

    // Export list
    document.getElementById("btnExportList").addEventListener("click", async () => {
        const lines = ["# Lista gerada pelo Viral Cutter"];
        batchBody.querySelectorAll("tr").forEach(tr => {
            const url   = tr.cells[1]?.querySelector("input")?.value.trim();
            const title = tr.cells[3]?.querySelector("input")?.value.trim();
            if (url) lines.push(title ? `${url} # ${title}` : url);
        });
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
    document.getElementById("btnImportList").addEventListener("click", async () => {
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
    document.getElementById("btnPlaywrightLogin2")?.addEventListener("click", async () => {
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

    document.getElementById("btnPlaywrightReset2")?.addEventListener("click", async () => {
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
    document.getElementById("btnStartBatch").addEventListener("click", async () => {
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
                    upload_youtube: document.getElementById("batchCheckUpload").checked,
                    use_playwright: document.querySelector('[name="batchUploadMethod"]:checked')?.value === "playwright",
                    youtube_profile_index: parseInt(document.getElementById("batchYtProfile")?.value || 0),
                    schedule_hrs: parseInt(document.getElementById("batchScheduleHrs").value || 0),
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
    function syncBatchProfileSelects(profiles, activeIndex) {
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

    async function loadNicheCategories() {
        try {
            const d = await fetch("/api/niche/categories").then(r => r.json());
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
        } catch (e) { console.error("Falha ao carregar nichos:", e); }
    }

    const cardNicheResults = document.getElementById("cardNicheResults");
    const nicheVideosList  = document.getElementById("nicheVideosList");
    const checkAll         = document.getElementById("checkSelectAllNicheVideos");

    document.getElementById("btnConnectNiche").addEventListener("click", async () => {
        if (!selectedNicheId) { alert("Selecione um nicho primeiro."); return; }
        const region = document.getElementById("selectNicheRegion").value;
        const count  = parseInt(document.getElementById("selectNicheCount").value || 10);
        nicheVideosList.innerHTML = `<li class="video-item"><span style="color:var(--amber);font-family:var(--mono);font-size:12px">Varrendo APIs do YouTube...</span></li>`;
        cardNicheResults.style.display = "block";
        cardNicheResults.scrollIntoView({ behavior: "smooth" });
        try {
            const d = await fetch("/api/niche/search", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ region, category_id: selectedNicheId, count }),
            }).then(r => r.json());
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
        } catch (e) {
            nicheVideosList.innerHTML = `<li class="video-item" style="color:var(--red)">Falha: ${e.message}</li>`;
        }
    });

    checkAll.addEventListener("change", () => {
        document.querySelectorAll(".niche-video-check").forEach(c => c.checked = checkAll.checked);
    });

    document.getElementById("btnAppendSelectedToQueue").addEventListener("click", async () => {
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
                cardNicheResults.style.display = "none";
            } else alert(`Erro: ${d.message}`);
        } catch (e) { alert(`Falha: ${e.message}`); }
    });

    // ── Playwright ─────────────────────────────────────────────────────────
    document.getElementById("btnPlaywrightLogin").addEventListener("click", async () => {
        const idx = parseInt(document.getElementById("selectManageProfile").value || 0);
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

    document.getElementById("btnPlaywrightReset").addEventListener("click", async () => {
        if (!confirm("Apagar todos os cookies desta conta?")) return;
        const idx = parseInt(document.getElementById("selectManageProfile").value || 0);
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
    async function loadResultsGallery() {
        try {
            const d = await fetch("/api/status").then(r => r.json());
            const cuts = d.results || [];
            const gallery = document.getElementById("cardGallery");
            const grid    = document.getElementById("galleryGrid");
            if (!cuts.length) { gallery.style.display = "none"; return; }
            gallery.style.display = "block";
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
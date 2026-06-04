import re

with open("static/app.js", "r") as f:
    js = f.read()

# 1. Inject updateOrInsertNode at the top of Attention Ops logic
new_utils = """
    function updateOrInsertNode(container, selectorDataAttr, id, createFn, updateFn) {
        let node = container.querySelector(`[${selectorDataAttr}="${id}"]`);
        if (!node) {
            node = createFn();
            node.setAttribute(selectorDataAttr, id);
            container.appendChild(node);
        }
        updateFn(node);
    }
"""
js = js.replace("let opsSseUnsubs = [];", new_utils + "\n    let opsSseUnsubs = [];")

# 2. Replace _upsertTrendItem and _clearTrendListAndRebuild
trend_pattern = re.compile(r'function _upsertTrendItem\(t\).*?function _clearTrendListAndRebuild\(trends = \[\]\) \{.*?\}', re.DOTALL)

trend_replacement = """function _upsertTrendItem(t) {
        const list = document.getElementById("trend-monitor-list");
        if (!list || !t?.video_id) return;
        
        const empty = list.querySelector('.empty-state');
        if (empty) empty.remove();

        updateOrInsertNode(list, 'data-video-id', t.video_id, () => {
            const root = document.createElement("div");
            root.className = "trend-item";
            root.style.display = "flex";
            root.style.justifyContent = "space-between";
            root.style.alignItems = "center";
            
            const info = document.createElement("div");
            
            const title = document.createElement("div");
            title.className = "trend-title";
            
            const stats = document.createElement("div");
            stats.className = "trend-stats";
            
            const vph = document.createElement("span");
            vph.className = "stat-pill high";
            const acc = document.createElement("span");
            acc.className = "stat-pill med";
            const score = document.createElement("span");
            score.className = "stat-pill";
            
            stats.appendChild(vph);
            stats.appendChild(acc);
            stats.appendChild(score);
            
            info.appendChild(title);
            info.appendChild(stats);
            
            const actions = document.createElement("div");
            actions.className = "action-group";
            actions.style.display = "flex";
            actions.style.gap = "4px";
            actions.innerHTML = `
                <button class="btn-action success">+ QUEUE</button>
                <button class="btn-action">INVESTIGATE</button>
            `;
            
            root.appendChild(info);
            root.appendChild(actions);
            
            return root;
        }, (node) => {
            const title = node.querySelector('.trend-title');
            const pills = node.querySelectorAll('.stat-pill');
            if(pills.length >= 3) {
                const [vph, acc, score] = pills;
                title.textContent = t.title || t.video_id;
                vph.textContent = `VPH: ${(t.relative_vph ?? 0).toFixed(1)}x`;
                acc.textContent = `ACC: ${(t.vph_acceleration ?? 0).toFixed(1)}`;
                score.textContent = `SCORE: ${((t.final_viral_score ?? 0) * 100).toFixed(0)}`;
            }
        });
    }

    function _clearTrendListAndRebuild(trends = []) {
        const list = document.getElementById("trend-monitor-list");
        if (!list) return;

        if (!trends.length) {
            list.innerHTML = '<div class="empty-state">Aguardando sinal... <button class="btn-action" style="margin-top: 10px;">FORCE SCAN</button></div>';
            return;
        }
        
        const badge = document.getElementById("trend-count");
        if (badge) badge.textContent = `${trends.length} ACTIVE`;

        const currentIds = new Set(trends.map(t => String(t.video_id)));
        for (const child of Array.from(list.children)) {
            if (child.className.includes('empty-state')) continue;
            const id = child.getAttribute('data-video-id');
            if (id && !currentIds.has(id)) {
                child.remove();
            }
        }

        for (const t of trends) _upsertTrendItem(t);
    }"""
js = trend_pattern.sub(trend_replacement, js, count=1)


# 3. Replace _upsertJobItem and _clearJobListAndRebuild
job_pattern = re.compile(r'function _upsertJobItem\(j\).*?function _clearJobListAndRebuild\(jobs = \[\]\) \{.*?\}', re.DOTALL)

job_replacement = """function _upsertJobItem(j) {
        const list = document.getElementById("job-queue-list");
        if (!list || j?.job_id == null) return;

        const empty = list.querySelector('.empty-state');
        if (empty) empty.remove();

        updateOrInsertNode(list, 'data-job-id', String(j.job_id), () => {
            const root = document.createElement("div");
            root.className = "job-item";
            root.style.display = "flex";
            root.style.justifyContent = "space-between";
            root.style.alignItems = "center";

            const info = document.createElement("div");
            info.className = "job-info";

            const title = document.createElement("div");
            title.className = "job-title";

            const meta = document.createElement("div");
            meta.className = "job-meta";

            info.appendChild(title);
            info.appendChild(meta);

            const badge = document.createElement("div");
            badge.className = "job-status-badge";
            
            const actions = document.createElement("div");
            actions.className = "action-group";
            actions.style.display = "flex";
            actions.style.gap = "4px";
            actions.innerHTML = `
                <button class="btn-action">PAUSE</button>
                <button class="btn-action danger">CANCEL</button>
                <button class="btn-action success">PRIORITY BOOST</button>
            `;

            const rightSide = document.createElement("div");
            rightSide.style.display = "flex";
            rightSide.style.flexDirection = "column";
            rightSide.style.alignItems = "flex-end";
            rightSide.style.gap = "8px";
            rightSide.appendChild(badge);
            rightSide.appendChild(actions);

            root.appendChild(info);
            root.appendChild(rightSide);
            
            return root;
        }, (node) => {
            const title = node.querySelector('.job-title');
            const meta = node.querySelector('.job-meta');
            const badge = node.querySelector('.job-status-badge');
            
            title.textContent = j.title || j.video_id || String(j.job_id);
            const prio = (j.priority_score ?? 0);
            meta.textContent = `ID: ${j.job_id} | PRIO: ${prio.toFixed(1)}`;
            const status = String(j.status || "PENDING");
            badge.className = `job-status-badge status-${status.toLowerCase()}`;
            badge.textContent = status;
        });
    }

    function _clearJobListAndRebuild(jobs = []) {
        const list = document.getElementById("job-queue-list");
        if (!list) return;

        if (!jobs.length) {
            list.innerHTML = '<div class="empty-state">Queue is empty...</div>';
            return;
        }

        const currentIds = new Set(jobs.map(j => String(j.job_id)));
        for (const child of Array.from(list.children)) {
            if (child.className.includes('empty-state')) continue;
            const id = child.getAttribute('data-job-id');
            if (id && !currentIds.has(id)) {
                child.remove();
            }
        }

        for (const j of jobs) _upsertJobItem(j);
    }"""
js = job_pattern.sub(job_replacement, js, count=1)


# 4. Replace _renderTelemetryUpdate
telemetry_pattern = re.compile(r'function _renderTelemetryUpdate\(metric\) \{.*?\}', re.DOTALL)
telemetry_replacement = """function _renderTelemetryUpdate(metric) {
        if (!metric || !metric.metric_type) return;
        const v = metric.avg_value ?? metric.value;

        if (metric.metric_type === "render_time") {
            _setVal("sb-throughput", `${Number(v).toFixed(1)}s avg`);
        }
        if (metric.metric_type === "deduplication_savings") {
            // map deduplication to something
        }
        if (metric.metric_type === "cpu_usage") {
            _setVal("sb-cpu", `${Number(v).toFixed(0)}%`);
        }
    }"""
js = telemetry_pattern.sub(telemetry_replacement, js, count=1)

# Add pipeline count to status bar
dash_pattern = re.compile(r'_setVal\("m-throughput", `\$\{dash\.throughput_24h \|\| 0\} clips`\);', re.DOTALL)
dash_repl = """_setVal("sb-throughput", `${dash.throughput_24h || 0} clips`);
            _setVal("sb-queue", dash.queue_size || 0);
            _setVal("sb-workers", dash.active_jobs || 0);"""
js = dash_pattern.sub(dash_repl, js, count=1)


with open("static/app.js", "w") as f:
    f.write(js)

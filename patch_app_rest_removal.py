import re

with open("static/app.js", "r") as f:
    js = f.read()

# 1. Remove refreshOpsFromApiOnce, renderTelemetry, updateOpsDashboard
pattern = re.compile(r'function _renderTelemetryUpdate.*?function startOpsSSE\(\) \{', re.DOTALL)
replacement = """function _renderTelemetryUpdate(metric) {
        if (!metric || !metric.metric_type) return;
        const v = metric.avg_value ?? metric.value;

        if (metric.metric_type === "render_time") {
            _setVal("sb-throughput", `${Number(v).toFixed(1)}s avg`);
        }
        if (metric.metric_type === "cpu_usage") {
            _setVal("sb-cpu", `${Number(v).toFixed(0)}%`);
        }
        if (metric.metric_type === "active_workers") {
            _setVal("sb-workers", `${Number(v).toFixed(0)}`);
        }
        if (metric.metric_type === "queue_depth") {
            _setVal("sb-queue", `${Number(v).toFixed(0)}`);
        }
    }

    function updateOpsDashboard() {
        console.warn("REST refresh is disabled in Event Sourcing mode.");
    }

    function startOpsSSE() {"""
js = pattern.sub(replacement, js)

# 2. Update startOpsSSE to NOT fetch/build from state right away, but to let the EventBus handle it
start_sse_pattern = re.compile(r'function startOpsSSE\(\) \{.*?function stopOpsSSE\(\) \{', re.DOTALL)
start_sse_repl = """function startOpsSSE() {
        if (opsMounted) return;
        const attention = _getAttentionOS();
        if (!attention?.eventBus) return;

        opsMounted = true;

        const tl = document.getElementById("trend-monitor-list");
        if(tl) tl.innerHTML = "";
        const jl = document.getElementById("job-queue-list");
        if(jl) jl.innerHTML = "";

        // Atualizações reativas por evento
        opsSseUnsubs.push(
            attention.eventBus.on("TREND_CREATED", (payload, { id }) => {
                if (!opsMounted || !payload) return;
                const trend = { ...payload, video_id: id.replace('trend_', '') };
                _upsertTrendItem(trend);
                _setVal("val-trending", attention.store.getState().trends.size);
            })
        );

        const handleJobEvent = (payload, { id, patch }) => {
            if (!opsMounted) return;
            const uiJob = { ...payload, ...patch, job_id: id.replace('job_', '') };
            _upsertJobItem(uiJob);
            
            const counts = _computePipelineCountsFromJobs();
            _setVal("val-active", counts.active_jobs);
            _setVal("val-queue", counts.queue_size);
            _setVal("val-rendered", counts.clips_rendered);
        };

        opsSseUnsubs.push(attention.eventBus.on("JOB_QUEUED", handleJobEvent));
        opsSseUnsubs.push(attention.eventBus.on("JOB_PROGRESS", handleJobEvent));
        opsSseUnsubs.push(attention.eventBus.on("JOB_COMPLETED", handleJobEvent));
        opsSseUnsubs.push(attention.eventBus.on("JOB_ERROR", handleJobEvent));
        opsSseUnsubs.push(attention.eventBus.on("JOB_PAUSED", handleJobEvent));
        opsSseUnsubs.push(attention.eventBus.on("JOB_CANCELLED", handleJobEvent));

        opsSseUnsubs.push(
            attention.eventBus.on("SYSTEM_METRICS", (payload) => {
                if (!opsMounted) return;
                _renderTelemetryUpdate(payload);
            })
        );
    }

    function stopOpsSSE() {"""
js = start_sse_pattern.sub(start_sse_repl, js)

# 3. Modify updateOrInsertNode to include queueMicrotask or requestAnimationFrame batching
update_node_pattern = re.compile(r'function updateOrInsertNode\(container, selectorDataAttr, id, createFn, updateFn\) \{.*?\}', re.DOTALL)
update_node_repl = """
    let pendingUpdates = new Map();
    let isFlushScheduled = false;

    function flushEventBatch() {
        for (const [id, task] of pendingUpdates.entries()) {
            let node = task.container.querySelector(`[${task.selectorDataAttr}="${id}"]`);
            if (!node) {
                node = task.createFn();
                node.setAttribute(task.selectorDataAttr, id);
                task.container.appendChild(node);
            }
            task.updateFn(node);
        }
        pendingUpdates.clear();
        isFlushScheduled = false;
    }

    function updateEntity(container, selectorDataAttr, id, createFn, updateFn) {
        pendingUpdates.set(id, { container, selectorDataAttr, id, createFn, updateFn });
        if (!isFlushScheduled) {
            isFlushScheduled = true;
            requestAnimationFrame(flushEventBatch);
        }
    }
"""
js = update_node_pattern.sub(update_node_repl, js)

# 4. Replace `updateOrInsertNode` with `updateEntity` inside upsert functions
js = js.replace("updateOrInsertNode(list", "updateEntity(list")

with open("static/app.js", "w") as f:
    f.write(js)

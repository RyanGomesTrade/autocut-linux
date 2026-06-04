import re

with open("templates/index.html", "r") as f:
    html = f.read()

# Remove TIER 3
tier3_pattern = re.compile(r'<!-- TIER 3: OBSERVABILITY -->.*?</div>\s*</section>', re.DOTALL)
html = tier3_pattern.sub('</section>', html)

# Add status bar before </body>
status_bar_html = """
    <div class="bottom-status-bar" id="global-status-bar">
        <span class="status-item"><span style="color: var(--amber)">[ATTENTION OS]</span> WORKFLOW ACTIVE</span>
        <span class="status-divider">|</span>
        <span class="status-item">WORKERS: <span id="sb-workers">0</span></span>
        <span class="status-divider">|</span>
        <span class="status-item">QUEUE DEPTH: <span id="sb-queue">0</span></span>
        <span class="status-divider">|</span>
        <span class="status-item">CPU: <span id="sb-cpu">--%</span></span>
        <span class="status-divider">|</span>
        <span class="status-item">WHISPER: <span id="sb-whisper" style="color: var(--green);">IDLE</span></span>
        <span class="status-divider">|</span>
        <span class="status-item">THROUGHPUT: <span id="sb-throughput">0</span></span>
    </div>
</body>
"""
if '<div class="bottom-status-bar"' not in html:
    html = html.replace('</body>', status_bar_html)

with open("templates/index.html", "w") as f:
    f.write(html)

import re

with open("static/style.css", "r") as f:
    css = f.read()

# 1. Update variables
css = css.replace("--bg0: #0b0c0f;", "--bg0: #000000;")
css = css.replace("--bg1: #111318;", "--bg1: #0A0A0A;")
css = css.replace("--bg2: #181b22;", "--bg2: #141414;")
css = css.replace("--bg3: #1f222b;", "--bg3: #1A1A1A;")

css = css.replace("--amber-glow: rgba(232, 165, 0, 0.06);", "--amber-glow: transparent;")

css = css.replace("--r-sm: 4px;", "--r-sm: 0px;")
css = css.replace("--r-md: 8px;", "--r-md: 0px;")
css = css.replace("--r-lg: 12px;", "--r-lg: 0px;")

css = css.replace("--text-1: #e8eaf0;", "--text-1: #e0e0e0;")
css = css.replace("--text-2: #8891a4;", "--text-2: #888888;")
css = css.replace("--text-3: #4e5768;", "--text-3: #444444;")

# 2. Top bar
css = css.replace("background: rgba(11,12,15,0.85);", "background: var(--bg0);")
css = css.replace("backdrop-filter: blur(16px);", "")

# 3. Sidebar
css = css.replace("background: rgba(11,12,15,0.60);", "background: var(--bg1);")

# 4. Cards
css = css.replace("background: rgba(17,19,24,0.80);", "background: var(--bg0);")
css = css.replace("backdrop-filter: blur(8px);", "")
css = css.replace("padding: 20px 18px;", "padding: 10px 14px;")

css = css.replace("background: rgba(0,0,0,0.2);", "background: var(--bg1);")
css = css.replace("padding: 12px 18px;", "padding: 6px 12px;")

# 5. Buttons (remove shimmer and gradients)
css = css.replace("box-shadow: 0 6px 20px var(--amber-dim);", "box-shadow: none;")
css = re.sub(r'\.btn-shimmer \{.*?\.btn-primary:hover \.btn-shimmer \{ transform: translateX\(100\%\); \}', '', css, flags=re.DOTALL)

# 6. Progress bar
css = css.replace("background: linear-gradient(90deg, rgba(34,197,94,0.9), rgba(245,158,11,0.9));", "background: var(--amber);")
css = css.replace("box-shadow: 0 0 20px rgba(245,158,11,0.08);", "box-shadow: none;")
css = css.replace("background: linear-gradient(90deg, #c47d00, var(--amber));", "background: var(--amber);")

# 7. Timeline legend glow
css = css.replace("box-shadow: 0 0 18px rgba(255,255,255,0.04);", "")
css = css.replace("box-shadow: 0 0 0 3px var(--amber-dim);", "outline: 1px solid var(--amber);")

# 8. Background grid (make it barely visible)
css = css.replace("opacity: 0.5;", "opacity: 0.15;")
css = css.replace("background: linear-gradient(90deg, transparent, rgba(232,165,0,0.3), transparent);", "display: none;")

# 9. Pipeline Visualizer Tweaks (make it look more technical)
css = css.replace("font-size: 28px;", "font-size: 20px;")

# Write back
with open("static/style.css", "w") as f:
    f.write(css)

print("CSS Refactored")

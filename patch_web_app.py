import re

with open("web_app.py", "r") as f:
    code = f.read()

# 1. Update emit function: ts -> timestamp
emit_pattern = re.compile(r'"ts": time\.time\(\),')
code = emit_pattern.sub('"timestamp": time.time(),', code)

# 2. Update TELEMETRY_UPDATE -> SYSTEM_METRICS
telemetry_pattern = re.compile(r'"TELEMETRY_UPDATE",')
code = telemetry_pattern.sub('"SYSTEM_METRICS",', code)

with open("web_app.py", "w") as f:
    f.write(code)

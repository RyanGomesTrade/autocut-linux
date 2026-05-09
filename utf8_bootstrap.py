"""
utf8_bootstrap.py - Importar NO TOPO de main.py, ui.py e batch_processor.py

Este módulo DEVE ser o primeiro import do seu projeto.
Ele garante que o processo Python atual roda em modo UTF-8 completo,
independente do locale do sistema operacional.
"""

import sys
import os
import io
import logging
import builtins

# ─── 1. Força UTF-8 Mode (PEP 540) ───────────────────────────────────────────
os.environ["PYTHONUTF8"] = "1"
os.environ["PYTHONIOENCODING"] = "utf-8"

# ─── 2. Reconfigura STDIN/STDOUT/STDERR ──────────────────────────────────────
def _reconfigure_stream(stream, name: str) -> None:
    try:
        if stream is None: return
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
        elif hasattr(stream, "buffer"):
            new_stream = io.TextIOWrapper(
                stream.buffer,
                encoding="utf-8",
                errors="replace",
                line_buffering=getattr(stream, "line_buffering", True),
            )
            if name == "stdout": sys.stdout = new_stream
            elif name == "stderr": sys.stderr = new_stream
            elif name == "stdin": sys.stdin = new_stream
    except Exception:
        pass

_reconfigure_stream(sys.stdin, "stdin")
_reconfigure_stream(sys.stdout, "stdout")
_reconfigure_stream(sys.stderr, "stderr")

# ─── 3. Monkeypatch global open() ────────────────────────────────────────────
# Garante que qualquer biblioteca que use open() sem encoding use UTF-8.
_original_open = builtins.open

def _new_open(file, mode='r', buffering=-1, encoding=None, errors=None, newline=None, closefd=True, opener=None):
    # Se for modo texto ('r', 'w', 'a', etc. sem 'b') e não tiver encoding definido
    if 'b' not in mode and encoding is None:
        encoding = 'utf-8'
    return _original_open(file, mode, buffering, encoding, errors, newline, closefd, opener)

builtins.open = _new_open

# ─── 4. Configuração de Locale ───────────────────────────────────────────────
import locale
try:
    # Tenta definir locale para UTF-8 para garantir que bibliotecas C
    # (como as usadas pelo faster-whisper/ctranslate2) funcionem corretamente.
    locale.setlocale(locale.LC_ALL, 'pt_BR.UTF-8')
except Exception:
    try:
        locale.setlocale(locale.LC_ALL, 'C.UTF-8')
    except Exception:
        pass

# ─── 5. Variáveis de ambiente para subprocessos ───────────────────────────────
# Fallback seguro caso LANG não esteja definido ou seja C
for var in ["LANG", "LC_ALL", "LC_CTYPE"]:
    val = os.environ.get(var, "")
    if not val or val.upper() in ("C", "POSIX", "C.UTF-8"):
        os.environ[var] = "pt_BR.UTF-8"

# ─── 6. Logging ───────────────────────────────────────────────────────────────
_log = logging.getLogger("viral_cutter.bootstrap")
_log.debug(f"UTF-8 Bootstrap ativo. stdout={getattr(sys.stdout, 'encoding', '?')} | locale={locale.getlocale()}")
"""
utf8_bootstrap.py - Importar NO TOPO de main.py e batch_processor.py

Este módulo DEVE ser o primeiro import do seu projeto.
Ele garante que o processo Python atual roda em modo UTF-8 completo,
independente do locale do sistema operacional (Void Linux, Alpine, etc.)

USO:
  # Primeira linha após os imports de stdlib em main.py:
  import utf8_bootstrap  # noqa: F401  (importação tem efeito colateral intencional)

POR QUE ISSO É NECESSÁRIO:
  Em sistemas onde PYTHONUTF8 e PYTHONIOENCODING não estão configurados
  no shell de inicialização (ex: Void Linux com runit / s6), o Python usa o
  codec do locale para sys.stdin/stdout/stderr e para open() sem encoding.
  
  Se LANG=C ou LANG não está definido, o codec padrão é ASCII, e qualquer
  caractere acima de 0x7F (incluindo 'ã', 'é', 'ç') causa:
    UnicodeDecodeError: 'ascii' codec can't decode byte 0xc3 ...
    UnicodeEncodeError: 'ascii' codec can't encode character ...
"""

import sys
import os
import io
import logging

# ─── 1. Força UTF-8 Mode (PEP 540) ───────────────────────────────────────────
# Equivalente a rodar: python -X utf8 main.py
# ou definir PYTHONUTF8=1 antes de iniciar o Python.
# Funciona em Python 3.7+. No 3.15+ será o padrão.
if hasattr(sys, "flags") and not getattr(sys.flags, "utf8_mode", False):
    # Não podemos mudar sys.flags retroativamente, mas podemos
    # reconfigurar os streams e definir a variável de ambiente
    # para que subprocessos herdem.
    os.environ["PYTHONUTF8"] = "1"
    os.environ["PYTHONIOENCODING"] = "utf-8"

# ─── 2. Reconfigura stdout/stderr para UTF-8 ─────────────────────────────────
# Necessário quando o terminal redireciona para pipe (ex: | tee, > arquivo)
# onde o Python detecta que não é um TTY e define encoding=ASCII.

def _reconfigure_stream(stream, name: str) -> None:
    """Tenta reconfigurar um stream para UTF-8, ignorando erros."""
    try:
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
        elif hasattr(stream, "buffer"):
            # Substitui por TextIOWrapper explicitamente UTF-8
            new_stream = io.TextIOWrapper(
                stream.buffer,
                encoding="utf-8",
                errors="replace",
                line_buffering=stream.line_buffering,
            )
            if name == "stdout":
                sys.stdout = new_stream
            elif name == "stderr":
                sys.stderr = new_stream
    except Exception:
        pass  # Nunca deve quebrar o startup


_reconfigure_stream(sys.stdout, "stdout")
_reconfigure_stream(sys.stderr, "stderr")

# ─── 3. Variáveis de ambiente para subprocessos ───────────────────────────────
# Garante que FFmpeg, yt-dlp e outros subprocessos herdem UTF-8.
os.environ.setdefault("LANG", "pt_BR.UTF-8")
os.environ.setdefault("LC_ALL", "pt_BR.UTF-8")
os.environ.setdefault("LC_CTYPE", "pt_BR.UTF-8")

# ─── 4. Logging ───────────────────────────────────────────────────────────────
_log = logging.getLogger("viral_cutter.bootstrap")
_log.debug(
    f"UTF-8 Bootstrap: stdout={getattr(sys.stdout, 'encoding', '?')}, "
    f"stderr={getattr(sys.stderr, 'encoding', '?')}, "
    f"fs={sys.getfilesystemencoding()}"
)
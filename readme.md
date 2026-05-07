# 🎬 Viral Cutter Pro

![Viral Cutter UI](file:///C:/Users/Ryan%20Gomes/.gemini/antigravity/brain/85fc2c2f-8b22-408f-87dd-f075a15c8829/viral_cutter_ui_mockup_1777927917196.png)

O **Viral Cutter Pro** é um ecossistema completo e automatizado para transformar vídeos longos (podcasts, entrevistas, lives) em cortes virais de alto impacto para TikTok, Reels e Shorts. O sistema opera **100% offline**, garantindo privacidade total e custo zero com APIs.

---

### 🚀 Automação em Lote e YouTube (NOVO)
- **Gerenciador de Lote Visual**: Importe listas de URLs e configure individualmente o formato (Shorts, TikTok, etc.) e o título de cada vídeo.
- **Upload Automático para YouTube**: Integração direta com a YouTube Data API v3 para postagem sem intervenção manual.
- **Agendamento Inteligente**: Defina um intervalo (ex: 4 em 4 horas) e o sistema agenda as postagens automaticamente no YouTube, garantindo presença nos horários de pico.
- **Títulos Virais**: O sistema utiliza o "Hook" gerado pela IA como título do vídeo e adiciona hashtags estratégicas.

---

## 📁 Estrutura do Sistema

```text
AUTO_CUT_/
├── ui.py                 # Interface Gráfica Principal (PySide6)
├── batch_processor.py    # Motor de processamento em lote e fila
├── youtube_uploader.py   # Módulo de autenticação e upload para YouTube
├── main.py               # Orquestrador CLI e lógica central
├── analyzer.py           # Motores de análise (Ollama + Heurístico)
├── transcriber.py        # Extração de áudio + Faster-Whisper
├── cutter.py             # Lógica de corte e re-encoding com FFmpeg
├── subtitle_generator.py # Geração de SRT e estilização
├── downloader.py         # Módulo de download do YouTube
├── ui_worker.py          # Gerenciamento de threads para a UI
└── requirements.txt      # Dependências do projeto
```

---

## 🛠️ Instalação Rápida

### 1. Requisitos de Sistema
Certifique-se de ter o **FFmpeg** instalado: `winget install ffmpeg`.

### 2. Configurar YouTube (Opcional para Postagem)
Para usar o upload automático:
1. Crie um projeto no [Google Cloud Console](https://console.cloud.google.com/).
2. Ative a **YouTube Data API v3**.
3. Crie uma credencial **OAuth Client ID (Desktop App)**.
4. Baixe o JSON e salve como `client_secrets.json` na raiz do projeto.

### 3. Configurar IA (Ollama)
```bash
ollama pull llama3
```

### 4. Instalar Dependências Python
```bash
pip install -r requirements.txt
```

---

## 🚀 Como Usar

### Pipeline de Alta Escala (Lote)
1. Execute `python ui.py`.
2. Vá na aba **"Gerenciar Lote"**.
3. Importe seu arquivo `list.txt` ou adicione URLs manualmente.
4. Configure o **Intervalo de Agendamento** (ex: 4h para 6 vídeos por dia).
5. Marque **"Upload automático para YouTube"** e clique em Iniciar.

---

## ⚙️ Configurações Recomendadas

| Recurso | Hardware Recomendado | Motor Sugerido |
| :--- | :--- | :--- |
| **Transcrição** | GPU NVIDIA (CUDA) | `medium` ou `large-v3` |
| **Transcrição** | CPU apenas | `tiny` ou `base` |
| **Análise** | 16GB+ RAM | `Ollama (Llama 3)` |
| **Análise** | Hardware Antigo | `Motor Heurístico` |

---

## 📄 Licença
Este projeto está sob a licença MIT. Sinta-se à vontade para usar e modificar.
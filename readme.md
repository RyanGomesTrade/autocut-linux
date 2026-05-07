# 🎬 Viral Cutter Pro

![Viral Cutter UI](file:///C:/Users/Ryan%20Gomes/.gemini/antigravity/brain/85fc2c2f-8b22-408f-87dd-f075a15c8829/viral_cutter_ui_mockup_1777927917196.png)

O **Viral Cutter Pro** é um ecossistema completo e automatizado para transformar vídeos longos (podcasts, entrevistas, lives) em cortes virais de alto impacto para TikTok, Reels e Shorts. O sistema opera **100% offline**, garantindo privacidade total e custo zero com APIs.

---

## ✨ Novas Funcionalidades

### 🖥️ Interface Gráfica Moderna (PySide6)
Agora com uma interface desktop intuitiva e profissional:
- **Dashboard Central**: Gerenciamento fácil de arquivos de entrada e saída.
- **Importação YouTube**: Baixe vídeos diretamente pela URL com o motor `yt-dlp`.
- **Galeria de Resultados**: Visualize e abra seus cortes gerados com um clique.
- **Monitoramento em Tempo Real**: Barra de progresso e console de logs integrados.

### 🧠 Motores de Análise Inteligente
Escolha como o sistema deve encontrar seus melhores momentos:
- **Motor Ollama (IA)**: Utiliza modelos como **Llama 3** ou **Mistral** para entender o contexto, emoção e potencial viral dos trechos.
- **Motor Heurístico (Legacy)**: Desenvolvido para máxima performance em máquinas com hardware limitado (como o AMD FX-6300). Analisa densidade de fala e palavras-chave sem necessidade de IA pesada.

### 🎞️ Edição e Legendas de Precisão
- **Legendas de Alto Impacto (ASS)**: Estilo viral com destaque colorido na palavra atual e efeitos de zoom sincronizados.
- **Sincronização Word-Level**: Precisão absoluta entre fala e texto.
- **Trilha Sonora Inteligente**: Mixagem automática de música de fundo que combina com o tema do vídeo sugerido pela IA.
- **Subtitles Burn-in**: Legendas embutidas no vídeo (hardcore) ou faixas separadas (soft).
- **Ajuste de Silêncio**: O sistema detecta silêncios no início e fim dos cortes para evitar cortes bruscos.
- **Presets de Redes Sociais**: Exportação automática em 9:16 (Vertical), 1:1 (Square) ou 16:9 (Landscape).

---

## 📁 Estrutura do Sistema

```text
AUTO_CUT_/
├── ui.py                 # Interface Gráfica Principal (PySide6)
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
Certifique-se de ter o **FFmpeg** instalado no seu sistema:
```bash
# Windows (PowerShell admin)
winget install ffmpeg

# Linux/macOS
sudo apt install ffmpeg  # Ubuntu
brew install ffmpeg       # Mac
```

### 2. Configurar IA (Ollama)
Para usar o motor de análise por IA, instale o [Ollama](https://ollama.com/) e baixe o modelo recomendado:
```bash
ollama pull llama3
ollama serve
```

### 3. Instalar Dependências Python
```bash
# Recomendado: use um ambiente virtual
python -m venv venv
source venv/bin/activate  # Linux/Mac
venv\Scripts\activate     # Windows

pip install -r requirements.txt
```

---

## 🚀 Como Usar

### Via Interface Gráfica (Recomendado)
Para iniciar o Viral Cutter Pro com a nova interface:
```bash
python ui.py
```

### Via Linha de Comando (CLI)
Para usuários avançados ou automação em servidores:
```bash
python main.py --input video.mp4 --output ./cortes --top-n 5 --preset tiktok
```

---

## ⚙️ Configurações Recomendadas

| Recurso | Hardware Recomendado | Motor Sugerido |
| :--- | :--- | :--- |
| **Transcrição** | GPU NVIDIA (CUDA) | `medium` ou `large-v3` |
| **Transcrição** | CPU apenas | `small` ou `base` |
| **Análise** | 16GB+ RAM | `Ollama (Llama 3)` |
| **Análise** | Hardware Antigo | `Motor Heurístico` |

---

## 📤 Saída Gerada
O sistema organiza tudo para você na pasta de saída:
- `clips/*.mp4`: Seus vídeos prontos para postar.
- `subtitles/*.srt`: Arquivos de legenda individuais.
- `transcript.txt`: A transcrição completa do vídeo original.
- `session_report.json`: Metadados e scores de todos os cortes.

---

## 📄 Licença
Este projeto está sob a licença MIT. Sinta-se à vontade para usar e modificar.
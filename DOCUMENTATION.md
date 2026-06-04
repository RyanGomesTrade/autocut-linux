# 🎬 Documentação Técnica: Viral Cutter Pro

Este documento explica detalhadamente a arquitetura e o funcionamento de cada arquivo do projeto **AutoCut Linux / Viral Cutter**.

---

## 🛠 Arquitetura do Sistema

O projeto é dividido em quatro camadas principais:
1. **Interface (UI)**: Gerenciamento visual e interação com o usuário.
2. **Processamento (Core)**: Download, transcrição, análise e edição de vídeo.
3. **Distribuição (Upload)**: Envio automatizado para o YouTube (via API ou Navegador).
4. **Utilidades**: Estilos, gerenciamento de logs e funções auxiliares.

---

## 📄 Descrição dos Arquivos

### 1. `main.py`
O coração do processamento individual. Ele coordena o "Pipeline":
- Orquestra o download do vídeo original.
- Chama o Whisper para a transcrição.
- Envia a transcrição para análise (Ollama ou Heurística).
- Executa os cortes e a edição final.

### 2. `ui.py`
O arquivo principal da interface gráfica (PySide6).
- Gerencia a navegação entre Dashboard, Lote, Configurações e Resultados.
- Controla o estado global do aplicativo (configurações de marca d'água, modelos de IA, etc.).
- Contém os diálogos de gerenciamento de canais e login do Playwright.

### 3. `ui_styles.py`
Define a identidade visual do programa.
- Implementa o **Apple Minimalist Theme** usando QSS (Qt Style Sheets).
- Garante que botões, cards e menus tenham um visual moderno e consistente.

### 4. `batch_processor.py`
Responsável pelo processamento em lote (múltiplos vídeos).
- Lê arquivos `list.txt` ou entradas da tabela de lote.
- Gerencia a fila de jobs, garantindo que se um vídeo falhar, os próximos continuem.
- Implementa a **Lógica de Agendamento**, calculando o horário de postagem sequencial (ex: de 1 em 1 hora).

### 5. `cutter.py`
O motor de edição de vídeo baseado em **FFmpeg**.
- Realiza o "crop" (corte lateral) para transformar vídeos horizontais em verticais (9:16).
- Aplica efeitos de desfoque (blur) no fundo.
- Insere legendas, marca d'água e trilha sonora.
- Contém a função de **escape de caracteres**, evitando erros com apóstrofos ou símbolos nos nomes dos arquivos.

### 6. `youtube_uploader.py`
Gerenciador oficial de uploads via **YouTube Data API v3**.
- Suporta múltiplos perfis de canais.
- Implementa a **Troca Automática de Cota**: se um projeto do Google Cloud atingir o limite, ele pula para o próximo canal configurado.
- Gerencia tokens OAuth2 de forma isolada para cada conta.

### 7. `playwright_uploader.py`
Alternativa de upload via automação de navegador (**Playwright**).
- Simula um usuário real no YouTube Studio para ignorar limites de cota da API.
- **Sessões Isoladas**: Mantém pastas de cookies separadas para cada canal, permitindo que você fique logado em várias contas simultaneamente.
- Permite o "Reset" de sessões para trocar de conta facilmente.

### 8. `auto_list.py` & `auto_list_ui.py`
Ferramenta de mineração de conteúdo.
- Busca vídeos virais no YouTube com base em nichos lucrativos (Finanças, IA, Curiosidades, etc.).
- Filtra por região (Brasil ou EUA) e duração (evita Shorts para pegar vídeos longos para corte).
- Salva os resultados diretamente no `list.txt` para processamento.

### 9. `watermark.py`
Módulo especializado em sobreposição de marca d'água.
- Calcula o posicionamento matemático exato para imagens e textos.
- Garante que a logo mantenha a proporção original, independentemente da resolução do vídeo.

### 10. `utils.py`
Funções de suporte usadas em todo o projeto.
- Sanitização de nomes de arquivos (remove caracteres proibidos).
- Configuração global de logs.
- Garantia de existência de diretórios.

### 11. `downloader.py`
Interface para o `yt-dlp`.
- Realiza o download dos vídeos do YouTube na melhor qualidade disponível antes do processamento.

---

## 📂 Pastas Importantes

- `/playwright_sessions`: Guarda os logins de cada canal para o navegador.
- `/results`: Pasta padrão onde os vídeos finais editados são salvos.
- `youtube_profiles.json`: Arquivo que armazena a configuração dos seus múltiplos canais.

---
*Documentação gerada automaticamente para o projeto Viral Cutter Pro.*

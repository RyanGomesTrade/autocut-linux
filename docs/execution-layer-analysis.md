# Análise da Execution Layer Antiga

## 1. Fluxo Completo (Legacy Pipeline)

O pipeline original foi projetado para um processamento linear e síncrono:

```text
Discovery (auto_list.py) -> URL -> Downloader (yt-dlp) -> Transcrição (Whisper) -> Análise (Ollama) -> Corte/Render (FFmpeg) -> Upload (API/Selenium)
```

### Componentes por Etapa:
*   **Discovery/Seleção:** `auto_list.py` (Modo 1) gera uma lista de URLs. `batch_processor.py` lê essa lista.
*   **Downloader:** `downloader.py` usa `yt-dlp` para baixar o vídeo completo antes de qualquer análise.
*   **Transcrição:** `transcriber.py` usa `whisper` para transcrever o vídeo inteiro localmente.
*   **Análise de Cortes:** `analyzer.py` divide o texto em blocos de 6 minutos e envia para o Ollama (Llama3) identificar momentos virais.
*   **Corte e Render:** `cutter.py` executa o FFmpeg para extrair segmentos, ajustar silêncios, embutir legendas e aplicar filtros.
*   **Export/Upload:** `batch_processor.py` coordena o salvamento e chama `youtube_uploader.py` ou `playwright_uploader.py`.

---

## 2. Arquitetura da Camada de Execução

### Cutter.py (Orquestrador FFmpeg)
É o componente mais robusto e reaproveitável. 
*   **O que funciona:** Presets de exportação (TikTok, Shorts, Landscape), detecção de silêncio para evitar cortes bruscos, e embutição de legendas "high impact".
*   **O que está acoplado:** Depende fortemente de arquivos SRT gerados em tempo de execução.
*   **Auto-Framing:** Possui uma implementação inicial de face tracking usando OpenCV (Haar Cascades).

### Batch_processor.py (O antigo "Worker")
*   **Sistema de Fila:** Inexistente. É um loop `for` simples que percorre uma lista de URLs.
*   **Estado:** Usa um `batch_progress.json` para marcar URLs como concluídas ou falhas (mecanismo básico de resume).

---

## 3. Interface de Entrada

Atualmente, o sistema é "Video-Centric":
1.  Recebe uma **URL**.
2.  Baixa o **Vídeo Inteiro**.
3.  Só então começa a pensar nos cortes.

O novo **Discovery Engine** muda isso para "Segment-Centric", onde já sabemos o `start_time` e `end_time` antes de baixar o vídeo.

---

## 4. Sistema de Filas e Jobs

*   **Linearidade:** O sistema roda linearmente. Se um vídeo de 3 horas entrar na fila, o pipeline para por 40 minutos para transcrever e analisar.
*   **Retries:** Apenas via reinicialização manual do `batch_processor.py`.
*   **Prioridade:** Não existe. A ordem é a do arquivo `list.txt`.

---

## 5. Estrutura e Heurísticas dos Cortes

*   **Decisão de Timestamps:** 100% delegada ao LLM (Ollama) em blocos isolados. Não há visão global do vídeo.
*   **Ajuste de Silêncio:** Heurística sólida que evita cortar palavras ao meio (offset de 0.1s pós-silêncio).
*   **Duração:** Fixa entre 20s e 65s (configurável no `DEFAULT_CONFIG`).

---

## 6. Gargalos Identificados

1.  **I/O de Vídeo:** Baixar 2GB para extrair 30 segundos de áudio/vídeo.
2.  **Whisper Full-Scan:** Transcrever partes irrelevantes de vídeos longos.
3.  **Ollama Blocking:** A análise de blocos é sequencial e impede que o FFmpeg comece a trabalhar.
4.  **Single-Worker:** Um único processo faz tudo. Se o render está batendo na CPU, o downloader está parado.

---

## 7. Integração com o Novo Discovery Engine

O Execution Layer antigo **não consegue** consumir o novo engine sem adaptações, mas a base é compatível.

### Adaptações Necessárias:
1.  **Consumo de DB:** O executor precisa ler de `segments` (SQLite) em vez de chamar o `OllamaAnalyzer`.
2.  **Download Cirúrgico:** Integrar a lógica de download parcial (já esboçada no `transcription_fallback.py`) no pipeline principal de corte.
3.  **Desacoplamento:** Separar a etapa de "Identificação de Cortes" (Brain) da etapa de "Renderização" (Muscle).

---

## 8. Diagnóstico de Infraestrutura Existente

*   **Clip Candidates:** O banco `viral_engine.db` (novo) já faz esse papel muito melhor que o `analyzer.py` (antigo).
*   **Pending Jobs:** Precisamos transformar a tabela `generated_clips` em uma fila de renderização real.
*   **Upload Queue:** O `youtube_profiles.json` e os uploaders estão prontos, mas precisam de um worker que não trave o render.

---

## 9. Plano de Evolução

1.  **Criar o `execution_worker.py`:** Um processo independente que monitora a tabela `segments` com score alto e `status = 'pending'`.
2.  **Migrar Heurísticas:** Mover a lógica de "Ajuste de Silêncio" e "Auto-Frame" do `cutter.py` para serem chamadas pelo novo worker.
3.  **Implementar Multi-Stage Render:**
    *   Stage 1: Download parcial (apenas o segmento viral + buffer).
    *   Stage 2: Transcrição precisa (Whisper Medium/Large) apenas do segmento.
    *   Stage 3: Render FFmpeg.
4.  **Observabilidade:** Salvar o rastro de renderização (logs de erro do FFmpeg) no banco, assim como fizemos no Discovery Engine.

# VISÃO ESTRATÉGICA

A execution layer antiga é um **"Operador de Máquina"** (faz o que mandam, um por um). 
O novo Discovery Engine é um **"Estrategista"** (prevê onde está o valor).

A próxima fase do projeto é construir a **"Linha de Montagem Industrial"**: um sistema onde o Estrategista alimenta uma fila de alta performance que o Operador processa de forma assíncrona e resiliente.

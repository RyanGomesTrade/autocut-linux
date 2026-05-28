# Pipeline de Processamento

## Fases do Pipeline

### Fase 1: Discovery (The Radar)
Varredura contínua de nichos pré-definidos e canais selecionados.
*   **Input:** Queries de nicho ou Channel IDs.
*   **Output:** Lista de candidatos para análise profunda.
*   **Decision:** "Este vídeo vale o tempo de análise?"

### Fase 2: Intelligence (The Brain)
Extração de features semânticas e comportamentais.
*   **Processo:** Transcrição (Oficial ou Whisper) + Scan de Comentários.
*   **Análise:** Segmentação do texto em blocos e análise heurística de cada bloco.
*   **Output:** Matriz de features por segmento.

### Fase 3: Scoring & Ranking (The Filter)
Consolidação de todos os sinais em um ranking unificado.
*   **Processo:** Cálculo do Viral Score final.
*   **Output:** Entrada no banco SQLite pronta para ser "cortada".

### Fase 4: Feedback (The Loop) - *EM DESENVOLVIMENTO*
Monitoramento dos vídeos postados para aprendizado.
*   **Processo:** Salvar views/likes dos cortes gerados.
*   **Objetivo:** Ajustar os thresholds de VPH e Clip Density baseados no que realmente funcionou.

## Funil de Custo Computacional
| Fase | Custo | Tecnologia |
| :--- | :--- | :--- |
| **Discovery** | ~0 (API) | YouTube Data API v3 |
| **Intelligence (Transcript)** | ~0 (API) | YouTube Transcript API |
| **Intelligence (Fallback)** | Médio (GPU/CPU) | yt-dlp + faster-whisper |
| **Analysis** | Baixo (CPU) | Heuristic Python Logic |

## Gargalos Conhecidos
1.  **YouTube Rate Limits:** Resolvido com rotação de perfis/tokens.
2.  **Whisper Processing:** Resolvido com `Strategic Audio Sampling` (extração apenas de partes do áudio).
3.  **Transcrições Desativadas:** Resolvido com o pipeline de fallback híbrido.

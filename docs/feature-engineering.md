# Feature Engineering: Quantificando a Atenção

## Objetivo
Transformar áudio e metadados em números que um algoritmo possa classificar.

## Features Atuais (Heurísticas)

### Semânticas
*   **Hook Density:** Frequência de frases de impacto (ex: "você não vai acreditar", "o segredo é", "pare tudo").
*   **Controversy Index:** Detecção de palavras de alto peso emocional ou temas sensíveis.
*   **Authority Score:** Assertividade detectada pelo Whisper (uso de verbos no imperativo, pausas dramáticas).

### Comportamentais
*   **VPH (Velocity):** Quão rápido as pessoas estão clicando.
*   **Acceleration:** Quão rápido o interesse está aumentando.
*   **Relative Momentum:** O interesse é atípico para este canal?

### Sociais
*   **Comment Velocity:** Frequência de novos comentários.
*   **Timestamp Clusters:** Áreas do vídeo com muitos comentários mencionando horários (indicativo forte de momento clipável).

## Features Futuras (ML)
*   **Audio Energy:** Picos de volume e entusiasmo na voz.
*   **Visual Staticity:** Detecção de cortes de câmera ou mudanças de cena (via metadados de stream).
*   **Text Embeddings:** Vetorização do transcript para comparação com base de dados de "Shorts que já explodiram".

# Estrutura de Dados (Database)

## Filosofia
O banco de dados não é apenas para persistência da UI, mas para criação de um **Dataset de Atenção**.

## Esquema SQLite (`viral_engine.db`)

### Tabela `channels`
Armazena a linha de base (baseline) de performance de cada canal.
*   `channel_id` (PK)
*   `name`
*   `avg_vph`: Média histórica para cálculo de `Relative VPH`.
*   `last_scanned`: Timestamp.

### Tabela `videos`
O coração do sistema.
*   `video_id` (PK)
*   `vph`, `relative_vph`, `vph_acceleration`.
*   `momentum_score`, `trend_score`, `final_viral_score`.
*   `audio_hash`: Para evitar re-transcrição de conteúdo duplicado.
*   `raw_signals_json`: Dump completo dos sinais para ML futuro.

### Tabela `video_history`
Série temporal para cálculo de aceleração.
*   `video_id`, `vph`, `timestamp`.

### Tabela `segments`
Momentos específicos detectados dentro do vídeo.
*   `video_id`, `start_time`, `end_time`, `total_score`, `features_json`.

## Estratégia de Observabilidade
*   Salvamos o `raw_signals_json` para que, se decidirmos mudar a fórmula do score no futuro, possamos re-processar o banco inteiro sem precisar chamar a API do YouTube novamente.
*   O `audio_hash` funciona como um sistema de deduplicação em nível de conteúdo, não apenas de ID de vídeo.

# Attention Operations Dashboard - Implementation Report

## Visão Geral
O `web_app.py` foi transformado de uma interface de configuração simples em um **Attention Operations Dashboard** de alta performance, inspirado no design do Bloomberg Terminal. O sistema agora serve como o "centro nervoso" operacional para monitoramento de tendências virais e controle do pipeline de renderização em tempo real.

## Arquitetura de API
Foram criados endpoints organizados sob o namespace `/api/ops/` para separar a lógica de UI da lógica de telemetria e controle:

*   **`/api/ops/dashboard`**: Sumário executivo (jobs ativos, falhados, throughput 24h, vídeos em tendência).
*   **`/api/ops/jobs`**: Visualização detalhada da fila de execução com status em tempo real.
*   **`/api/ops/trends`**: Monitor de inteligência de atenção (VPH Relativo, Aceleração, Score Viral).
*   **`/api/ops/metrics`**: Telemetria de performance (tempo de render, uso de Whisper, taxa de deduplicação).
*   **`/api/ops/segments/<video_id>`**: Segment Inspector (Explainable Viral AI) - detalha por que cada segmento foi escolhido.
*   **`/api/ops/clips`**: Feedback Loop - comparação de performance prevista vs real.

## Frontend & UX
*   **Visual Bloomberg-style**: Tema escuro de alto contraste, tipografia mono-espaçada para dados técnicos e grids densos de informação.
*   **Pipeline Visualizer**: Representação gráfica do fluxo `Discovery → Queue → Render → Upload`.
*   **Baixa Latência**: Implementação de polling otimizado (3s) para garantir que o dashboard reflita o estado real do backend sem sobrecarga excessiva do SQLite.
*   **Segment Inspector**: Modal dedicado para análise profunda de vídeos, expondo o `decision_trace` e scores individuais de hook/controvérsia.

## Métricas Expostas
*   **Relative VPH**: Velocidade de visualização comparada à média histórica do canal.
*   **Acceleration**: Taxa de variação do VPH (detecção precoce de viralização).
*   **Throughput**: Capacidade de processamento diário do pipeline.
*   **Deduplication Rate**: Economia de banda e processamento via `SegmentDeduplicator`.

## Problemas de Concorrência e Soluções
*   **Database Locking**: O SQLite foi configurado com um gerenciador de conexões resiliente no `database.py` para evitar erros de `database is locked` durante acessos simultâneos da API e dos Workers.
*   **SSE vs Polling**: Optou-se por Polling para os dados de dashboard por ser mais robusto em ambientes de rede instáveis, enquanto o SSE (Server-Sent Events) foi mantido para logs de terminal em tempo real.

## Testes Executados
1.  **Validação de Endpoints**: Todos os endpoints `/api/ops/` foram testados e retornam JSON válido.
2.  **Stress de Polling**: O dashboard suporta atualizações frequentes sem degradação perceptível da UI.
3.  **Integração DB**: Verificada a persistência e recuperação de métricas operacionais na tabela `operational_metrics`.

## Conclusão
O sistema agora possui uma camada de observabilidade de nível industrial, permitindo que o operador identifique gargalos e visualize o "pulso" da atenção humana capturada pelo Viral Discovery Engine.

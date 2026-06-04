# Execution Surface Report

## Arquitetura Implementada

A Execution Queue foi transformada em uma Execution Surface viva!

### Componentes Principais

1. **Job Cards Enriquecidos**
    - Estrutura vertical com mais detalhes.
    - Status badge.
    - Stage (ex: QUEUED, RENDERING).
    - Worker responsável (placeholder por enquanto).
    - Progress bar alimentada por patch SSE.
    - ETA (placeholder por enquanto).
    - Botões PAUSE/CANCEL com data-action e data-id.

2. **Progress Bars Reais via SSE**
    - Patch SSE com campo `progress` (0.0 a 1.0).
    - `updateNodeProperties` atualiza SOMENTE o progress bar do job relevante.
    - Transição suave com CSS `transition: width 0.3s ease`.

3. **Stage Visualization**
    - O pipeline (DISCOVERY → QUEUE → RENDER → UPLOAD) já existia no HTML.
    - Adicionado CSS com borda, fundo e pulsação (animation `viz-pulse`).
    - Frontend ativa o stage com base nos status dos jobs.
        - Se houver job em RENDERING: ativa stage RENDER.
        - Se houver job em PENDING: ativa stage QUEUE.
        - Se houver job em DONE: ativa stage UPLOAD.

4. **Pause/Cancel Reais**
    - Endpoints no backend:
        - `POST /api/jobs/pause`: Atualiza status do job para PAUSED no banco.
        - `POST /api/jobs/cancel`: Atualiza status do job para CANCELLED no banco.
    - EventBus listeners no frontend:
        - `PAUSE_REQUESTED` → POST /api/jobs/pause → hydrateInitialOnce().
        - `CANCEL_REQUESTED` → POST /api/jobs/cancel → hydrateInitialOnce().

5. **Runtime Registry & RAF Batching**
    - Continuamos usando o Runtime Registry existente.
    - Nenhum re-render global.
    - Nenhum polling manual.
    - Eventos → dirty queue → RAF flush → DOM patch.

## Lifecycle dos Jobs

1. **JOB_QUEUED**: Job é criado no banco, aparece na Execution Queue com status PENDING.
2. **JOB_PROGRESS**: Job recebe patch de progresso (ex: 0.42) e stage (ex: RENDERING).
3. **JOB_COMPLETED**: Job tem status DONE.
4. **PAUSE_REQUESTED**: Job é pausado via backend, status PAUSED.
5. **CANCEL_REQUESTED**: Job é cancelado via backend, status CANCELLED.

## Estratégia de Runtime

- **Event-Driven**: Todas as atualizações partem de eventos (SSE ou EventBus).
- **Entity-Only Updates**: Somente o node DOM correspondente à entidade é atualizado.
- **RAF Batching**: Mudanças são agrupadas em frames de animação para performance.
- **Hydrate-Once Fallback**: Ainda usamos hidratação via API para dados históricos, pois o SSE só captura eventos após a conexão.

## Gargalos Restantes

1. **Sem progresso real do clip_worker**: O `clip_worker.py` não está emitindo métricas (progress, fps, eta) para o banco ou para o SSE.
2. **Worker info é placeholder**: Os jobs não tem worker atribuído ainda.
3. **Hydrate-Once para cada ação**: Estamos rehidratando a cada QUEUE/PAUSE/CANCEL para garantir que o runtime tenha os dados mais recentes; seria melhor se o backend emitisse o evento correspondente imediatamente após a ação.

## Riscos Futuros

1. **Performance com muitos jobs**: Se houver centenas de jobs, o `hydrateInitialOnce` pode ficar lento porque busca todos os jobs/trends via API.
2. **Sem idempotência**: Não há mecanismo para garantir que o mesmo evento não seja processado duas vezes.
3. **Sem reconciliação**: Se o SSE perder conexão e reconectar, não há forma de "reconhecer" o que já foi processado (usamos apenas timestamps no backend para watermark).

## Sensação Operacional da Queue

- **Visualização industrial**: A Execution Queue parece uma linha de produção, não mais uma tabela web.
- **Pipeline "respirando"**: O stage active pulsa, dando a sensação de que algo está acontecendo.
- **Atualizações suaves**: A progress bar anima, e os status são atualizados sem re-renderizar toda a lista.
- **Operacional**: Os botões PAUSE/CANCEL funcionam, e o usuário vê o resultado em tempo real.
- **Limitação**: Sem progresso real do worker, a sensação "render acontecendo AGORA" não está 100% lá ainda.

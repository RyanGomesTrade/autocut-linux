# Worker Orchestration Report

## Arquitetura do Worker Loop

O `ClipWorker` em [clip_worker.py](file:///home/gomes/Projetos%20/autocut-linux/clip_worker.py:161) já possui um loop operacional completo!

**Loop Principal**:
```python
while self.running:
    jobs = database.get_pending_jobs()  # Busca jobs em status "PENDING"
    if not jobs:
        time.sleep(5)
        continue
    for job in jobs:
        self.process_job(job)
```

**Processamento de Job**:
1.  **Marca como DOWNLOADING**: `database.update_job_status(job_id, "DOWNLOADING")`
2.  **Download Parcial**: `download_partial_stream(video_id, start, end, ...)`
3.  **Marca como CUTTING**: `database.update_job_status(job_id, "CUTTING")`
4.  **Ajuste de Silêncio**: `detect_silence()` + `adjust_cut_to_avoid_silence()`
5.  **Marca como RENDERING**: `database.update_job_status(job_id, "RENDERING")`
6.  **Render Final**: `cut_video_segment()`
7.  **Marca como DONE**: `database.update_job_status(job_id, "DONE", ...)`

## Como os Jobs São Consumidos

1.  **Status Inicial**: O `add_render_job` em [database.py:234](file:///home/gomes/Projetos%20/autocut-linux/database.py#L234) define status = "PENDING".
2.  **Busca**: `get_pending_jobs()` filtra `WHERE status = 'PENDING'`.
3.  **Atualização**: Cada etapa do `process_job()` atualiza o status via `update_job_status()`.
4.  **WAL Mode**: O SQLite está em modo Write-Ahead Logging (WAL), então leituras do frontend e escritas do worker podem acontecer simultaneamente.

## Eventos SSE Emitidos

Os eventos SSE são gerados automaticamente pelo endpoint `/stream/events` em [web_app.py:1037](file:///home/gomes/Projetos%20/autocut-linux/web_app.py#L1037), que monitora o `updated_at` dos jobs!
- **JOB_QUEUED**: Quando o job é criado.
- **JOB_PROGRESS**: Quando `updated_at` muda (qualquer etapa, desde DOWNLOADING até RENDERING).
- **JOB_COMPLETED**: Quando status = "DONE".
- **JOB_ERROR**: Quando status = "FAILED".

## Gargalos Encontrados

1. **Todos os Jobs Estavam Cancelados**: Os jobs que você criou anteriormente estavam todos em status "CANCELLED", então o worker não pegava nenhum.
2. **Sem Mock de Progresso**: O worker não emite progresso granular (0.0 até 1.0) durante o download/renderização, apenas atualiza o status geral.
3. **Worker Simples (Single Thread)**: Processa um job por vez; sem mecanismo de pool de workers.

## Riscos Restantes

1. **Autocura em caso de falha do worker**: Se o worker cair no meio de um job, o status permanece em "DOWNLOADING"/"RENDERING" e não retorna para "PENDING" automaticamente.
2. **Sem limite de concorrência**: Não há mecanismo para evitar que múltiplos workers peguem o mesmo job.
3. **Sem Heartbeat do Worker**: O worker não registra seu status no banco.

## Fluxo Operacional Completo (Para Testar Agora)

1. **Clique em +QUEUE** em um trend no navegador.
2. **Job criado**: Status inicial PENDING.
3. **Worker detecta**: Dentro de 5 segundos, `get_pending_jobs()` encontra o job.
4. **Job inicia**: Worker marca status como DOWNLOADING.
5. **UI Atualiza**: SSE envia JOB_PROGRESS → UI atualiza.
6. **Job Finaliza**: Se tudo der certo, status DONE.

## Diagnóstico Honesto do Pipeline Atual

✅ **Backend Event-Driven**: 100% funcionando (SSE, EventBus, Runtime Registry).
✅ **Worker Loop**: Existente e correto.
✅ **Queue Consumption**: Funcionando (basta ter jobs em PENDING).
⚠️ **Jobs Existentes**: Todos estavam cancelados (já resetamos 2, 3, 4 para PENDING).
⚠️ **Progresso Granular**: Ainda não temos (seria legal adicionar no futuro).

## Teste Agora!

Agora você pode testar o fluxo completo!
1.  **Inicie o worker**: Abra um novo terminal e execute `python3 clip_worker.py`.
2.  **Atualize o navegador**: F5 na página.
3.  **Veja os jobs na Execution Queue**: Os jobs 2,3,4 devem aparecer como PENDING.
4.  **Veja o worker começar a trabalhar**: No terminal do worker, você verá logs de download/renderização!

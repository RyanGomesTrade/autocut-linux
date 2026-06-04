# Web Control Panel: Architecture & Strategy
**Document Version:** 1.0.0  
**Project:** Viral Discovery Engine (AutoCut)  
**Status:** Operational / Evolution Phase

## 1. Visão Estratégica do Web App

O [web_app.py](file:///home/gomes/Projetos /autocut-linux/web_app.py) não é meramente uma interface gráfica para usuários finais; ele é o **Painel de Controle Estratégico do Motor de Atenção**. Enquanto editores de vídeo comuns focam na estética, nosso Web App foca na **governança da atenção**.

### De Interface para Cockpit Operacional
Diferente de uma interface CRUD (Create, Read, Update, Delete) convencional, o Web Control Panel funciona como um radar de alta frequência:
- **Observabilidade do Pipeline**: Visualização em tempo real do fluxo `Discovery → Queue → Render → Upload`.
- **Controle de Estratégia**: Ajuste dinâmico de parâmetros de viralidade (Relative VPH, Acceleration thresholds) sem reiniciar o backend.
- **Supervisão de Workers**: Monitoramento da carga do Whisper, renderizadores FFmpeg e workers de download.
- **Inteligência Operacional**: O sistema não apenas executa; ele explica o porquê das decisões através do **Explainable Viral AI**.

A governança é crítica porque o pipeline de descoberta viral opera em um ambiente de alta volatilidade. Parâmetros mal ajustados podem resultar em desperdício de banda ou perda de tendências emergentes.

---

## 2. Arquitetura Atual

A arquitetura atual é baseada em um modelo **Hybrid Polling-SSE** sobre uma base de dados SQLite.

### Componentes Core
- **Backend ([web_app.py](file:///home/gomes/Projetos /autocut-linux/web_app.py))**: Servidor Flask que gerencia workers em threads separadas (`threading.Thread`) para não bloquear a UI.
- **API Layer**: Camada de endpoints em `/api/ops/` que expõe o estado do banco de dados de forma assíncrona.
- **Persistence ([database.py](file:///home/gomes/Projetos /autocut-linux/database.py))**: SQLite centralizado. O banco é o ponto de sincronização entre o `discovery_engine.py` (produtor de dados) e o `web_app.py` (consumidor).
- **Frontend ([app.js](file:///home/gomes/Projetos /autocut-linux/static/app.js))**: Vanilla JavaScript orquestrando a renderização dinâmica.

### Fluxo de Dados
1. **Produção**: O `discovery_engine.py` detecta uma tendência e insere em `videos` e `render_jobs`.
2. **Exposição**: O backend Flask lê essas tabelas através de consultas otimizadas no SQLite.
3. **Consumo**: O `app.js` realiza polling a cada 3 segundos nos endpoints `/api/ops/*`.
4. **Logs**: O `SSELoggingHandler` captura logs do sistema e os envia via **Server-Sent Events (SSE)** para o terminal da UI.

### Gargalos Identificados
- **SQLite Locking**: Em momentos de alta carga (múltiplos workers escrevendo), a UI pode travar ou retornar erros de "database is locked" ao tentar ler métricas.
- **DOM Overhead**: A renderização manual via `innerHTML` em listas grandes de tendências pode causar jank (travamentos visuais) no navegador.
- **Single-process Flask**: O uso do servidor de desenvolvimento do Flask limita a concorrência real de requisições API.

---

## 3. Estrutura Ideal do Frontend

O frontend deve ser modularizado em blocos de inteligência:

### Dashboard (Radar de Atenção)
- **Métricas em Tempo Real**: Throughput (clips/hora), economia de banda (deduplicação).
- **Status do Pipeline**: Indicadores visuais de saúde para cada etapa (Discovery, Queue, Render).

### Discovery Monitor
- **Trend Heatmap**: Visualização temporal de quando os vídeos estão atingindo o pico de momentum.
- **Acceleration Gauge**: Indicador visual da velocidade com que um assunto está "explodindo".

### Render Queue (Execution Control)
- Estados granulares: `PENDING`, `DOWNLOADING`, `CUTTING`, `RENDERING`, `DONE`, `FAILED`.
- **Priority Override**: Capacidade de mover um job manualmente para o topo da fila pela UI.

### Operational Metrics (System Health)
- Monitoramento de recursos locais: Uso de GPU (VRAM para Whisper), CPU e latência de extração de stream.

### Strategy Panel (Control Panel)
A aba de parâmetros atual será evoluída para um **Strategy Control Panel**:
- **Discovery Strategy**: Ajuste de nichos e pesos de metadados.
- **Attention Strategy**: Configuração de hooks, densidade de controvérsia e thresholds de Viral Score.
- **Upload Strategy**: Agendamento e controle de cotas das plataformas.

---

## 4. JavaScript Architecture

O JS atual é imperativo e orientado ao DOM. A evolução exige uma arquitetura reativa.

### Estado Atual
- **Polling**: Requisições cíclicas para `/api/ops/dashboard`.
- **SSE**: Conexão persistente unidirecional para logs.
- **Gargalo**: O polling de 3s cria um atraso artificial e gera carga desnecessária no banco.

### Evolução Proposta
- **WebSockets (Socket.io)**: Substituir o polling por uma conexão bi-direcional. O servidor "empurra" atualizações apenas quando o estado do banco muda (ex: um job termina).
- **Event-Driven UI**: Componentes que reagem a eventos específicos (`JOB_FINISHED`, `TREND_DETECTED`).
- **Virtualized Lists**: Para o Monitor de Tendências, renderizar apenas os itens visíveis para suportar milhares de vídeos sem perda de performance.
- **Optimistic Updates**: Ao deletar ou priorizar um job, a UI reflete a mudança instantaneamente antes da confirmação do servidor.

---

## 5. CSS / UX Strategy: Bloomberg Terminal Aesthetic

A interface deve transmitir **precisão técnica** e não apenas facilidade de uso.

- **Dark Mode Operacional**: Fundo `#0b0c0f` para reduzir fadiga visual em monitoramento prolongado.
- **Status Colors**: 
    - `Amber (#e8a500)`: Sistema em processamento/alerta.
    - `Green (#22c55e)`: Fluxo saudável / Sucesso.
    - `Red (#ef4444)`: Falha crítica / Bloqueio.
- **Glow Effects**: Vídeos com `vph_acceleration > 2.0` devem possuir um efeito de brilho (glow) para atrair o olhar do operador imediatamente.
- **Modular Cards**: Design baseado em grids densos de informação, maximizando a densidade de dados por pixel.

---

## 6. Backend Integration

A integração backend-frontend deve ser otimizada para concorrência:
- **API Design**: Seguir o padrão RESTful para `/jobs`, `/trends`, `/metrics`.
- **SQLite WAL Mode**: Habilitar *Write-Ahead Logging* para permitir leituras e escritas simultâneas sem travar a UI.
- **Pagination/Lazy Loading**: O endpoint de tendências deve suportar paginação para não carregar todo o histórico de uma vez.

---

## 7. Segurança e Estabilidade

- **Race Conditions**: Uso de `threading.Lock` no `web_app.py` para proteger o estado global de progresso.
- **Polling Backoff**: Implementar backoff exponencial se o servidor começar a falhar, evitando "DDoS acidental" do próprio frontend.
- **Sanitização**: Validação rigorosa de URLs de entrada para evitar injeção de comandos via `yt-dlp`.

---

## 8. Roadmap do Web App

### Curto Prazo (Observabilidade)
- Finalizar a integração total das métricas de telemetria (CPU/GPU load) na UI.
- Implementar visualização de log por job específico (Segment Inspector).

### Médio Prazo (Controle Estratégico)
- Implementar o "Live Strategy Tuning" (mudar parâmetros do Discovery Engine em tempo real).
- Criar editor de templates de legenda via Web App.

### Longo Prazo (Escala)
- **Multi-user Support**: Login e níveis de acesso.
- **Cluster Orchestration**: Gerenciar múltiplos workers rodando em máquinas diferentes através de um dashboard central.

---

## 9. Filosofia Final

> "O Web App não é uma interface. É o centro nervoso do sistema."

Ele é onde a inteligência artificial encontra a supervisão humana. O frontend do Viral Discovery Engine é a ferramenta que permite ao operador navegar no oceano de dados do YouTube e extrair ouro em forma de atenção humana.

---

## Relatório Técnico de Engenharia Reversa

### Problemas Reais Encontrados
1. **Concurrency Bottleneck**: O uso de `threading.Thread` no Flask sem uma fila de tarefas robusta (como Celery) pode levar à perda de controle de workers se o processo principal do Flask cair.
2. **SQLite Contention**: Consultas pesadas de agregação (ex: `AVG(value)` na tabela de métricas) durante picos de escrita causam latência perceptível na UI.
3. **JS State Sync**: O `app.js` reconstrói partes do DOM do zero a cada polling, o que causa perda de foco se o usuário estiver interagindo com um elemento no momento do refresh.

### Limitações
- A interface atual é single-host (roda apenas na máquina local).
- Não há persistência de estado da UI (se der refresh, o modal aberto fecha).

### Prioridades Críticas
1. **Migração para WAL Mode no SQLite** (Urgente para estabilidade).
2. **Refatoração do render de listas no JS** para usar templates ou fragmentos, evitando o `innerHTML` massivo.
3. **Implementação de WebSocket** para substituir o polling agressivo.

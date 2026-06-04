# EVENT_RUNTIME_REPORT

## Arquitetura Implementada

A arquitetura do Attention OS foi migrada de um modelo de "State Polling/Global Sync" para um **Event-Driven Runtime** real.

### Componentes Core
1.  **Backend (web_app.py)**: Agora atua como o *Source of Truth* atômico. Ele emite eventos SSE contendo patches incrementais. Nunca envia o estado global da aplicação.
2.  **EventBus (event-bus.js)**: Distribuidor de eventos desacoplado que roteia mensagens do SSE para o Runtime.
3.  **Runtime Registry (runtime-registry.js)**: 
    -   `nodes`: Cache O(1) de referências a elementos do DOM.
    -   `meta`: Metadados transitórios e patches mesclados.
    -   `dirty`: Fila de entidades que precisam de atualização visual.
4.  **DOM Projector (app.js)**: Uma função pura de projeção que recebe patches e os projeta diretamente nas propriedades dos elementos DOM existentes, sem loops de `innerHTML`.

## Análise de Performance

### Batching via RAF (RequestAnimationFrame)
Implementamos um loop de renderização baseado em `requestAnimationFrame`. Em vez de atualizar o DOM imediatamente a cada evento (o que causaria reflows excessivos), o sistema marca a entidade como `dirty`. O loop do runtime limpa a fila de sujos e aplica as projeções em um único frame.

### O(1) DOM Access
O uso do `runtime.nodes` Map elimina a necessidade de `document.querySelector` durante os loops de atualização. O acesso à referência do elemento é direto e instantâneo.

## Comportamento do Replay SSE
O backend utiliza "watermarks" baseados em timestamps de banco de dados. Ao conectar ou reconectar, o backend faz o replay de todos os eventos desde o último timestamp conhecido. O frontend, sendo reativo e baseado em patches incrementais, reconstrói o estado visual automaticamente à medida que os eventos chegam, sem necessidade de um snapshot inicial pesado.

## Gargalos Restantes
-   **Initial Hydration**: Atualmente o sistema depende totalmente do replay de eventos. Se o histórico de eventos for muito longo, a hidratação inicial pode demorar alguns segundos.
-   **Memory Leak**: Precisamos monitorar se entidades removidas do DOM estão sendo corretamente limpas dos Maps `nodes` e `meta` no RuntimeRegistry.

## Próximos Riscos Arquiteturais
1.  **Concorrência de Patches**: Se dois eventos de patch chegarem fora de ordem (embora o SSE garanta ordem por conexão TCP), o estado final pode ficar inconsistente. O uso de timestamps no patch ajuda a mitigar isso.
2.  **Complexidade de Projeção**: À medida que a UI fica mais complexa, a função `updateNodeProperties` pode se tornar um monólito difícil de manter. Uma abordagem de "Component Projectors" pode ser necessária.

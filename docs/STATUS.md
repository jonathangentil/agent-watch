# Estado da entrega — 2026-11-12

V2 entregue: aba **Kanban** com replay, além do Painel e do Escritório da V1.

## Entrega da V2

- Terceira aba **Kanban** na janela gráfica e `--kanban` na CLI; o login preserva `view=kanban`.
- Tarefas da execução em foco nas colunas Backlog, Em progresso, Aguardando testes, Em testes, Pronto e Bloqueado, decididas por evidência em `board.build_tasks` e publicadas como `tasks` no snapshot (`version` continua 1).
- Leitor da Alethe expõe contrato, revisão declarada, revisão do diff, existência do `diff.patch` (sem lê-lo), índice da onda e os `gate-NN.json`. O vínculo entre Developer e testador é deduzido pela onda e confirmado pelo gate; gate com revisão divergente não aprova nem bloqueia o cartão.
- Rodadas de correção mantêm os cartões rejeitados em Bloqueado, esmaecidos e marcados como substituídos.
- Cartões detalhados, painel de detalhes que começa fechado (botão e `Esc`), evidência da coluna e testador selecionável pelo teclado.
- Movimento FLIP de cartão arrastado: levantar, viajar 780 ms, vizinhos em 280 ms, 140 ms entre movimentos, até 6 animações por snapshot; histórico não anima; Pausar e Movimento reduzido compartilhados com o Escritório.
- **Replay** das transições registradas: lotes de 1 s real, pausa de até 0,5 s depois que o último cartão do lote assenta, 1×/2×/4×, barra de posição, relógio no horário real e retorno ao vivo. No replay, os cartões mostram só dados que não dependem do momento.
- **Apenas ativos** passou a filtrar só as execuções; os agentes concluídos ou com falha da execução em foco continuam visíveis.

## Verificação da V2

- **200 testes Python** e **77 testes JavaScript** em 8 arquivos.
- **83 verificações no Chromium** contra a demonstração, em `tests/web/kanban-*smoke.mjs`: colunas, cartões, texto malicioso inerte, foco, acessibilidade, keyframes e durações, destino fora da área, preferências, barra lateral, três temas e quatro larguras sem rolagem lateral, e replay estável em três execuções seguidas.
- `tests/web/browser-smoke.mjs` atualizado para os novos módulos; continua aprovado.
- Leitura real somente de metadados com o código atual: 6 projetos, 20 execuções e 161 tarefas (150 Alethe, 8 Claude, 3 Codex); a última transição coincide com a coluna em todas as tarefas.
- Implementação orquestrada pela Alethe, com gates de Reviewer e QA independentes em cada etapa: etapa 1 APPROVED em `rev-8098586ecfe57d03`, etapa 2 em `rev-1c812f572da4477a` (26/26 critérios) e etapa 3 em `rev-4b44d39e87718a43` (40/40). Os defeitos encontrados nas revisões e no Chromium foram corrigidos com testes de regressão.

## Limites conhecidos da V2

As colunas de teste só se aplicam ao pipeline da Alethe. O replay reproduz apenas transições com evidência nos artefatos e omite nos cartões o que depende do momento. Com horário ausente, a transição entra na ordem lógica, marcada como sem horário.

# Estado da V1 — 2026-11-10

V1 implementada e instalada localmente, com o comando local `./run.sh`.

## Entrega

- TUI Textual e janela gráfica com Painel / Escritório, seleção preservada e janela compacta.
- Nome público **Agent Watch** nas interfaces e no comando `agent-watch`; alias `alethe-tui` preservado.
- Três temas gráficos: Atual, Aura escuro e Claro, com preferência salva por endereço local no navegador.
- `./service.sh start|status|stop`: monitor em segundo plano na porta 3010, com controle privado e proteção contra PID reutilizado.
- Leitores somente leitura da Alethe, subagentes Claude Code e subagentes Codex.
- Vários projetos e execuções simultâneos; relações comprovadas por IDs de sessão.
- Cena com todos os agentes filtrados, sem paginação, com colunas conforme a largura e crescimento vertical. Líder separado dos workers; estados e interações conforme os eventos disponíveis. Modo Charme explicitamente decorativo.
- Envelopes animados na delegação e na entrega comprovada do resultado; conclusão sem entrega gera um indicador junto ao agente. Até três passagens por evento, remoção automática e opção persistente Cartas de tarefas para ocultar.
- Lista lateral de execuções nas duas apresentações, respeitando origem e limitada à altura do conteúdo, com paginação quando necessário. Linha inteira da tabela seleciona o agente.
- Apenas ativos também filtra as duas barras laterais e o seletor de execução. Considera execução ou agentes em execução/na fila, respeitando a origem; estado desconhecido sozinho não é atividade. A seleção se ajusta quando a execução deixa de estar ativa.
- Função comprovada como nome, identificador/onda preservados; tarefas da Alethe recuperadas do `prompt.txt`, resumo no snapshot e detalhe completo sob demanda. Modelo e effort na dica do personagem.
- `.env` local com múltiplas pastas de projetos (`AGENT_WATCH_PROJECT_DIRS`); `.env.example` versionável.
- Configuração de raízes adicionais, demonstração sintética e servidor local autenticado.
- Consumo de tokens por agente e total da execução no Painel, incluindo cache informado sem duplicação e totais parciais qualificados; saída com altura de 420 px e fonte preservada.

## Verificação

- **110 testes Python passaram**, incluindo TUI, encerramento, leitores, correlação tardia, retenção de histórico, HTTP local e ciclo do monitor em segundo plano.
- **27 testes JavaScript passaram** em quatro arquivos (executados diretamente com Node para evitar a restrição de subprocessos do sandbox).
- Navegador contra servidor HTTP real e fontes sintéticas: marca Agent Watch, três temas persistentes, três leitores, dois projetos, três execuções, troca de interface e descoberta/evento de uma nova onda em até cinco segundos.
- Validação no Chromium: todos os agentes na sala, seleção pela linha inteira, barra lateral nas duas apresentações, filtro de origem e quatro larguras de tela, sem erros JavaScript.
- Leitura real somente leitura confirmou agrupamento das worktrees removidas e disponibilidade das tarefas; não foram impressas nem versionadas transcrições reais.
- A instalação local foi atualizada junto do código: o serviço usava uma cópia antiga em `site-packages`.
- Após atualização da instalação e reinício, Chromium consultou a API real da porta 3010 e confirmou 5 projetos, 15 execuções, nenhuma pasta `skill-*` como projeto, tarefa acessível, dica com modelo/effort, filtro de origem e barra lateral no Escritório; zero erros JavaScript.
- Revisão independente encontrou dois problemas importantes: datas de execuções nativas ausentes e eventos desatualizados após correlação tardia. Ambos foram corrigidos com testes de regressão.

Evidências locais ignoradas pelo Git: `.superpowers/implementation/final-pytest.log` e `real-browser.log`.

## Limites conhecidos

A aplicação acompanha artefatos locais persistidos nas raízes conhecidas. Não garante detecção de sessões remotas/temporárias sem histórico, nem de raízes personalizadas não cadastradas. O estado aparece não confirmado quando o formato não oferece evidência suficiente. Silêncio não prova travamento; conclusão de um turno não prova recebimento do resultado pelo lead.

Não houve alteração de hooks, configurações de CLI, SQLite, históricos ou processos de agentes. As capturas em `docs/images/` usam dados fictícios.

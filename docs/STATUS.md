# Estado da entrega — 2026-11-10

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
- Kanban permanece no roadmap da V2, fora desta entrega.

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

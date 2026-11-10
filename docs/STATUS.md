# Estado da entrega — 2026-11-10

V1 implementada e instalada em `agent-watch`, com o comando local `./run.sh`.

## Entrega

- TUI Textual e janela gráfica com Painel / Escritório, seleção preservada e janela compacta.
- Leitores somente leitura da Alethe, subagentes Claude Code e subagentes Codex.
- Vários projetos e execuções simultâneos; relações comprovadas por IDs de sessão.
- Cena paginada, líder separado dos workers, estados e interações conforme os eventos disponíveis. Modo Charme explicitamente decorativo.
- Configuração de raízes adicionais, demonstração sintética e servidor local autenticado.
- Kanban permanece no roadmap da V2, fora desta entrega.

## Verificação

- **65 testes Python passaram**, incluindo TUI, encerramento, leitores, correlação tardia, retenção de histórico e HTTP local.
- Três arquivos de testes JavaScript passaram.
- Navegador contra servidor HTTP real e fontes sintéticas: três leitores, dois projetos, três execuções, troca de interface e descoberta/evento de uma nova onda em até cinco segundos.
- Leitura real somente de metadados confirmou agentes das três fontes; não foram impressas nem versionadas transcrições reais.
- Revisão independente encontrou dois problemas importantes: datas de execuções nativas ausentes e eventos desatualizados após correlação tardia. Ambos foram corrigidos com testes de regressão.

Evidências locais ignoradas pelo Git: `.superpowers/implementation/final-pytest.log` e `real-browser.log`.

## Limites conhecidos

A aplicação acompanha artefatos locais persistidos nas raízes conhecidas. Não garante detecção de sessões remotas/temporárias sem histórico, nem de raízes personalizadas não cadastradas. O estado aparece não confirmado quando o formato não oferece evidência suficiente. Silêncio não prova travamento; conclusão de um turno não prova recebimento do resultado pelo lead.

Não houve alteração de hooks, configurações de CLI, SQLite, históricos ou processos de agentes. As antigas prévias de `docs/superpowers/previews/` usam dados fictícios.

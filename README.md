# Alethe TUI

Monitor local, somente leitura, para orquestrações Alethe e subagentes nativos do Claude Code e Codex.

## Abrir

Na pasta `agent-watch`:

```sh
./run.sh                       # TUI no terminal
./run.sh --web --office         # janela gráfica, iniciando no escritório
./run.sh --web                  # janela gráfica, iniciando no painel
./run.sh --web --office --demo  # demonstração explicitamente fictícia
```

A janela gráfica oferece **Painel / Escritório**, preservando projeto, execução e agente selecionados. O botão **Janela compacta** abre uma janela menor. Na TUI, `o` abre o escritório e `p` abre o painel.

Mantenha o comando aberto para acompanhar novas execuções. `Ctrl+C` encerra o servidor gráfico; `q` encerra a TUI. Isso não interrompe os agentes monitorados. A primeira URL exibida pelo comando autoriza somente essa sessão local; não a publique.

## Instalação em outra máquina

Python 3.11 ou superior e `uv`:

```sh
uv sync --extra dev
uv run alethe-tui --web --office
```

O ambiente desta pasta já está em `.venv/`. Dependências resolvidas em `uv.lock`; nenhuma chave de API é necessária para monitorar os arquivos locais.

## Fontes e vários projetos

- Alethe: `~/.config/alethe/orchestrations`, respeitando `XDG_CONFIG_HOME`, `ALETHE_ORCHESTRATE_POLICY` e `ALETHE_ORCHESTRATE_HOME`.
- Claude Code: `~/.claude/projects`, respeitando `CLAUDE_CONFIG_DIR`.
- Codex: `~/.codex/sessions`, respeitando `CODEX_HOME`.

A coleta acompanha todas as raízes configuradas. Os filtros de projeto e execução mudam a visualização, sem parar a coleta das outras execuções. Worktrees são agrupadas pela raiz comum do Git. Nomes iguais em projetos diferentes conservam suas identidades.

```sh
./run.sh --root /outra/raiz/alethe --root /mais/uma/raiz
./run.sh --claude-root /pasta/projects --codex-root /pasta/sessions
./run.sh --web --no-open --port 8765
```

Configuração opcional em `~/.config/alethe-tui/config.toml`:

```toml
roots = ["/outra/raiz/alethe"]
interval = 1.0
verify_pids = true
```

Use `--no-pid-check` para arquivos copiados de outra máquina: PIDs locais não verificam processos remotos. Uma raiz personalizada desconhecida precisa ser cadastrada; a aplicação não varre todo o disco.

## Estados e animações

Delegação, conclusão e entrega de resultado são situações distintas. A cena anima os eventos identificáveis disponíveis na fonte. Eventos históricos não são reapresentados como novos a cada atualização.

O modo **Charme decorativo** é opcional; caminhadas e acenos desse modo não comprovam mensagens entre modelos. Pausar animações não pausa agentes. O escritório mostra até seis workers por página e mantém o líder separado das contagens.

Os formatos locais variam por versão. Onde não há evidência suficiente, aparece **estado não confirmado**. No Claude, uma resposta concluída pode ser retomada; não representa encerramento permanente do agente. Silêncio não prova travamento. Resultados do Codex e da Alethe não são rotulados como recebidos pelo lead sem um evento que comprove isso.

Não há alteração de hooks, configurações de CLI, históricos, SQLite ou agentes. Raciocínio interno não é exibido. O servidor fica em `127.0.0.1`, com cookie de sessão, e não envia os dados a serviços externos.

## Validação

```sh
.venv/bin/python -m pytest
node --test tests/web/*.test.mjs
```

O smoke `tests/web/real-server-smoke.mjs` usa Playwright e Chromium já instalados, apontados por `PLAYWRIGHT_MODULE` e `CHROMIUM_EXECUTABLE`. Ele inicia um servidor real com fontes sintéticas; não chama modelos nem altera históricos reais.

Estado da entrega e evidências: [docs/STATUS.md](docs/STATUS.md). Desenho e plano em `docs/superpowers/`. As prévias HTML dessa pasta usam dados fictícios e ficam preservadas como referência visual.

## V2

**Kanban como terceira interface**, solicitado pelo usuário. Fora desta V1; registrado em [docs/ROADMAP.md](docs/ROADMAP.md).

# Alethe TUI

Monitor local de agentes com TUI e uma janela opcional com bonequinhos trabalhando.

## Estado do projeto

Desenho e prévias interativas preparados. A aplicação funcional ainda não foi implementada; aguarda aprovação do desenho.

Decisões confirmadas pelo usuário em 2026-11-09:

- TUI que permanece aberta e detecta novas execuções.
- Aplicação independente acompanhando a Alethe.
- Prévia visual no navegador.
- Janela compacta com bonequinhos trabalhando e interagindo por charme.
- Detectar também subagentes nativos do Claude Code e do Codex.
- Manter o painel detalhado e o escritório visual, com alternância preservando a seleção.
- Acompanhar várias orquestrações em vários projetos ao mesmo tempo, com resumo geral e filtros.
- Projeto separado em `agent-watch`.

## Desenho e prévias

- [Desenho proposto](docs/superpowers/specs/2026-11-09-alethe-tui-design.md).
- [Prévia da TUI](docs/superpowers/previews/alethe-tui.html).
- [Prévia do escritório](docs/superpowers/previews/alethe-office.html).
- [Prévia unificada: projetos, execuções e duas interfaces](docs/superpowers/previews/alethe-preview.html).

As prévias usam dados fictícios. É possível abrir os HTMLs diretamente no navegador; o servidor de brainstorming acrescenta atualização automática. A cena e os filtros não controlam agentes reais.

## Direção técnica proposta

Python + Textual para o terminal; painel detalhado e escritório SVG/CSS/JavaScript na janela; um monitor compartilhado que lê os artefatos locais da Alethe, Claude Code e Codex. A leitura inicial independe de hooks, modificações nos executores ou novas chamadas a modelos.

Não há comando instalável ainda. O nome proposto para a aplicação é `alethe-tui`.

## Próximo passo

V2 solicitada: **Kanban como terceira interface**. Planejamento em [docs/ROADMAP.md](docs/ROADMAP.md); a V1 mantém Painel e Escritório.

Revisar/aprovar o desenho e a prévia atualizados. Depois, preparar o plano e implementar os adaptadores, a TUI e a cena com testes de detecção, estado e hierarquia.

Os arquivos de sessão da prévia em `.superpowers/` ficam fora do Git; não publicar chaves do servidor, transcrições ou configurações de autenticação.

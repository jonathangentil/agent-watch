"""Interface de terminal sobre snapshots do monitor compartilhado."""
from __future__ import annotations

import asyncio
from functools import partial
from datetime import datetime, timezone
import webbrowser

from rich.text import Text
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import DataTable, Footer, Header, Input, RichLog, Select, Static, Tree

LABELS = {"queued": "aguardando", "running": "executando", "succeeded": "concluído", "turn_complete": "turno concluído",
          "failed": "falhou", "timed_out": "tempo esgotado", "interrupted": "interrompido", "stopped": "parado", "skipped": "ignorado", "unknown": "não confirmado"}


def _elapsed(actor):
    try:
        start = datetime.fromisoformat(actor["started_at"].replace("Z", "+00:00"))
        end = datetime.fromisoformat(actor["finished_at"].replace("Z", "+00:00")) if actor.get("finished_at") else datetime.now(timezone.utc)
        seconds = max(0, int((end - start.replace(tzinfo=start.tzinfo or timezone.utc)).total_seconds()))
        return f"{seconds // 60:02d}m {seconds % 60:02d}s"
    except (TypeError, KeyError, ValueError, AttributeError):
        return "—"


class AgentApp(App):
    TITLE = "ALÊTHE · agentes trabalhando"
    CSS = """
    Screen { background: #101419; color: #dce7df; }
    #overview { height: 2; padding: 0 1; color: #b8e88c; }
    #filters { height: 3; }
    #project, #execution { width: 1fr; }
    #search { width: 1fr; }
    #workspace { height: 1fr; }
    #sessions { width: 27%; min-width: 20; border-right: solid #354538; }
    #right { width: 1fr; }
    #agents { height: 1fr; min-height: 4; }
    #agent-meta { height: 3; padding: 0 1; }
    #detail { height: 8; border-top: solid #354538; padding: 0 1; }
    #hint { height: 1; color: #9eafa0; padding: 0 1; }
    """
    BINDINGS = [("q", "quit", "Sair"), ("/", "search", "Buscar"), ("a", "active", "Ativas"),
                ("l", "detail_kind", "Saída/resultado"), ("f", "follow", "Seguir saída"),
                ("r", "refresh", "Atualizar"), ("o", "office", "Escritório"), ("p", "panel", "Painel")]

    def __init__(self, monitor, server=None):
        super().__init__()
        self.monitor = monitor
        self.server = server
        self.selected_agent_id = ""
        self._project_id = "all"
        self._execution_id = ""
        self._remembered = {}
        self._active_only = False
        self._detail_kind = "output"
        self._detail_text = ""
        self._last_detail_key = None
        self._project_options = []
        self._execution_options = []
        self._tree_signature = None
        self._rendering = False
        self._data = {}

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Static("Aguardando fontes locais…", id="overview")
        with Horizontal(id="filters"):
            yield Select([("Todos os projetos", "all")], allow_blank=False, value="all", id="project")
            yield Select([("Aguardando execuções", "")], allow_blank=False, value="", id="execution")
            yield Input(placeholder="/ buscar agente, modelo ou tarefa", id="search")
        with Horizontal(id="workspace"):
            yield Tree("Projetos / execuções", id="sessions")
            with Vertical(id="right"):
                yield DataTable(id="agents", cursor_type="row", zebra_stripes=True)
                yield Static("Selecione um agente", id="agent-meta", markup=False)
                yield RichLog(id="detail", wrap=True, markup=False, highlight=False, max_lines=2000, min_width=1)
        yield Static("Somente leitura · q fecha o monitor e mantém os agentes em execução", id="hint", markup=False)
        yield Footer()

    def on_mount(self):
        table = self.query_one("#agents", DataTable)
        table.add_columns("Agente", "Origem / modelo", "Estado", "Tempo", "Sem saída")
        self.sync_snapshot()
        self.set_interval(1, self.sync_snapshot)
        table.focus()

    def sync_snapshot(self):
        if not self.is_mounted:
            return
        self._rendering = True
        data = self.monitor.snapshot()
        self._data = data
        totals = data["totals"]
        summary = f"{totals['projects']} projetos · {totals['executions']} execuções · {totals['agents']} agentes · {totals['running']} executando · {totals['queued']} aguardando"
        if self._active_only:
            summary += " · filtro: ativos"
        if data["diagnostics"]:
            summary += f" · {len(data['diagnostics'])} avisos de fonte"
        self.query_one("#overview", Static).update(Text(summary))
        projects = [(p["name"], p["id"]) for p in data["projects"]]
        options = [("Todos os projetos", "all")] + projects
        if self._project_id not in {p[1] for p in options}:
            self._project_id = "all"
        widget = self.query_one("#project", Select)
        if options != self._project_options:
            widget.set_options([(Text(label), key) for label, key in options])
            self._project_options = options
        if widget.value != self._project_id:
            widget.value = self._project_id
        executions = [e for e in data["executions"] if self._project_id == "all" or self._project_id in (e.get("project_ids") or [e["project_id"]])]
        if self._execution_id not in {e["id"] for e in executions}:
            self._execution_id = executions[0]["id"] if executions else ""
        choices = [(f"{e['project_name']} / {e['title']} · {e['source']}", e["id"]) for e in executions] or [("Aguardando execuções", "")]
        widget = self.query_one("#execution", Select)
        if choices != self._execution_options:
            widget.set_options([(Text(label), key) for label, key in choices])
            self._execution_options = choices
        if widget.value != self._execution_id:
            widget.value = self._execution_id
        query = self.query_one("#search", Input).value.casefold()
        actors = [a for a in data["agents"] if a["execution_id"] == self._execution_id
                  and (not self._active_only or a["status"] in {"running", "queued"})
                  and query in " ".join(str(a.get(k) or "") for k in ("name", "model", "task", "provider")).casefold()]
        preferred = self._remembered.get(self._execution_id, self.selected_agent_id)
        self.selected_agent_id = preferred if any(a["id"] == preferred for a in actors) else (actors[0]["id"] if actors else "")
        table = self.query_one("#agents", DataTable)
        table.clear()
        for actor in actors:
            style = "green" if actor["status"] == "running" else "yellow" if actor["status"] == "queued" else "red" if actor["status"] in {"failed", "interrupted", "timed_out"} else ""
            idle = actor.get("idle_seconds")
            table.add_row(Text(actor["name"]), Text(f"{actor['source']} / {actor.get('model') or 'não informado'}"),
                          Text(LABELS.get(actor["status"], actor["status"]), style=style), _elapsed(actor),
                          f"{int(idle)}s" if isinstance(idle, (int, float)) else "—", key=actor["id"])
        if actors:
            table.move_cursor(row=next(i for i, a in enumerate(actors) if a["id"] == self.selected_agent_id))
        signature = [(e["id"], e["title"], e["project_id"]) for e in executions]
        if signature != self._tree_signature:
            tree = self.query_one("#sessions", Tree)
            tree.clear()
            nodes = {}
            for execution in executions:
                key = execution["project_id"]
                node = nodes.setdefault(key, tree.root.add(Text(execution["project_name"]), expand=True)) if key not in nodes else nodes[key]
                node.add_leaf(Text(execution["title"]), data=execution["id"])
            tree.root.expand()
            self._tree_signature = signature
        self._rendering = False
        self._show_selected()

    def _show_selected(self):
        actor = next((a for a in self._data.get("agents", []) if a["id"] == self.selected_agent_id), None)
        if actor:
            self._remembered[self._execution_id] = actor["id"]
            metadata = f"{actor['name']} · {self._detail_kind} · {actor.get('evidence') or 'estado não confirmado'}\n{actor.get('task') or 'Tarefa não informada'}"
        else:
            metadata = "Nenhum agente neste filtro. Aguardando fontes ou uma nova execução."
        self.query_one("#agent-meta", Static).update(Text(metadata))
        if actor:
            # Create the coroutine only when its worker actually runs. A rapid
            # selection change may cancel a queued worker before it starts.
            self.run_worker(partial(self._load_detail, actor["id"], self._detail_kind), group="detail", exclusive=True)
        else:
            self.query_one("#detail", RichLog).clear()
            self._detail_text = ""

    async def _load_detail(self, actor_id, kind):
        try:
            text = await asyncio.to_thread(self.monitor.detail, actor_id, kind)
        except (KeyError, OSError, ValueError, ImportError) as error:
            text = f"Detalhe indisponível: {error}"
        if actor_id != self.selected_agent_id or kind != self._detail_kind or not self.is_mounted:
            return
        key = actor_id, kind
        if key != self._last_detail_key or text != self._detail_text:
            log = self.query_one("#detail", RichLog)
            log.clear()
            log.write(Text(text or "Ainda não há saída disponível."))
            self._detail_text, self._last_detail_key = text, key

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted):
        if self._rendering or event.row_key.value is None:
            return
        actor_id = str(event.row_key.value)
        if actor_id != self.selected_agent_id:
            self.selected_agent_id = actor_id
            self._show_selected()

    def on_input_changed(self, event: Input.Changed):
        if event.input.id == "search":
            self.sync_snapshot()

    def on_select_changed(self, event: Select.Changed):
        # set_options/value emit queued changes; ignore superseded messages.
        if self._rendering or not isinstance(event.value, str) or event.value != event.select.value:
            return
        if event.select.id == "project" and event.value != self._project_id:
            self._project_id = event.value
            self.sync_snapshot()
        elif event.select.id == "execution" and event.value != self._execution_id:
            self._execution_id = event.value
            self.sync_snapshot()

    def on_tree_node_selected(self, event: Tree.NodeSelected):
        if isinstance(event.node.data, str):
            self._execution_id = event.node.data
            self.sync_snapshot()

    def action_search(self):
        self.query_one("#search", Input).focus()

    def action_active(self):
        self._active_only = not self._active_only
        self.sync_snapshot()

    def action_follow(self):
        log = self.query_one("#detail", RichLog)
        log.auto_scroll = not log.auto_scroll
        self.notify("Acompanhar saída: " + ("ligado" if log.auto_scroll else "desligado"))

    def action_detail_kind(self):
        kinds = ["output", "result", "error", "task"]
        self._detail_kind = kinds[(kinds.index(self._detail_kind) + 1) % len(kinds)]
        self._show_selected()

    async def action_refresh(self):
        await asyncio.to_thread(self.monitor.refresh)
        self.sync_snapshot()

    async def _open(self, view):
        if self.server:
            opened = await asyncio.to_thread(webbrowser.open, self.server.url(view=view))
            if not opened:
                self.notify("O navegador não abriu. O endereço está na saída inicial do comando.")
        else:
            self.notify("Servidor gráfico não disponível nesta sessão.")

    async def action_office(self):
        await self._open("office")

    async def action_panel(self):
        await self._open("panel")

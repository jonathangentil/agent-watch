import importlib
import importlib.util
import json

from alethe_tui.model import Agent


def detail(agent, kind="output"):
    assert importlib.util.find_spec("alethe_tui.details"), "safe details are not implemented"
    return importlib.import_module("alethe_tui.details").read_agent_detail(agent, kind)


def agent(path=None, source="alethe", **fields):
    return Agent("synthetic", source, "synthetic", "execution", "project", "Example",
                 output_path=str(path) if path else None, **fields)


def test_details_safe_text_removes_ansi_terminal_links_html_rich_and_private_blocks(tmp_path):
    path = tmp_path / "stdout.log"
    path.write_text('\x1b[31mVisible\x1b[0m \x1b]8;;https://invalid.example\x07link\x1b]8;;\x07\n'
                    '[bold]Public[/bold] <script>bad()</script>\n<think>PRIVATE\nSECRET</think>\nFinal\x00')
    text = detail(agent(path))
    assert "Visible" in text and "Public" in text and "Final" in text
    assert all(part not in text for part in ("\x1b", "\x00", "PRIVATE", "SECRET", "<script>", "[bold]"))


def test_details_jsonl_allowlists_public_text_tools_and_excludes_reasoning_channels(tmp_path):
    path = tmp_path / "native.jsonl"
    rows = [
        {"type": "response_item", "payload": {"type": "reasoning", "summary": [{"text": "PRIVATE1"}]}},
        {"type": "response_item", "payload": {"type": "message", "channel": "analysis", "content": [{"type": "output_text", "text": "PRIVATE2"}]}},
        {"type": "response_item", "payload": {"type": "message", "role": "assistant", "channel": "final", "content": [{"type": "output_text", "text": "Public answer"}]}},
        {"type": "response_item", "payload": {"type": "function_call", "name": "exec_command", "arguments": "PUBLIC COMMAND"}},
        {"type": "assistant", "message": {"content": [{"type": "thinking", "thinking": "PRIVATE3"}, {"type": "text", "text": "Claude answer"}, {"type": "tool_use", "name": "Read", "input": {"file_path": "example.py"}}]}},
        {"type": "unknown", "text": "PRIVATE4"},
    ]
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n{partial")
    text = detail(agent(path, "codex"))
    assert all(part in text for part in ("Public answer", "exec_command", "Claude answer", "Read"))
    assert "PRIVATE" not in text and "partial" not in text


def test_details_tail_is_bounded_by_bytes_and_lines_and_drops_cut_record(tmp_path):
    path = tmp_path / "stdout.log"
    path.write_text("OLD" + "x" * 70000 + "\n" + "\n".join(f"line-{i}" for i in range(3000)))
    text = detail(agent(path))
    assert len(text.encode()) <= 65536
    assert len(text.splitlines()) <= 2000
    assert "OLD" not in text and "line-0\n" not in text
    assert text.endswith("line-2999")


def test_detail_kinds_and_missing_files_use_only_agent_fields(tmp_path):
    result = tmp_path / "result.md"
    error = tmp_path / "stderr.log"
    result.write_text("Result")
    error.write_text("Error")
    example = agent(tmp_path / "absent", result_path=str(result), error_path=str(error), task="Task")
    assert detail(example, "result") == "Result"
    assert detail(example, "error") == "Error"
    assert detail(example, "task") == "Task"
    assert isinstance(detail(example), str)
    assert detail(example, str(result)) == ""


def test_alethe_structured_stdout_never_falls_back_to_raw_json_after_tail_cut(tmp_path):
    path = tmp_path / "stdout.log"
    path.write_text(json.dumps({"type": "reasoning", "text": "x" * 70000}) + "\n")
    with path.open("a") as handle:
        handle.write(json.dumps({"type": "unknown", "text": "PRIVATE"}) + "\n")
        handle.write(json.dumps({"type": "result", "result": "Public result"}) + "\n")
    text = detail(agent(path))
    assert "PRIVATE" not in text and "Public result" in text


def test_details_never_reveal_private_tool_result_blocks_or_event_analysis(tmp_path):
    path = tmp_path / "native.jsonl"
    rows = [
        {"type": "assistant", "message": {"channel": "analysis", "content": [{"type": "tool_use", "name": "PRIVATE"}]}},
        {"type": "event_msg", "payload": {"type": "agent_message", "channel": "analysis", "message": "PRIVATE"}},
        {"type": "assistant", "message": {"content": [{"type": "tool_result", "content": [
            {"type": "thinking", "thinking": "PRIVATE"}, {"type": "text", "text": "Public tool result"}]}]}},
    ]
    path.write_text("\n".join(map(json.dumps, rows)) + "\n")
    text = detail(agent(path, "codex"))
    assert "Public tool result" in text and "PRIVATE" not in text


def test_details_filter_json_partial_last_line_even_when_decodable(tmp_path):
    path = tmp_path / "native.jsonl"
    path.write_text(json.dumps({"type": "result", "result": "Public"}) + "\n" +
                    json.dumps({"type": "result", "result": "Not yet committed"}))
    assert detail(agent(path, "claude")) == "Public"


def test_details_mixed_stdout_never_displays_unknown_json_payload(tmp_path):
    path = tmp_path / "stdout.log"
    path.write_text('Public banner\n' + json.dumps({"type": "thinking", "thinking": "PRIVATE"}) + "\n" +
                    json.dumps({"type": "result", "result": "Public result"}) + "\n")
    text = detail(agent(path))
    assert "Public banner" in text and "Public result" in text and "PRIVATE" not in text


def test_native_result_detail_returns_last_public_final_instead_of_task_or_tools(tmp_path):
    path = tmp_path / "native.jsonl"
    rows = [
        {"type": "event_msg", "payload": {"type": "user_message", "message": "Task"}},
        {"type": "event_msg", "payload": {"type": "task_complete", "last_agent_message": "Older result"}},
        {"type": "response_item", "payload": {"type": "function_call", "name": "Read"}},
        {"type": "event_msg", "payload": {"type": "task_complete", "last_agent_message": "Final result"}},
    ]
    path.write_text("\n".join(map(json.dumps, rows)) + "\n")
    assert detail(agent(path, "codex", result_path=str(path)), "result") == "Final result"

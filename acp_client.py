"""Small ACP v1 stdio client, independent of Hermes's private implementation.

The only executable is the operator-selected OpenCode CLI. All requested host
work is returned as remote tool calls; this module never executes model tools.
"""
from contextlib import contextmanager
import json
import math
import os
import queue
import signal
import subprocess
import threading
import time
from types import SimpleNamespace
import uuid

from .constants import DEFAULT_MODEL, FREE_MODELS, WORKSPACE, opencode_command

BRIDGE_MODE = "build"
MAX_FRAME = 4 * 1024 * 1024
OPEN_TAG, CLOSE_TAG = "<hermes_tool_call>", "</hermes_tool_call>"
CONTRACT = (
    "REMOTE TOOL PROTOCOL: This conversation belongs to Hermes, not OpenCode. "
    "All tools described below are REMOTE Hermes tools. To request one, emit ONLY "
    '<hermes_tool_call>{"id":"unique_call_id","type":"function","function":'
    '{"name":"tool_name","arguments":"{...}"}}</hermes_tool_call> as your final TEXT response. '
    "arguments must be a JSON object encoded as a JSON string. Stop after requesting the tool; "
    "Hermes executes it AFTER your response and supplies the result in the next transcript. "
    "Do NOT use native OpenCode tools, shell, files, skills, or subagents: those are blocked. "
    "A blocked native tool does not mean the corresponding remote Hermes tool is unavailable. "
    "Do not claim an action happened before a real tool result exists. If the transcript "
    "already contains the needed tool result, answer from it. If no tool is needed, answer normally."
)
# Only infrastructure/non-secret behavior values are forwarded. In particular,
# no HERMES_*, vendor API keys, tokens, inline OpenCode configuration or YOLO
# settings from the parent are inherited. The CLI owns its normal login in HOME.
CHILD_ENV_NAMES = frozenset({
    "PATH", "HOME", "USER", "LOGNAME", "USERPROFILE", "APPDATA", "LOCALAPPDATA",
    "SYSTEMROOT", "SystemRoot", "WINDIR", "COMSPEC", "PATHEXT", "TMPDIR", "TEMP", "TMP",
    "XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME", "XDG_STATE_HOME", "XDG_RUNTIME_DIR",
    "LANG", "LC_ALL", "LC_CTYPE", "LC_MESSAGES", "TZ", "TERM",
    "SSL_CERT_FILE", "SSL_CERT_DIR", "NODE_EXTRA_CA_CERTS", "REQUESTS_CA_BUNDLE",
    "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY",
    "http_proxy", "https_proxy", "all_proxy", "no_proxy",
})


class Record(SimpleNamespace):
    """Structural OpenAI-compatible result with no SDK dependency."""
    def model_dump(self, *, exclude_none=False, **kwargs):
        def dump(value):
            if isinstance(value, SimpleNamespace):
                return {key: dump(item) for key, item in vars(value).items()
                        if not (exclude_none and item is None)}
            if isinstance(value, list):
                return [dump(item) for item in value]
            if isinstance(value, dict):
                return {key: dump(item) for key, item in value.items()}
            return value
        return dump(self)


def child_environment():
    return {key: value for key, value in os.environ.items() if key in CHILD_ENV_NAMES}


def effective_timeout(value):
    if isinstance(value, (int, float)):
        seconds = float(value)
    else:
        values = [getattr(value, key, None) for key in ("read", "write", "connect", "pool")]
        seconds = max((float(item) for item in values if isinstance(item, (int, float))), default=900.0)
    if not math.isfinite(seconds) or seconds <= 0:
        raise ValueError("ACP timeout must be a finite positive number of seconds")
    return seconds


def options(option):
    """ACP select options can be flat or grouped. Never normalize model IDs."""
    result = []
    for item in option.get("options") or []:
        if not isinstance(item, dict):
            continue
        if isinstance(item.get("value"), str):
            result.append(item["value"])
        elif isinstance(item.get("options"), list):
            result.extend(child["value"] for child in item["options"]
                          if isinstance(child, dict) and isinstance(child.get("value"), str))
    return result


def config_option(session, category, required=None):
    candidates = [item for item in session.get("configOptions") or []
                  if isinstance(item, dict) and isinstance(item.get("id"), str)
                  and (item.get("id") == category or item.get("category") == category)]
    for item in candidates:
        if required is None or required in options(item):
            return item
    offered = sorted({value for item in candidates for value in options(item)})
    raise RuntimeError(f"OpenCode ACP required {category} {required!r} was not advertised; offered={offered!r}. No prompt was sent.")


def selected_value(result, config_id):
    return next((item.get("currentValue") for item in (result or {}).get("configOptions", [])
                 if isinstance(item, dict) and item.get("id") == config_id), None)


def render_content(content):
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        if any(isinstance(item, dict) and item.get("type") not in (None, "text", "input_text", "output_text") for item in content):
            raise ValueError("OpenCode Free ACP is text-only; image/audio attachments are not forwarded")
        return "\n".join(item if isinstance(item, str) else str(item.get("text", ""))
                         for item in content if isinstance(item, (str, dict)))
    return json.dumps(content, ensure_ascii=False)


def render_prompt(messages, tools=None, tool_choice=None):
    parts = [CONTRACT]
    if tools:
        parts.append("Remote Hermes tools (OpenAI function schemas):\n" + json.dumps(tools, ensure_ascii=False))
    if tool_choice is not None:
        parts.append("Remote tool choice: " + json.dumps(tool_choice, ensure_ascii=False))
    parts.append("Conversation transcript:")
    for message in messages or []:
        role = str(message.get("role", "context"))
        label = role.capitalize()
        if role == "tool":
            label += " result for " + str(message.get("tool_call_id", "unknown"))
        content = render_content(message.get("content"))
        if content:
            parts.append(label + ":\n" + content)
        if message.get("tool_calls"):
            parts.append("Assistant's prior remote tool requests:\n" + json.dumps(message["tool_calls"], ensure_ascii=False))
    parts.extend(["Continue from the latest user request, using actual tool results already in the transcript.", CONTRACT])
    return "\n\n".join(parts)


def parse_tool_calls(text, tools=None, tool_choice=None):
    allowed = {item["function"]["name"] for item in tools or []
               if isinstance(item, dict) and isinstance(item.get("function"), dict)
               and isinstance(item["function"].get("name"), str)}
    calls, prose, cursor, seen = [], [], 0, set()
    while True:
        start = text.find(OPEN_TAG, cursor)
        if start < 0:
            prose.append(text[cursor:])
            break
        prose.append(text[cursor:start])
        body_start = start + len(OPEN_TAG)
        body_start += len(text[body_start:]) - len(text[body_start:].lstrip())
        body, consumed = json.JSONDecoder().raw_decode(text[body_start:])
        end = body_start + consumed
        end += len(text[end:]) - len(text[end:].lstrip())
        if not text.startswith(CLOSE_TAG, end):
            raise ValueError("Incomplete remote tool-call envelope; no tool was dispatched")
        function = body.get("function") if isinstance(body, dict) else None
        if not isinstance(body, dict) or body.get("type") != "function" or not isinstance(function, dict) or function.get("name") not in allowed:
            raise ValueError("Unadvertised or invalid remote tool call; no tool was dispatched")
        if tool_choice == "none":
            raise ValueError("Remote tool call violates tool_choice=none")
        if isinstance(tool_choice, dict) and function["name"] != (tool_choice.get("function") or {}).get("name"):
            raise ValueError("Remote tool call violates the selected function")
        arguments = function.get("arguments", "{}")
        decoded = json.loads(arguments) if isinstance(arguments, str) else arguments
        if not isinstance(decoded, dict):
            raise ValueError("Remote tool arguments must be a JSON object")
        call_id = body.get("id", "acp_" + uuid.uuid4().hex)
        if not isinstance(call_id, str) or not call_id.strip() or call_id in seen:
            raise ValueError("Remote tool IDs must be nonempty and unique")
        seen.add(call_id)
        calls.append(Record(id=call_id, type="function", call_id=call_id, response_item_id=None,
                            function=Record(name=function["name"], arguments=json.dumps(decoded, ensure_ascii=False))))
        cursor = end + len(CLOSE_TAG)
    return calls, "\n".join(part.strip() for part in prose if part.strip())


class OpenCodeFreeClient:
    HERMES_SKIP_TRANSPORT_WRAP = True
    HERMES_SKIP_ASYNC_WRAP = True

    def __init__(self, *, command=None, args=None, acp_command=None, acp_args=None, **kwargs):
        self.command = acp_command or command or opencode_command()
        self.args = list(acp_args or args or ["acp"])
        self.workspace = str(WORKSPACE)
        self.base_url = "acp://opencode-free"
        self.chat = Record(completions=Record(create=self._create_chat_completion))
        self.is_closed = False
        self._cancelled = threading.Event()
        self._lock = threading.Lock()
        self._processes = set()

    @staticmethod
    def _signal(proc, force=False):
        try:
            if os.name == "posix":
                os.killpg(proc.pid, signal.SIGKILL if force else signal.SIGTERM)
            elif proc.poll() is None:
                proc.kill() if force else proc.terminate()
        except (ProcessLookupError, PermissionError, OSError):
            pass

    def cancel(self):
        self._cancelled.set()
        self.is_closed = True
        with self._lock:
            processes = tuple(self._processes)
        for proc in processes:
            self._signal(proc)  # no waiting or closing another thread's descriptors

    def close(self):
        self.cancel()

    @contextmanager
    def _session(self, timeout_seconds):
        timeout_seconds = effective_timeout(timeout_seconds)
        if self._cancelled.is_set():
            raise RuntimeError("OpenCode ACP request was cancelled")
        launch = {"start_new_session": True} if os.name == "posix" else {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)}
        try:
            proc = subprocess.Popen([self.command, *self.args], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace", bufsize=1,
                                    cwd=self.workspace, env=child_environment(), **launch)
        except OSError as exc:
            raise RuntimeError(f"Could not launch OpenCode ACP executable {self.command!r}") from exc
        with self._lock:
            self._processes.add(proc)
            self.is_closed = False
        inbox = queue.Queue()
        deadline = time.monotonic() + effective_timeout(timeout_seconds)
        sequence = 0

        def pump():
            try:
                while True:
                    line = proc.stdout.readline(MAX_FRAME + 1)
                    if not line:
                        inbox.put(RuntimeError("OpenCode ACP exited before replying"))
                        return
                    if len(line) > MAX_FRAME:
                        raise ValueError("OpenCode ACP response exceeded the frame limit")
                    message = json.loads(line)
                    if not isinstance(message, dict):
                        raise ValueError("OpenCode ACP emitted a non-object frame")
                    inbox.put(message)
            except Exception as exc:
                inbox.put(exc)

        def discard_stderr():
            while proc.stderr.read(4096):
                pass  # never persist vendor stderr, which may contain sensitive data

        readers = [threading.Thread(target=pump, daemon=True), threading.Thread(target=discard_stderr, daemon=True)]
        for reader in readers:
            reader.start()

        def send(message):
            if self._cancelled.is_set():
                raise RuntimeError("OpenCode ACP request was cancelled")
            wire = json.dumps(message, ensure_ascii=False)
            if len(wire.encode("utf-8")) > MAX_FRAME:
                raise ValueError("OpenCode ACP request exceeded the frame limit")
            proc.stdin.write(wire + "\n")
            proc.stdin.flush()

        def request(method, params, *, text_parts=None, reasoning_parts=None):
            nonlocal sequence
            sequence += 1
            rid = sequence
            send({"jsonrpc": "2.0", "id": rid, "method": method, "params": params})
            while time.monotonic() < deadline:
                if self._cancelled.is_set():
                    raise RuntimeError("OpenCode ACP request was cancelled")
                try:
                    message = inbox.get(timeout=min(0.1, max(0.001, deadline - time.monotonic())))
                except queue.Empty:
                    continue
                if isinstance(message, BaseException):
                    raise RuntimeError(str(message)) from message
                if isinstance(message.get("method"), str):
                    self._server_message(message, send, text_parts, reasoning_parts)
                    continue
                if message.get("id") != rid:
                    continue
                if "error" in message:
                    code = (message.get("error") or {}).get("code", "unknown")
                    raise RuntimeError(f"OpenCode ACP {method} failed (code {code}); vendor error text was not logged")
                return message.get("result") or {}
            raise TimeoutError(f"OpenCode ACP timed out during {method}")

        try:
            request("initialize", {"protocolVersion": 1,
                    "clientCapabilities": {"fs": {"readTextFile": False, "writeTextFile": False}, "terminal": False},
                    "clientInfo": {"name": "hermes-opencode-free-acp", "version": "0.3.0"}})
            session = request("session/new", {"cwd": self.workspace, "mcpServers": []})
            if not isinstance(session.get("sessionId"), str) or not session["sessionId"]:
                raise RuntimeError("OpenCode ACP did not return a session ID")
            yield session, request
        finally:
            self._signal(proc)
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self._signal(proc, force=True)
                proc.wait(timeout=2)
            for reader in readers:
                reader.join(timeout=1)
            for stream in (proc.stdin, proc.stdout, proc.stderr):
                stream.close()
            with self._lock:
                self._processes.discard(proc)
                if not self._processes:
                    self.is_closed = True

    @staticmethod
    def _server_message(message, send, text_parts, reasoning_parts):
        method = message["method"]
        if method == "session/update":
            update = (message.get("params") or {}).get("update") or {}
            kind = update.get("sessionUpdate")
            if kind in ("tool_call", "tool_call_update"):
                raise RuntimeError("OpenCode attempted a native tool; this bridge only permits Hermes-dispatched tools")
            sink = {"agent_message_chunk": text_parts, "agent_thought_chunk": reasoning_parts}.get(kind)
            content = update.get("content") or {}
            if sink is not None and isinstance(content, dict) and isinstance(content.get("text"), str):
                sink.append(content["text"])
            return
        if "id" not in message:
            return
        response = {"jsonrpc": "2.0", "id": message["id"]}
        if method == "session/request_permission":
            response["result"] = {"outcome": {"outcome": "cancelled"}}
        else:
            response["error"] = {"code": -32601, "message": "Native file, terminal and other ACP client operations are unavailable"}
        send(response)

    def list_models(self, *, timeout_seconds=15.0):
        with self._session(timeout_seconds) as (session, _):
            offered = set(options(config_option(session, "model")))
            return [model for model in FREE_MODELS if model in offered]

    def _run_prompt(self, prompt, *, model, timeout_seconds):
        if model not in FREE_MODELS:
            raise ValueError(f"OpenCode Free refuses an unapproved or paid model: {model!r}")
        with self._session(timeout_seconds) as (session, request):
            sid = session["sessionId"]
            # Validate both selections before sending any prompt. A failed model
            # selection must never continue on a possibly paid default model.
            mode = config_option(session, "mode", BRIDGE_MODE)
            chosen = config_option(session, "model", model)
            for option, value in ((mode, BRIDGE_MODE), (chosen, model)):
                result = request("session/set_config_option", {"sessionId": sid, "configId": option["id"], "value": value})
                if selected_value(result, option["id"]) != value:
                    raise RuntimeError(f"OpenCode did not confirm requested {option['id']}={value!r}; no prompt was sent")
            text, reasoning = [], []
            request("session/prompt", {"sessionId": sid, "prompt": [{"type": "text", "text": prompt}]},
                    text_parts=text, reasoning_parts=reasoning)
            answer = "".join(text)
            if not answer.strip():
                raise RuntimeError("OpenCode returned no assistant text; not treating this as success")
            return answer, "".join(reasoning)

    def _create_chat_completion(self, *, model=None, messages=None, tools=None, tool_choice=None,
                                timeout=None, stream=False, **kwargs):
        model = model or DEFAULT_MODEL
        prompt = render_prompt(messages, tools, tool_choice)
        text, reasoning = self._run_prompt(prompt, model=model, timeout_seconds=effective_timeout(timeout))
        calls, content = parse_tool_calls(text, tools, tool_choice)
        message = Record(role="assistant", content=content, tool_calls=calls,
                         reasoning=reasoning or None, reasoning_content=reasoning or None, reasoning_details=None)
        result = Record(id="acp_" + uuid.uuid4().hex, object="chat.completion", created=int(time.time()), model=model,
                        choices=[Record(index=0, message=message, finish_reason="tool_calls" if calls else "stop")], usage=None)
        if not stream:
            return result
        deltas = [Record(index=index, id=call.id, type="function", function=call.function) for index, call in enumerate(calls)]
        delta = Record(role="assistant", content=content or None, tool_calls=deltas or None,
                       reasoning_content=reasoning or None, reasoning=reasoning or None)
        return [Record(id=result.id, model=model, created=result.created, choices=[Record(index=0, delta=delta,
                       finish_reason=result.choices[0].finish_reason)], usage=None)]

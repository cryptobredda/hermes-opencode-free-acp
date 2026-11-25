"""Synthetic ACP server for offline tests. Never calls a model or reads user data."""
import io
import json
import subprocess
import sys
import time

for stream in (sys.stdin, sys.stdout):
    if isinstance(stream, io.TextIOWrapper):
        stream.reconfigure(encoding="utf-8")

SCENARIO = sys.argv[1] if len(sys.argv) > 1 else "normal"
MODEL = "opencode/glm-5.3-flash-free"
DYNAMIC_FREE = "opencode/new-model-free"
values = {"mode": "plan", "model": "openai/paid-test-only"}
prompts = 0
child = None
if SCENARIO == "descendant":
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"],
                             stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL)


def send(message):
    print(json.dumps(message), flush=True)


def config():
    model_options = [{"value": MODEL}, {"value": "openai/paid-test-only"}]
    if SCENARIO == "dynamic-model":
        model_options.insert(1, {"value": DYNAMIC_FREE})
    return [
        {"id": "mode", "category": "mode", "currentValue": values["mode"],
         "options": [{"value": "plan"}] + ([] if SCENARIO == "missing-build" else [{"value": "build"}])},
        {"id": "model", "category": "model", "currentValue": values["model"],
         "options": model_options},
    ]


for line in sys.stdin:
    request = json.loads(line)
    method, rid = request.get("method"), request.get("id")
    if method == "initialize":
        if SCENARIO == "invalid-json":
            print("not-json", flush=True)
            continue
        result = {"protocolVersion": 1, "agentCapabilities": {}}
    elif method == "session/new":
        result = {"sessionId": "fake-session", "configOptions": config()}
    elif method == "session/set_config_option":
        params = request["params"]
        if SCENARIO != "unconfirmed-model" or params["configId"] != "model":
            values[params["configId"]] = params["value"]
        result = {"configOptions": config()}
    elif method == "session/prompt":
        prompts += 1
        if SCENARIO == "slow":
            time.sleep(30)
        if SCENARIO == "exit":
            sys.exit(3)
        if SCENARIO == "rpc-error":
            send({"jsonrpc": "2.0", "id": rid, "error": {"code": -32000, "message": "TEST_SENSITIVE_TEXT_MUST_NOT_BE_LOGGED"}})
            continue
        if SCENARIO in ("native-tool", "native-tool-twice") and prompts == 1:
            send({"jsonrpc": "2.0", "method": "session/update", "params": {"update": {"sessionUpdate": "tool_call", "title": "native read"}}})
            text = ""
        elif SCENARIO == "native-tool":
            assert "native read" in request["params"]["prompt"][0]["text"], "correction must name the blocked tool"
            text = "FAKE_ACP_RECOVERED"
        elif SCENARIO == "native-tool-twice":
            send({"jsonrpc": "2.0", "method": "session/update", "params": {"update": {"sessionUpdate": "tool_call", "title": "native write"}}})
            text = ""
        elif SCENARIO == "denied-requests":
            for index, operation in enumerate(("session/request_permission", "fs/read_text_file", "fs/write_text_file", "terminal/create")):
                send({"jsonrpc": "2.0", "id": "server-" + str(index), "method": operation, "params": {}})
                reply = json.loads(sys.stdin.readline())
                if operation == "session/request_permission":
                    assert reply["result"]["outcome"]["outcome"] == "cancelled"
                else:
                    assert reply["error"]["code"] == -32601
            text = "FAKE_ACP_OK"
        else:
            text = "FAKE_ACP_OK"
        if SCENARIO == "descendant" and child is not None:
            text = "FAKE_CHILD_PID:" + str(child.pid)
        if SCENARIO == "unicode":
            text = "ACP café — 雪 👋"
            assert text in request["params"]["prompt"][0]["text"]
        if SCENARIO == "empty":
            text = ""
        if SCENARIO == "tool":
            text = '<hermes_tool_call>{"id":"fake-call","type":"function","function":{"name":"check_connection","arguments":"{\\"status\\":\\"ok\\"}"}}</hermes_tool_call>'
        if text:
            send({"jsonrpc": "2.0", "method": "session/update", "params": {"update": {"sessionUpdate": "agent_message_chunk", "content": {"type": "text", "text": text}}}})
        result = {"stopReason": "end_turn"}
    else:
        raise AssertionError("Unexpected synthetic request: " + str(method))
    send({"jsonrpc": "2.0", "id": rid, "result": result})

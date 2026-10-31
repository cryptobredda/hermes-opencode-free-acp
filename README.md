# OpenCode Free ACP for Hermes

Use the **real OpenCode CLI over ACP** as a Hermes model provider, while **Hermes keeps its own tool loop and approvals**.

This is an unofficial community integration, not an OpenCode or Nous Research product. It is not a generic autonomous-agent handoff, HTTP compatibility shim, shared inference service, or API-key proxy.

## What is different?

- The official installed `opencode acp` process makes model requests. The plugin does not imitate OpenCode HTTP headers or access its inference API directly.
- OpenCode runs its normal **Build** agent in the included restricted workspace. Its native tools are denied by workspace policy; ACP file/terminal requests are rejected and permissions are cancelled. A reported native tool call aborts the request.
- Hermes tool schemas and replayed tool results travel as text. Explicit `<hermes_tool_call>` envelopes are parsed into structural OpenAI-style calls, which **Hermes** validates and executes. The plugin never executes tool commands itself.
- Only a curated set of free-model IDs can be requested. Discovery intersects that set with the CLI's advertised catalog. Both agent and model selection must be confirmed before a prompt is sent; selection failure never continues on a possibly paid default.
- The transport is **Python standard library only**, with no private Hermes imports, monkey-patches, HTTP listeners, telemetry, Node/npm dependency of its own, or self-updater. OpenCode itself remains a separately installed runtime dependency.

The catalog-listed [oc-free-provider](https://github.com/anpicasso/hermes-oc-free-provider) takes a different, direct-HTTP approach. [opencode-hermes-acp](https://github.com/trojan-lord/opencode-hermes-acp) delegates actions to OpenCode's agent. This independent implementation instead combines actual CLI/ACP inference with Hermes-owned actions and a curated free-only selection policy.

## Requirements

- Hermes **0.22.2 or later**, with the documented external-process provider API.
- Python **3.11 or later** (normally the interpreter provided by Hermes).
- A separately installed, working **OpenCode v2 CLI** with `opencode acp` and ACP session config options. Live release testing used **OpenCode 2.1.2**, Hermes **v0.22.2+1376.g18c525b**, Python **3.14.7**, on Linux.
- `plugins.isolation: in_process` (the Hermes default). The provider returns a live client and does not support isolated plugin-host execution.

Version **0.4.0** adds platform handling for **Linux, macOS and native Windows**. The plugin uses the same Python implementation on each platform; install a compatible OpenCode CLI for your OS/CPU. Windows under WSL is a Linux installation: install both Hermes and OpenCode inside WSL rather than mixing Linux Hermes with a Windows executable.

Verification is documented separately from platform support: Linux has live model/tool verification; Windows Python and the real Windows CLI have also been exercised under Wine, not on a native Windows host. Native Windows/macOS CI is configured, but must pass for the new release before claiming those jobs succeeded. See [the verification report](docs/VERIFICATION.md).

## Install

Read the [security and privacy notes](#security-privacy-and-terms) first. Then install the public repository:

```sh
hermes plugins install cryptobredda/hermes-opencode-free-acp --enable
```

Select **OpenCode Free (ACP)** with `hermes model` or the Desktop model picker. To launch without changing the persistent default:

```sh
hermes chat --provider opencode-free-acp --model opencode/deepseek-v4.1-flash-free
```

`opencode/glm-5.3-flash-free` is also live-tested. Other offered models are discovered, not individually live-tested. Free availability, pricing, limits and privacy terms can change independently of this release; the name ending in `free` is not a perpetual pricing or access guarantee.

If the CLI is outside the gateway's PATH, the optional **non-secret** operator setting `HERMES_OPENCODE_ACP_COMMAND` names its executable. Only the `acp` argument is used by the provider; a model cannot choose the executable or its arguments.

### Platform setup

The installation and `hermes chat` commands above work in Linux/macOS terminals and Windows PowerShell; no Bash installer is required by this plugin. OpenCode must already be installed independently.

- **Linux:** PATH, `~/.opencode/bin`, `~/.bun/bin` and `~/.local/bin` are checked, followed by system bin directories.
- **macOS:** the same user paths plus Apple Silicon Homebrew (`/opt/homebrew/bin`) and Intel Homebrew (`/usr/local/bin`) are checked. This covers Desktop backends that do not inherit your interactive shell's PATH.
- **Windows:** PATH plus Bun, npm under `%APPDATA%`, Scoop shims and WinGet links are checked. Native `.exe` files and npm `.cmd`/`.bat` launchers are supported, including paths containing spaces or Unicode. PowerShell `.ps1` launchers are not executed and execution policy is never bypassed: use the native `.exe` or `.cmd` instead.

For a custom Windows install, set the executable path in the environment of the Hermes backend, for example:

```powershell
$env:HERMES_OPENCODE_ACP_COMMAND = 'C:\Users\you\AppData\Roaming\npm\opencode.cmd'
```

The setting is **one executable path**, not a shell command or a string containing arguments. A batch path containing `%` is refused rather than allowing environment expansion; point the override at the native `opencode.exe` instead (for npm v2, normally under `node_modules\@opencode\cli\bin`). Native executable paths do not have that batch-shell limitation. Restart an already-running backend after changing its environment.

Windows batch launch uses the OS command processor with AutoRun and delayed expansion disabled and fixed, quoted operator-owned arguments; model text never reaches that command line. Windows processes start suspended, join a private cleanup Job Object, and only then run, so a wrapper cannot spawn an untracked child before assignment. Cancellation/timeout closes that job; Linux/macOS use a separate process group. These are cleanup mechanisms, not OS sandboxes or permission grants. A Windows environment that disallows Job Objects fails closed rather than silently running without cleanup.

Installing does not intentionally change your default model, existing auxiliary/fallback routes, other profiles, or credentials. Existing paid Hermes auxiliary or fallback routes remain your responsibility. If upgrading a manually copied earlier bridge, back it up outside the autoload directories first to avoid two profiles registering the same provider name.

### Running Desktop / cached revisions

A new plugin directory is discovered dynamically. Editing an already-imported Python module does **not** reliably reload it inside a running backend. Restart the appropriate backend after an in-place update, without interrupting unrelated active work. Test an existing GUI session as well as a fresh CLI worker; the earlier local prototype's stale Build-agent check was only visible on the long-running Desktop path.

## Security, privacy and terms

**Not an OS sandbox.** OpenCode is a trusted executable running as your OS user. This plugin's workspace policy and protocol refusals constrain the integration; they are not a kernel isolation boundary. OpenCode still loads its own normal configuration/login and may load operator-configured plugins or hooks. Broader OpenCode policies can override workspace policies: do not use this bridge with a configuration that re-enables native tools, and do not point its executable override at an untrusted program.

**Disclosure:**

- Each discovery or inference call starts a short-lived local `opencode acp` subprocess in the plugin's included workspace. Processes are stopped after the call, on cancellation, or at the request deadline. There is no plugin daemon or background inference loop.
- Prompts, conversation history, tool schemas, tool arguments/results, and normal Hermes context are handed to OpenCode and leave the machine for OpenCode and the selected model provider. Their current terms and privacy/retention rules apply. Some free models use data for improvement or prohibit confidential data.
- OpenCode owns its own network calls, account/login handling, local configuration, caches and conversation records. The plugin never directly reads, copies, refreshes or writes vendor credential files, `.env`, Hermes `auth.json`, browser cookies or keychains. It neither acquires nor bundles a credential.
- The child receives an allowlist of OS/HOME/PATH/XDG, Windows profile, locale, certificate and proxy environment values, not arbitrary parent variables. The selected executable's directory is prepended to the child's PATH so installed launchers can find sibling runtimes. Hermes/provider API-key variables, inline OpenCode config, and inherited YOLO settings are excluded. Operator-configured proxy URLs are forwarded as network configuration and may themselves contain proxy credentials; they are not logged.
- The plugin itself performs no direct network requests, installs no tools, writes no runtime state files, sends no telemetry, auto-approves nothing and changes no Hermes core code. OpenCode's own ordinary data/config behavior still applies.
- This is not access authorization. Use only where OpenCode and the model provider permit your intended workload. Do not evade access restrictions, quotas, account requirements or rate limits, and do not use this as an inference service for third parties. If your intended use requires a supported client, login or paid access, comply with those requirements rather than treating this plugin as an exception.

See [OpenCode's model/privacy notices](https://opencode.ai/v2/docs/console/models/) and [terms](https://opencode.ai/legal/terms-of-service). Never send secrets or regulated/private data unless the applicable terms expressly permit it.

## Limits

- Text and Hermes function tools only; image/audio attachments fail explicitly instead of being silently dropped.
- ACP output is collected before it is returned. The OpenAI-shaped `stream=True` result is buffered, **not native token-by-token streaming**.
- Token usage/cost is **unknown** (`usage=None`). Zero counters shown by a frontend are not measured zero usage or billing evidence.
- Full transcripts are forwarded for each call; there is no persistent ACP session or guaranteed prompt-cache reuse. This adds process and prompt overhead.
- No reasoning-effort or temperature/output-limit controls are advertised. The CLI/model's own settings apply.
- Tool calls use a text protocol, not native model function calling. Malformed, incomplete, unadvertised or conflicting calls fail rather than being executed.

## Verify

The offline suite needs neither Hermes nor OpenCode, credentials, internet, nor live model access:

```sh
python -m unittest discover -s tests -v
```

It includes real stdio exchanges with an explicitly synthetic ACP server, not fabricated live-model results: exact model/Build selection, grouped options, tool/result replay, nested JSON, denied native operations, environment filtering, invalid frames, timeouts, process cleanup, and cancellation racing startup. Platform regressions cover GUI executable discovery, Windows quoting, Unicode/space-containing paths and protocol text. On Windows the suite also launches actual batch wrappers and verifies child-process cleanup without killing an unrelated process; those Windows-only tests are explicitly skipped elsewhere.

An optional, separate check negotiates ACP with the **real installed OpenCode CLI**, confirms Build/free-model selection, and stops before `session/prompt`. No conversation history or Hermes memory is loaded by this script:

```sh
python tests/smoke_cli.py
```

Unlike the offline suite, this requires OpenCode and may use its normal catalog network calls, configuration and local records. The CI workflow is configured to run both the offline Python 3.11/3.14 suite and a pinned official OpenCode 2.1.2 CLI check on Linux/macOS/Windows. Live model inference is not run in CI.

Check the actual provider with Hermes:

```sh
hermes plugins validate /path/to/hermes-opencode-free-acp --install-deps --json
hermes plugins doctor /path/to/hermes-opencode-free-acp --ci
```

For a live smoke test, create your own harmless scratch file and ask the model to read it. The example below uses POSIX shell line continuations; in PowerShell use one line and substitute your Windows file path:

```sh
hermes chat --source gui --provider opencode-free-acp \
  --model opencode/deepseek-v4.1-flash-free --ignore-rules --toolsets file \
  --max-turns 4 --format stream-json \
  -q 'Use the real Hermes read_file tool to read /absolute/path/to/test.txt and return its exact contents.'
```

Check for real `tool_use` and successful `tool_result` events and an exact matching final answer. `--ignore-rules` excludes private memory/project instructions from the synthetic check. Do not use `--safe-mode`, which disables user plugins; passing only an `--ignore-user-config` fresh-worker test does not establish that an existing Desktop backend loaded the current release.

Release verification notes are in [docs/VERIFICATION.md](docs/VERIFICATION.md). Hermes catalog platform availability is controlled separately by its reviewed, exact-SHA-pinned entry. Publishing this repository does not by itself update that entry: a cross-platform release also needs the catalog pin/version updated and `platforms: [linux, macos, windows]` admitted upstream.

## Contributing / license

Changes must keep Hermes's tool loop intact, avoid private core imports and credential-store access, and never add paid fallback, permission auto-approval, self-updating code or telemetry. Run the offline suite and Hermes validator before requesting review. Live inference is deliberately absent from CI.

MIT; see [LICENSE](LICENSE). Built on the public [Hermes model-provider interface](https://hermes-agent.nousresearch.com/docs/developer-guide/model-provider-plugin) and [Agent Client Protocol](https://agentclientprotocol.com/).

# Release verification — v0.3.0

Performed on 2026-10-25 on Linux with Hermes `v0.22.2+1376.g18c525b`, OpenCode `v2.1.2`, Python `3.14.7`, and OpenAI SDK `2.24.0` in Hermes (the plugin itself does not import the SDK).

## Offline suite

`python -m unittest discover -s tests -v`

Actual result: **47 tests passed**. These tests use an explicitly synthetic ACP stdio server; they neither perform inference nor require credentials, Hermes or OpenCode. CI is configured for Python 3.11/3.14 across Linux/macOS/Windows. Check the repository's Actions page for actual CI status; this local report does not claim those remote jobs passed before they ran.

## Hermes admission/runtime checks

Commands actually exercised:

- `hermes plugins validate /path/to/plugin --install-deps --json`
- `hermes plugins doctor /path/to/plugin --ci`

The validator returned `ok: true`, every check passed, `warnings: []`, a safe security scan, and no runtime core overrides. Runtime discovery/import/provider registration passed. Isolation classification was `in_process`, `host_ready: false`; this limitation is disclosed, not treated as isolated-host support.

## Live model transport

A direct instance of the release transport discovered the intersection of the curated IDs with OpenCode's real ACP model catalog. A live DeepSeek V4.1 Flash Free call returned the requested marker `PUBLIC_ACP_RELEASE_OK`. This was an actual OpenCode CLI request, not a mocked response.

## Live Hermes GUI-source tool loop, including resumed chats

A second isolated gateway was refused because the installed Hermes permits one gateway per host. The existing gateway was **not** stopped or restarted. Instead, a temporary, separately named model-provider alias loaded this release's transport on the existing gateway without replacing the user's working provider. Synthetic sessions used GUI source, `--ignore-rules`, and the file toolset; no real user memory or project instructions were sent for testing.

Both `opencode/deepseek-v4.1-flash-free` and `opencode/glm-5.3-flash-free`:

1. Emitted a real Hermes `read_file` request for a harmless scratch fixture.
2. Received a successful Hermes `tool_result` with that fixture's actual content.
3. Returned exactly `PUBLIC_PLUGIN_REAL_TOOL_PROOF_8C73A921`.
4. Were resumed on the same running gateway after the final transport revision was loaded under a fresh test-module namespace.
5. Issued a new real `read_file` call for a different fixture and returned exactly `PUBLIC_PLUGIN_FINAL_TOOL_PROOF_C49B28E1`.

The final proof was based on `tool_use`/`tool_result` events and exact file contents, not a model saying it had read a file. The tests exercise replayed tool history and an existing GUI session, not only a fresh command-line worker.

Only these two models and Linux live integration are claimed as verified. Other curated models are discoverable, not individually inference-tested. Token counters were displayed as zero by the frontend because usage is unknown; this is not evidence of zero tokens or a billing guarantee.

## Disclosure review

README.md documents the real CLI/network/data path, normal vendor configuration and local records, environment allowlisting, subprocess cleanup, no credential-store access by plugin code, tool/approval boundaries, non-sandbox status, limitations, terms, and distinction from the catalog's direct-HTTP OpenCode provider. No live inputs, vendor credentials, private account state or diagnostic logs are bundled in this repository.

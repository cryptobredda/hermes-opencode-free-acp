"""Non-secret release settings; no discovery, network, or filesystem writes."""
import os
from pathlib import Path
import shutil

VERSION = "0.3.0"
PROVIDER = "opencode-free-acp"
DEFAULT_MODEL = "opencode/glm-5.3-flash-free"
# Explicitly curated free IDs, never arbitrary strings ending in '-free'.
# ACP discovery intersects this list; inference checks live availability again.
FREE_MODELS = (
    DEFAULT_MODEL,
    "opencode/deepseek-v4.1-flash-free",
    "opencode/mimo-v2.6-flash-free",
    "opencode/nemotron-3.5-super-vl-free",
    "opencode/nemotron-3.5-lightning-free",
    "opencode/beam-free",
    "opencode/big-pickle",
)
WORKSPACE = Path(__file__).resolve().parent / "workspace"


def opencode_command():
    """Resolve an operator-owned executable, never a model-supplied command."""
    override = os.environ.get("HERMES_OPENCODE_ACP_COMMAND", "").strip()
    if override:
        return override
    found = shutil.which("opencode")
    if found:
        return found
    for candidate in (Path.home() / ".bun/bin/opencode", Path.home() / ".opencode/bin/opencode",
                      Path.home() / ".local/bin/opencode", Path("/opt/homebrew/bin/opencode")):
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    return "opencode"

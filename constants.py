"""Non-secret release settings; no discovery, network, or filesystem writes."""
from pathlib import Path

from .launcher import resolve_opencode

VERSION = "0.4.1"
PROVIDER = "opencode-free-acp"
DEFAULT_MODEL = "opencode/glm-5.3-flash-free"
# Curated free IDs. Dynamic discovery can include other OpenCode-advertised
# free models, but only inside the opencode namespace and only with an
# explicit free signal (-free suffix or known free ID like big-pickle).
CURATED_FREE_MODELS = (
    DEFAULT_MODEL,
    "opencode/deepseek-v4.1-flash-free",
    "opencode/mimo-v2.6-flash-free",
    "opencode/nemotron-3.5-super-vl-free",
    "opencode/nemotron-3.5-lightning-free",
    "opencode/beam-free",
    "opencode/big-pickle",
)
KNOWN_FREE_MODELS = frozenset(CURATED_FREE_MODELS)
FREE_MODELS = CURATED_FREE_MODELS  # compatibility export
WORKSPACE = Path(__file__).resolve().parent / "workspace"


def is_free_model(model):
    """Return True for curated or dynamically advertised OpenCode free models.

    Dynamic acceptance is intentionally narrow: opencode namespace only, and a
    clear free signal. This avoids treating arbitrary model IDs as free.
    """
    if not isinstance(model, str) or not model:
        return False
    if model in KNOWN_FREE_MODELS:
        return True
    if not model.startswith("opencode/"):
        return False
    name = model.split("/", 1)[1]
    return name == "big-pickle" or name.endswith("-free")


def opencode_command():
    """Resolve an operator-owned executable, never a model-supplied command."""
    return resolve_opencode()

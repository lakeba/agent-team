"""Model providers. Importing this package registers the built-in kinds."""
from .base import Provider, ProviderError, Reply, build, register  # noqa: F401
from . import http_providers  # noqa: F401  (registers ollama, openai, agent-http)

try:  # the Anthropic SDK is a dependency, but keep text-only setups importable without it
    from . import anthropic_provider  # noqa: F401
except ImportError:  # pragma: no cover
    pass

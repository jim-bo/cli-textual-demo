import os
from dotenv import load_dotenv
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.models.gemini import GeminiModel
from pydantic_ai.models.test import TestModel

load_dotenv()

KNOWN_PROVIDER_PREFIXES = {"anthropic", "openai", "gemini", "google"}


def get_model():
    """Dynamically select model based on environment variables."""
    model_name = os.getenv("PYDANTIC_AI_MODEL", "nvidia/nemotron-3-super-120b-a12b:free")

    if model_name.lower() == "test":
        return TestModel()

    # Only split "provider:name" on ":" if the left side is a known single-token provider.
    # This prevents "nvidia/model:free" style OpenRouter IDs from being mis-parsed.
    provider = None
    name = model_name
    if ":" in model_name:
        left, right = model_name.split(":", 1)
        if left.lower() in KNOWN_PROVIDER_PREFIXES:
            provider, name = left.lower(), right

    # Route through OpenRouter when key is available and no explicit native provider was parsed
    openrouter_key = os.getenv("OPENROUTER_API_KEY")
    if openrouter_key and provider is None:
        return OpenAIChatModel(
            model_name,
            provider=OpenAIProvider(
                base_url="https://openrouter.ai/api/v1",
                api_key=openrouter_key
            )
        )

    # Native providers
    if provider == "anthropic":
        return AnthropicModel(name)
    if provider == "gemini" or provider == "google":
        return GeminiModel(name)

    # openai: prefix or bare model name (e.g. "gpt-4o")
    return OpenAIChatModel(name if provider else model_name)


model = get_model()

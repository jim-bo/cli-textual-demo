import os
from dotenv import load_dotenv
from pydantic_ai import Agent, RunContext
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.models.gemini import GeminiModel
from pydantic_ai.models.test import TestModel

from cli_textual.core.agent_schemas import IntentResolution, ValidationResult, StructuredResult
from cli_textual.agents.prompt_loader import PROMPTS

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

# Initialize the shared model instance
model = get_model()

# ---------------------------------------------------------------------------
# Specialist 1: Intent Resolver
# ---------------------------------------------------------------------------
intent_resolver = Agent(
    model,
    output_type=IntentResolution,
    system_prompt=PROMPTS['specialists']['intent_resolver']['system_prompt']
)

@intent_resolver.tool
async def mock_resolve_intent(ctx: RunContext[None], query: str) -> str:
    """Mock search for intent identifiers."""
    return "Found matching target: demo_subject_001"

# ---------------------------------------------------------------------------
# Specialist 2: Data Validator
# ---------------------------------------------------------------------------
data_validator = Agent(
    model,
    output_type=ValidationResult,
    system_prompt=PROMPTS['specialists']['data_validator']['system_prompt']
)

@data_validator.tool
async def mock_check_data_availability(ctx: RunContext[None], target_id: str) -> str:
    """Mock validation of details for a given target identifier."""
    return f"Details confirmed for {target_id}: [detail_a, detail_b]"

# ---------------------------------------------------------------------------
# Specialist 3: Result Generator
# ---------------------------------------------------------------------------
result_generator = Agent(
    model,
    output_type=StructuredResult,
    system_prompt=PROMPTS['specialists']['result_generator']['system_prompt']
)

@result_generator.tool_plain
async def build_mock_structured_result(target_id: str, details: list[str]) -> str:
    """Deterministic result builder."""
    detail_str = ",".join(details)
    return f"https://example.com/results?id={target_id}&details={detail_str}"

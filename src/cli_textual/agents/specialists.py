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

def get_model():
    """Dynamically select model based on environment variables."""
    model_name = os.getenv("PYDANTIC_AI_MODEL", "test")
    
    if model_name.lower() == "test":
        return TestModel()

    # Detect Provider/Model Split
    provider = "openai"
    name = model_name
    if ":" in model_name:
        provider, name = model_name.split(":", 1)

    # 1. Handle OpenRouter
    openrouter_key = os.getenv("OPENROUTER_API_KEY")
    if openrouter_key and (provider == "openai" or "anthropic/" in name or "google/" in name):
        return OpenAIChatModel(
            name,
            provider=OpenAIProvider(
                base_url="https://openrouter.ai/api/v1",
                api_key=openrouter_key
            )
        )

    # 2. Handle Native Providers
    if provider == "openai":
        return OpenAIChatModel(name)
    elif provider == "anthropic":
        return AnthropicModel(name)
    elif provider == "gemini" or provider == "google":
        return GeminiModel(name)
            
    # Fallback
    return OpenAIChatModel(model_name)

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

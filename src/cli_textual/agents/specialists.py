import os
from dotenv import load_dotenv
from pydantic_ai import Agent, RunContext
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.models.gemini import GeminiModel
from pydantic_ai.models.test import TestModel

from cli_textual.core.agent_schemas import StudyResolution, ValidationResult, GeneratedLink

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

    # 1. Handle OpenRouter (Special case of OpenAI compatibility)
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
# Specialist 1: Study Resolver
# ---------------------------------------------------------------------------
study_resolver = Agent(
    model,
    output_type=StudyResolution,
    system_prompt=(
        "You resolve user queries to specific cBioPortal cancer studies. "
        "If the user is vague (e.g., 'breast cancer'), set confidence low (0.5) "
        "and provide a clarification question like 'I found several breast cancer studies, "
        "did you mean METABRIC or TCGA?'"
    )
)

@study_resolver.tool
async def search_studies(ctx: RunContext[None], query: str) -> str:
    """Mock search for studies in cBioPortal."""
    return "brca_tcga (TCGA Breast Cancer), brca_metabric (METABRIC Breast Cancer), lual_2014 (Lung Cancer)"

# ---------------------------------------------------------------------------
# Specialist 2: Parameter Validator
# ---------------------------------------------------------------------------
parameter_validator = Agent(
    model,
    output_type=ValidationResult,
    system_prompt=(
        "You validate whether a cancer study contains specific genomic or clinical data. "
        "If a key attribute like 'Overall Survival' is missing, set is_valid=False "
        "and ask if the user wants to proceed anyway."
    )
)

@parameter_validator.tool
async def get_study_attributes(ctx: RunContext[None], study_id: str) -> list[str]:
    """Mock fetching attributes for a study."""
    if "brca" in study_id:
        return ["MUTATIONS", "CNA", "OS_STATUS", "TMB"]
    return ["MUTATIONS"]

# ---------------------------------------------------------------------------
# Specialist 3: Link Generator
# ---------------------------------------------------------------------------
link_generator = Agent(
    model,
    output_type=GeneratedLink,
    system_prompt=(
        "Construct deep-links for cBioPortal based on the study_id and attributes. "
        "Ensure the explanation is helpful and concise."
    )
)

@link_generator.tool
async def build_url(ctx: RunContext[None], study_id: str, attributes: list[str]) -> str:
    """Deterministic URL builder for cBioPortal."""
    attrs = ",".join(attributes)
    return f"https://www.cbioportal.org/results/mutations?cancer_study_list={study_id}&attr_list={attrs}"

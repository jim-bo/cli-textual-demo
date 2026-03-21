import os
import asyncio
from typing import AsyncGenerator, List, Any
from pydantic_ai import Agent, RunContext
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.models.test import TestModel

from cli_textual.core.chat_events import (
    ChatEvent, AgentThinking, AgentToolStart, AgentToolEnd, AgentStreamChunk, AgentComplete
)
from cli_textual.agents.specialists import model, study_resolver, parameter_validator, link_generator
from cli_textual.core.agent_schemas import StudyResolution, ValidationResult, GeneratedLink

from openai import AsyncOpenAI

# Configure a slightly "smarter" model for the Manager agent if available
api_key = os.getenv("OPENROUTER_API_KEY")
manager_model = TestModel()

# ---------------------------------------------------------------------------
# Procedural Orchestration
# Explicit step-by-step logic in Python
# ---------------------------------------------------------------------------
async def run_procedural_pipeline(prompt: str) -> AsyncGenerator[ChatEvent, None]:
    """Execute the pipeline step-by-step using Python flow control."""
    
    # 1. Resolve Study
    yield AgentThinking(message="Resolving study semantic search...")
    await asyncio.sleep(0.5) # Minimum UI feedback delay
    
    # Step 1: Call Study Resolver
    yield AgentToolStart(tool_name="study_resolver", args={"query": prompt})
    res = await study_resolver.run(prompt)
    study: StudyResolution = res.output
    yield AgentToolEnd(tool_name="study_resolver", result=f"Resolved to {study.study_id}")
    
    # Check for clarification
    if study.clarification_needed:
        yield AgentStreamChunk(text=f"**Study Resolution Clarification Required:**\n\n{study.clarification_needed}")
        yield AgentComplete()
        return

    # 2. Validate Parameters
    yield AgentThinking(message=f"Validating attributes for {study.study_id}...")
    yield AgentToolStart(tool_name="parameter_validator", args={"study_id": study.study_id})
    val_res = await parameter_validator.run(f"Validating for {prompt} in {study.study_id}")
    validation: ValidationResult = val_res.output
    yield AgentToolEnd(tool_name="parameter_validator", result="Validation complete")

    # 3. Generate Link
    yield AgentThinking(message="Constructing final cBioPortal link...")
    yield AgentToolStart(tool_name="link_generator", args={"study_id": study.study_id, "attrs": validation.available_attributes})
    link_res = await link_generator.run(f"Generate link for {study.study_id} with {validation.available_attributes}")
    link: GeneratedLink = link_res.output
    
    yield AgentStreamChunk(text=f"### Result Found!\n\n{link.explanation}\n\n**Link:** [{link.url}]({link.url})")
    yield AgentComplete()

# ---------------------------------------------------------------------------
# Manager Orchestration
# A router agent that delegates to sub-agents as tools
# ---------------------------------------------------------------------------
manager_agent = Agent(
    model,
    system_prompt=(
        "You are a master cBioPortal orchestrator. To answer a user question, "
        "you MUST follow this flow: 1. Resolve the study, 2. Validate params, 3. Generate link. "
        "Do not answer directly; always use your specialized sub-agent tools. "
        "If a tool asks for clarification, relay that to the user."
    )
)

@manager_agent.tool
async def call_study_resolver(ctx: RunContext[None], query: str) -> str:
    """Resolve a user's natural language query to a specific cBioPortal study ID."""
    res = await study_resolver.run(query)
    data: StudyResolution = res.output
    if data.clarification_needed:
        return f"CLARIFICATION REQUIRED: {data.clarification_needed}"
    return f"RESOLVED: {data.study_id} ({data.study_name}) - Confidence: {data.confidence}"

@manager_agent.tool
async def call_parameter_validator(ctx: RunContext[None], study_id: str, question: str) -> str:
    """Validate if the study contains the attributes required by the user's question."""
    res = await parameter_validator.run(f"Check {study_id} for {question}")
    data: ValidationResult = res.output
    if data.clarification_needed:
        return f"CLARIFICATION REQUIRED: {data.clarification_needed}"
    status = "VALID" if data.is_valid else "PARTIAL"
    return f"STATUS: {status} - Attributes: {data.available_attributes}"

@manager_agent.tool
async def call_link_generator(ctx: RunContext[None], study_id: str, attributes: List[str], question: str) -> str:
    """Generate the final cBioPortal deep-link URL."""
    res = await link_generator.run(f"Generate link for {study_id} with {attributes} for {question}")
    data: GeneratedLink = res.output
    return f"RESULT: {data.explanation} - Link: {data.url}"

# ---------------------------------------------------------------------------
# Manager Pipeline Wrapper
# ---------------------------------------------------------------------------
async def run_manager_pipeline(prompt: str) -> AsyncGenerator[ChatEvent, None]:
    """Execute the manager orchestration and yield UI-compatible ChatEvents."""
    
    yield AgentThinking(message="Manager orchestrator initializing...")
    
    # We use run_stream to get tool call and chunk events
    async with manager_agent.run_stream(prompt) as result:
        last_length = 0
        async for message in result.stream_text():
            # stream_text() yields the full message so far, we only want the new part
            new_part = message[last_length:]
            if new_part:
                yield AgentStreamChunk(text=new_part)
                last_length = len(message)
            
    yield AgentComplete()

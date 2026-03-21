import os
import asyncio
from typing import AsyncGenerator, List, Any
from pydantic_ai import Agent, RunContext
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.models.test import TestModel
from pydantic_ai.messages import ModelMessage

from cli_textual.core.chat_events import (
    ChatEvent, AgentThinking, AgentToolStart, AgentToolEnd, AgentStreamChunk, AgentComplete,
    AgentRequiresUserInput, ChatDeps
)
from cli_textual.agents.specialists import model, intent_resolver, data_validator, result_generator
from cli_textual.core.agent_schemas import IntentResolution, ValidationResult, StructuredResult
from cli_textual.agents.prompt_loader import PROMPTS

from openai import AsyncOpenAI

# Configure a slightly "smarter" model for the Manager agent if available
api_key = os.getenv("OPENROUTER_API_KEY")
manager_model = TestModel()

# ---------------------------------------------------------------------------
# Procedural Orchestration
# Explicit step-by-step logic in Python
# ---------------------------------------------------------------------------
async def run_procedural_pipeline(prompt: str, message_history: List[Any] = None) -> AsyncGenerator[ChatEvent, None]:
    """Execute the pipeline step-by-step using Python flow control."""
    
    # 1. Resolve Intent
    yield AgentThinking(message="Resolving primary intent...")
    await asyncio.sleep(0.5) 
    
    # Step 1: Call Intent Resolver
    yield AgentToolStart(tool_name="intent_resolver", args={"query": prompt})
    res = await intent_resolver.run(prompt, message_history=message_history)
    intent: IntentResolution = res.output
    yield AgentToolEnd(tool_name="intent_resolver", result=f"Resolved to {intent.target_id}")
    
    # Check for clarification
    if intent.clarification_needed:
        yield AgentStreamChunk(text=f"**Clarification Required:**\n\n{intent.clarification_needed}")
        yield AgentComplete(new_history=res.new_messages())
        return

    # 2. Validate Details
    yield AgentThinking(message=f"Validating details for {intent.target_id}...")
    yield AgentToolStart(tool_name="data_validator", args={"target_id": intent.target_id})
    val_res = await data_validator.run(f"Validating for {prompt} in {intent.target_id}", message_history=res.all_messages())
    validation: ValidationResult = val_res.output
    yield AgentToolEnd(tool_name="data_validator", result="Validation complete")

    # 3. Generate Result
    yield AgentThinking(message="Constructing final structured result...")
    yield AgentToolStart(tool_name="result_generator", args={"target_id": intent.target_id, "details": validation.available_attributes})
    result_res = await result_generator.run(f"Generate result for {intent.target_id} with {validation.available_attributes}", message_history=val_res.all_messages())
    result: StructuredResult = result_res.output
    
    yield AgentStreamChunk(text=f"### Result Found!\n\n{result.explanation}\n\n**Output:** {result.output_data}")
    yield AgentComplete(new_history=result_res.new_messages())

# ---------------------------------------------------------------------------
# Manager Orchestration
# A router agent that delegates to sub-agents as tools
# ---------------------------------------------------------------------------
manager_agent = Agent(
    model,
    deps_type=ChatDeps,
    system_prompt=PROMPTS['orchestrators']['manager']['system_prompt']
)

@manager_agent.tool
async def ask_user_to_select_manager(ctx: RunContext[ChatDeps], prompt: str, options: List[str]) -> str:
    """Ask the user to select from a list of options. Use this when you need the user to make a choice."""
    await ctx.deps.event_queue.put(AgentRequiresUserInput(tool_name="/select", prompt=prompt, options=options))
    response = await ctx.deps.input_queue.get()
    return response

@manager_agent.tool
async def call_intent_resolver(ctx: RunContext[ChatDeps], query: str) -> str:
    """Resolve a user's natural language query to a specific target identifier."""
    res = await intent_resolver.run(query)
    data: IntentResolution = res.output
    if data.clarification_needed:
        return f"CLARIFICATION REQUIRED: {data.clarification_needed}"
    return f"RESOLVED: {data.target_id} ({data.target_name}) - Confidence: {data.confidence}"

@manager_agent.tool
async def call_data_validator(ctx: RunContext[ChatDeps], target_id: str, question: str) -> str:
    """Validate if the target contains the details required by the user's question."""
    res = await data_validator.run(f"Check {target_id} for {question}")
    data: ValidationResult = res.output
    if data.clarification_needed:
        return f"CLARIFICATION REQUIRED: {data.clarification_needed}"
    status = "VALID" if data.is_valid else "PARTIAL"
    return f"STATUS: {status} - Details: {data.available_attributes}"

@manager_agent.tool
async def call_result_generator(ctx: RunContext[ChatDeps], target_id: str, details: List[str], question: str) -> str:
    """Generate the final structured result."""
    res = await result_generator.run(f"Generate result for {target_id} with {details} for {question}")
    data: StructuredResult = res.output
    return f"RESULT: {data.explanation} - Data: {data.output_data}"

# ---------------------------------------------------------------------------
# Manager Pipeline Wrapper
# ---------------------------------------------------------------------------
async def run_manager_pipeline(
    prompt: str, 
    input_queue: asyncio.Queue, 
    message_history: List[Any] = None
) -> AsyncGenerator[ChatEvent, None]:
    """Execute the manager orchestration using queues for UI bridging."""
    event_queue = asyncio.Queue()
    deps = ChatDeps(event_queue=event_queue, input_queue=input_queue)
    
    await event_queue.put(AgentThinking(message="Manager orchestrator initializing..."))
    
    async def run_agent():
        try:
            async with manager_agent.run_stream(prompt, deps=deps, message_history=message_history) as result:
                last_length = 0
                async for text in result.stream_text():
                    new_part = text[last_length:]
                    if new_part:
                        await event_queue.put(AgentStreamChunk(text=new_part))
                        last_length = len(text)
                
                await event_queue.put(AgentComplete(new_history=result.new_messages()))
        except Exception as e:
            await event_queue.put(AgentComplete())
            raise e

    # Run the agent in the background
    task = asyncio.create_task(run_agent())
    
    # Yield events to the TUI as they come in
    while True:
        event = await event_queue.get()
        yield event
        if isinstance(event, AgentComplete):
            break

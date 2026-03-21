import os
import pytest
import asyncio
from pydantic_ai.models.test import TestModel

from cli_textual.agents.orchestrators import manager_agent, run_manager_pipeline
from cli_textual.core.chat_events import AgentRequiresUserInput, AgentStreamChunk, AgentComplete, AgentThinking

@pytest.mark.asyncio
async def test_manager_interactive_mock_backend():
    """Test the manager pipeline using a mock TestModel that forces a tool call."""
    input_queue = asyncio.Queue()
    
    # We force the TestModel to call the ask_user_to_select_manager tool before finishing
    mock_model = TestModel(call_tools=['ask_user_to_select_manager'])
    
    events = []
    with manager_agent.override(model=mock_model):
        pipeline = run_manager_pipeline("I'd like to write a funny sentence about my favorite color", input_queue)
        
        async for event in pipeline:
            events.append(event)
            if isinstance(event, AgentRequiresUserInput):
                assert event.tool_name == "/select"
                # Simulate the UI resolving the user input asynchronously
                await input_queue.put("Blue")
                
    # Verify the event sequence
    assert any(isinstance(e, AgentThinking) for e in events)
    assert any(isinstance(e, AgentRequiresUserInput) for e in events)
    assert any(isinstance(e, AgentStreamChunk) for e in events)
    assert isinstance(events[-1], AgentComplete)

@pytest.mark.asyncio
@pytest.mark.skipif(not os.getenv("OPENROUTER_API_KEY") and not os.getenv("OPENAI_API_KEY"), 
                    reason="No real API key configured for integration tests")
async def test_manager_integration_backend():
    """Test the manager pipeline using the real configured LLM."""
    input_queue = asyncio.Queue()
    
    from cli_textual.agents.specialists import get_model
    real_model = get_model() # Picks up PYDANTIC_AI_MODEL from env
    
    if isinstance(real_model, TestModel):
        pytest.skip("PYDANTIC_AI_MODEL resolved to TestModel. Skipping integration test.")
        
    events = []
    with manager_agent.override(model=real_model):
        # We prompt the real LLM to explicitly use the tool
        prompt = "Ask me what my favorite color is using your select tool, then write a funny sentence about it."
        pipeline = run_manager_pipeline(prompt, input_queue)
        
        async for event in pipeline:
            events.append(event)
            if isinstance(event, AgentRequiresUserInput):
                await input_queue.put("Neon Pink")
                
    # Verify the LLM called the tool
    assert any(isinstance(e, AgentRequiresUserInput) for e in events), "The LLM failed to call the interactive tool."
    
    # Combine the stream chunks to verify the LLM incorporated the answer
    text_chunks = [e.text for e in events if isinstance(e, AgentStreamChunk)]
    full_text = "".join(text_chunks)
    assert "Neon Pink" in full_text or "neon pink" in full_text.lower(), "The LLM did not use the supplied input."

@pytest.mark.asyncio
@pytest.mark.skipif(not os.getenv("OPENROUTER_API_KEY") and not os.getenv("OPENAI_API_KEY"), 
                    reason="No real API key configured for integration tests")
async def test_manager_multi_turn_memory():
    """Verify that the manager LLM remembers previous turns in a multi-turn conversation."""
    input_queue = asyncio.Queue()
    from cli_textual.agents.specialists import get_model
    real_model = get_model()
    
    if isinstance(real_model, TestModel):
        pytest.skip("PYDANTIC_AI_MODEL resolved to TestModel. Skipping integration test.")

    history = []
    
    # Turn 1: Tell the agent something
    with manager_agent.override(model=real_model):
        async for event in run_manager_pipeline("My secret password is 'BANANA'. Remember it.", input_queue, history):
            if isinstance(event, AgentComplete):
                history.extend(event.new_history)

    # Turn 2: Ask the agent to recall it
    events = []
    with manager_agent.override(model=real_model):
        async for event in run_manager_pipeline("What was my secret password?", input_queue, history):
            events.append(event)
            
    full_text = "".join([e.text for e in events if isinstance(e, AgentStreamChunk)])
    assert "BANANA" in full_text.upper(), f"The LLM forgot the secret. Output was: {full_text}"

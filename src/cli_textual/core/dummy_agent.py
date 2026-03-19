import asyncio
from typing import AsyncGenerator
from cli_textual.core.chat_events import (
    ChatEvent, AgentThinking, AgentToolStart, AgentToolEnd, AgentStreamChunk, AgentComplete
)

class DummyAgent:
    """A simulated AI agent that yields chat events with artificial latency."""

    async def ask(self, prompt: str) -> AsyncGenerator[ChatEvent, None]:
        """Process a prompt and yield a sequence of agent-loop events."""
        
        # 1. Thinking phase
        yield AgentThinking(message="Connecting to Gemini...")
        await asyncio.sleep(0.5)
        
        # 2. Tool decision
        yield AgentToolStart(tool_name="list_directory", args={"path": "."})
        await asyncio.sleep(0.8)
        yield AgentToolEnd(tool_name="list_directory", result="Found 3 files: app.py, README.md, tests/")
        
        # 3. Final response streaming
        chunks = [
            "I've scanned the ", "current workspace ", "and found a few ",
            "relevant files. ", "\n\n", "How can I ", "help you with ", "them?"
        ]
        
        for chunk in chunks:
            yield AgentStreamChunk(text=chunk)
            await asyncio.sleep(0.1) # Simulate streaming speed
            
        # 4. Completion
        yield AgentComplete()

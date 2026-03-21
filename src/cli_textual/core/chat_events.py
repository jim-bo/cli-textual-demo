from dataclasses import dataclass
from typing import Dict, Any, List
import asyncio

@dataclass
class ChatDeps:
    """Dependencies injected into Pydantic AI runs for interactive TUI tools."""
    event_queue: asyncio.Queue
    input_queue: asyncio.Queue

@dataclass
class ChatEvent:
    """Base class for all agent loop events."""
    pass

@dataclass
class AgentRequiresUserInput(ChatEvent):
    """The agent needs the TUI to gather input from the user."""
    tool_name: str
    prompt: str
    options: List[str]

@dataclass
class AgentThinking(ChatEvent):
    """The agent is processing or waiting for a response."""
    message: str = "Thinking..."

@dataclass
class AgentToolStart(ChatEvent):
    """The agent has decided to call a tool."""
    tool_name: str
    args: Dict[str, Any]

@dataclass
class AgentToolEnd(ChatEvent):
    """The agent has finished executing a tool."""
    tool_name: str
    result: str

@dataclass
class AgentStreamChunk(ChatEvent):
    """A partial chunk of the final text response."""
    text: str

@dataclass
class AgentComplete(ChatEvent):
    """The agent has finished the entire request loop."""
    new_history: List[Any] = None # List[ModelMessage]


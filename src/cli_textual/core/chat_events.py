from dataclasses import dataclass
from typing import Dict, Any

@dataclass
class ChatEvent:
    """Base class for all agent loop events."""
    pass

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
    pass

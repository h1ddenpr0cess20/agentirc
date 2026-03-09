"""chatbot -- AI-powered IRC chatbot using OpenAI-compatible Responses APIs."""

from .bot import ChatBot
from .config import ChatConfig

__all__ = [
    "ChatBot",
    "ChatConfig",
]

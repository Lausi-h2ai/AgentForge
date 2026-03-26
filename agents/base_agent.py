"""
Improved BaseAgent with conversation history and better error handling.
All variables initialized before use, proper method signatures.
"""
from typing import List, Dict, Optional

from .llama_compat import ChatMessage


class ConversationHistory:
    """Manages conversation history between agents"""
    
    def __init__(self, max_history: int = 10):
        self.max_history = max_history
        self.history: List[Dict[str, str]] = []
    
    def add_message(self, role: str, content: str):
        """Add a message to history"""
        self.history.append({"role": role, "content": content})
        
        # Trim to max_history, keeping system message if present
        if len(self.history) > self.max_history:
            # Keep first message if it's system, otherwise just trim from start
            if self.history[0].get("role") == "system":
                self.history = [self.history[0]] + self.history[-(self.max_history-1):]
            else:
                self.history = self.history[-self.max_history:]
    
    def get_messages(self) -> List[ChatMessage]:
        """Convert history to ChatMessage format"""
        return [
            ChatMessage(role=msg["role"], content=msg["content"]) 
            for msg in self.history
        ]
    
    def clear(self):
        """Clear conversation history"""
        self.history = []
    
    def get_summary(self, max_chars: int = 500) -> str:
        """Get a summary of the conversation"""
        if not self.history:
            return "No conversation history"
        
        summary = f"Conversation history ({len(self.history)} messages):\n"
        for msg in self.history[-3:]:  # Last 3 messages
            role = msg['role'].upper()
            content = msg['content'][:100] + "..." if len(msg['content']) > 100 else msg['content']
            summary += f"[{role}]: {content}\n"
        
        return summary


class BaseAgent:
    """
    Improved base agent with:
    - Conversation history tracking
    - Better error handling
    - Telemetry hooks
    - Proper initialization order
    
    IMPORTANT: All subclasses must call super().__init__() FIRST before
    accessing any instance variables.
    """
    
    def __init__(self, llm_class, llm_args, temperature, agent_name):
        """
        Initialize base agent. This MUST be called first in all subclasses.
        
        Args:
            llm_class: LLM class to instantiate
            llm_args: Arguments for LLM initialization
            temperature: Temperature setting for this agent
            agent_name: Name of the agent (e.g., "DeveloperAgent")
        """
        # Initialize ALL instance variables at the start
        self.agent_name = agent_name
        self.conversations: Dict[str, ConversationHistory] = {}
        self.call_count = 0
        self.total_tokens = 0
        self.error_count = 0
        
        # Now create LLM instance
        args = llm_args.copy()
        args['temperature'] = temperature
        self.llm = llm_class(**args)
        
        # Print confirmation
        model_display_name = llm_args.get("model_name") or llm_args.get("model")
        print(f"  -> {self.agent_name} initialized with {model_display_name} (temp={self.llm.temperature})")
    
    def _call_llm(self, system_message, prompt, logger):
        """
        Call LLM with error tracking.
        
        Args:
            system_message: System prompt
            prompt: User prompt
            logger: Optional logger instance (can be None)
        
        Returns:
            LLM response string
        """
        from .utils import call_llm
        
        self.call_count += 1
        try:
            return call_llm(self.llm, system_message, prompt, logger, self.agent_name)
        except Exception as e:
            self.error_count += 1
            if logger:
                logger.log("ERROR", f"{self.agent_name} LLM call failed: {e}")
            raise
    
    def _get_or_create_conversation(self, other_agent_name: str) -> ConversationHistory:
        """Get or create conversation history with another agent"""
        if other_agent_name not in self.conversations:
            self.conversations[other_agent_name] = ConversationHistory()
        return self.conversations[other_agent_name]
    
    async def chat(self, message: str) -> str:
        """
        BACKWARDS COMPATIBLE chat method.
        
        This is the default implementation that maintains backward compatibility
        with existing code. Subclasses can override this.
        
        Args:
            message: The message to send
        
        Returns:
            Response string
        """
        # Default system message for a generic chat
        system_message = f"You are {self.agent_name}. Answer the user's question directly."
        
        # Use the synchronous _call_llm here (no logger in base implementation)
        return self._call_llm(system_message, message, None)
    
    def clear_conversation(self, other_agent_name: Optional[str] = None):
        """Clear conversation history with a specific agent or all agents"""
        if other_agent_name:
            if other_agent_name in self.conversations:
                self.conversations[other_agent_name].clear()
        else:
            for conv in self.conversations.values():
                conv.clear()
    
    def get_stats(self) -> Dict:
        """Get agent statistics"""
        return {
            "agent_name": self.agent_name,
            "call_count": self.call_count,
            "error_count": self.error_count,
            "error_rate": self.error_count / max(self.call_count, 1),
            "active_conversations": len(self.conversations)
        }
    
    def __enter__(self):
        """Context manager entry"""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - cleanup resources"""
        # Clear all conversations on exit
        self.conversations.clear()
        return False  # Don't suppress exceptions

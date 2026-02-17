"""
Improved utilities with better JSON parsing, retry logic, and error handling.
All functions maintain backward compatibility with original signatures.
"""
import json
import re
import time
import os
from typing import Optional, Dict, Tuple
from enum import Enum

# LlamaIndex imports
from llama_index.llms.google_genai import GoogleGenAI
from llama_index.embeddings.google_genai import GoogleGenAIEmbedding
from llama_index.core import Settings
from llama_index.core.llms import ChatMessage
from llama_index.llms.ollama import Ollama
from llama_index.core.callbacks import CallbackManager, TokenCountingHandler
from llama_index.embeddings.ollama import OllamaEmbedding

# Google API imports
try:
    from google.genai.errors import ClientError
except ImportError:
    ClientError = None

class ErrorCategory(Enum):
    """Classification of errors for intelligent retry"""
    RETRYABLE = "retryable"
    FATAL = "fatal"
    REQUIRES_HUMAN = "requires_human"
    PARSING_ERROR = "parsing_error"
    UNKNOWN = "unknown"


def get_phase_model_overrides(provider: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Get optional planning/execution model overrides from environment variables.

    Supported env vars:
      - OLLAMA_PLANNING_MODEL / OLLAMA_EXECUTION_MODEL / OLLAMA_MODEL
      - GOOGLE_PLANNING_MODEL / GOOGLE_EXECUTION_MODEL / GOOGLE_MODEL
    """
    provider_key = (provider or "").lower()
    if provider_key == "google":
        planning = os.getenv("GOOGLE_PLANNING_MODEL")
        execution = os.getenv("GOOGLE_EXECUTION_MODEL")
        fallback = os.getenv("GOOGLE_MODEL")
    else:
        planning = os.getenv("OLLAMA_PLANNING_MODEL")
        execution = os.getenv("OLLAMA_EXECUTION_MODEL")
        fallback = os.getenv("OLLAMA_MODEL")

    if planning is None and fallback is not None:
        planning = fallback
    if execution is None and planning is not None:
        execution = planning

    return planning, execution


def parse_json_from_response(response_str: str) -> Optional[Dict]:
    """
    Enhanced JSON parsing with multiple strategies and repair attempts.
    MAINTAINS ORIGINAL SIGNATURE for backward compatibility.
    
    Strategies:
    1. Direct parse
    2. Extract from markdown code blocks
    3. Find balanced braces
    4. Repair common issues
    
    Args:
        response_str: Raw LLM response
    
    Returns:
        Parsed JSON dict or None
    """
    if not response_str or not isinstance(response_str, str):
        print("❌ Error: Invalid response_str type")
        return None
    
    # Strategy 1: Direct parse
    try:
        return json.loads(response_str)
    except json.JSONDecodeError:
        pass
    
    # Strategy 2: Extract from markdown code blocks
    json_match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', response_str, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group(1))
        except json.JSONDecodeError:
            pass
    
    # Strategy 3: Find balanced braces/brackets
    for opener, closer in [('{', '}'), ('[', ']')]:
        idx_start = response_str.find(opener)
        if idx_start == -1:
            continue
        
        balance = 1
        idx_end = -1
        in_string = False
        escape_next = False
        
        for i in range(idx_start + 1, len(response_str)):
            char = response_str[i]
            
            if escape_next:
                escape_next = False
                continue
            
            if char == '\\':
                escape_next = True
                continue
            
            if char == '"':
                in_string = not in_string
                continue
            
            if in_string:
                continue
            
            if char == opener:
                balance += 1
            elif char == closer:
                balance -= 1
            
            if balance == 0:
                idx_end = i + 1
                break
        
        if idx_end != -1:
            json_str = response_str[idx_start:idx_end]
            
            # Strategy 4: Try with repairs
            for attempt in range(3):
                try:
                    return json.loads(json_str)
                except json.JSONDecodeError as e:
                    if attempt < 2:
                        json_str = _repair_json(json_str, str(e))
                    else:
                        print(f"❌ JSON parsing failed after 3 repair attempts")
                        print(f"Error: {e}")
                        if len(json_str) < 500:
                            print(f"Problematic JSON:\n{json_str}")
    
    return None


def _repair_json(json_str: str, error_msg: str) -> str:
    """Attempt to repair common JSON issues"""
    # Remove // comments (but preserve URLs)
    json_str = re.sub(r'(?<!:)//[^\n]*', '', json_str)
    
    # Remove trailing commas
    json_str = re.sub(r',(\s*[}\]])', r'\1', json_str)
    
    # Remove control characters
    json_str = re.sub(r'[\x00-\x1f\x7f]', '', json_str)
    
    return json_str


def configure_llm_and_embed(provider="ollama", model=None):
    """
    ORIGINAL FUNCTION SIGNATURE MAINTAINED.
    Configures and returns LLM and embedding models based on the provider.
    
    Args:
        provider: "ollama" or "google"
        model: Optional model override
    
    Returns:
        Tuple of (llm_class, llm_args, token_counter)
    """
    print(f"Configuring models for provider: {provider.upper()}")

    if provider == "google":
        if not os.getenv("GOOGLE_API_KEY"):
            raise ValueError("Environment variable GOOGLE_API_KEY is required to use Google GenAI.")
        llm_class = GoogleGenAI
        embed_model = GoogleGenAIEmbedding(model_name="gemini-embedding-1.0")
        llm_args = {"model_name": model or "models/gemma-3-12b"}

    elif provider == "ollama":
        llm_class = Ollama
        embed_model = OllamaEmbedding(model_name="nomic-embed-text:latest")
        llm_args = {
            "model": model or "qwen3-coder-next:cloud",
            "request_timeout": 3000.0,
            #"context_window": 32768,
        }
    else:
        raise ValueError(f"Unsupported LLM provider: {provider}")
    
    # Apply configuration globally
    Settings.embed_model = embed_model

    token_counter = TokenCountingHandler()
    Settings.callback_manager = CallbackManager([token_counter])
    
    return llm_class, llm_args, token_counter


def call_llm(llm_instance, system_message: str, user_prompt: str, logger, agent_name: str = "Unknown Agent") -> str:
    """
    ORIGINAL FUNCTION SIGNATURE MAINTAINED.
    Enhanced LLM call with intelligent retry logic and error handling.
    
    Args:
        llm_instance: LLM instance to call
        system_message: System prompt
        user_prompt: User prompt
        logger: Logger instance (can be None)
        agent_name: Name of calling agent
    
    Returns:
        LLM response string
    
    Raises:
        Exception: After max retries or on fatal errors
    """
    # Validate inputs
    if not system_message or not isinstance(system_message, str):
        system_message = "You are a helpful assistant."
    
    if not user_prompt or not isinstance(user_prompt, str):
        raise ValueError("user_prompt must be a non-empty string")
    
    # Log if logger available
    if logger:
        try:
            logger.log_event_in_step("llm_call", {
                "agent_name": agent_name, 
                "prompt": user_prompt[:200] + "..." if len(user_prompt) > 200 else user_prompt
            })
        except Exception as e:
            print(f"⚠️ Logger error (non-fatal): {e}")
    
    max_retries = 5
    last_error = None
    
    for attempt in range(max_retries):
        try:
            messages = [
                ChatMessage(role="system", content=system_message),
                ChatMessage(role="user", content=user_prompt),
            ]
            
            response = llm_instance.chat(messages)
            response_content = response.message.content
            
            # Log response if logger available
            if logger:
                try:
                    logger.log_event_in_step("llm_response", {
                        "response": response_content[:500] + "..." if len(response_content) > 500 else response_content
                    })
                except Exception as e:
                    print(f"⚠️ Logger error (non-fatal): {e}")
            
            return response_content
            
        except Exception as e:
            last_error = e
            
            # Classify error
            error_str = str(e).lower()
            
            # Check for rate limiting
            if "resource_exhausted" in error_str or "429" in error_str:
                # Try to extract delay
                retry_delay = _extract_retry_delay_from_error(e)
                if retry_delay <= 0:
                    retry_delay = 5 * (2 ** attempt)
                
                print(f"⚠️ Rate limited. Waiting {retry_delay}s before retry {attempt + 1}/{max_retries}...")
                time.sleep(retry_delay + 1)
                continue
            
            # Check for fatal errors
            if "unauthorized" in error_str or "401" in error_str or "api key" in error_str:
                print(f"❌ Fatal error - invalid API key: {e}")
                raise e
            
            # Check for daily quota
            if "quota" in error_str and "daily" in error_str:
                print(f"❌ Daily quota exceeded - requires human intervention")
                raise e
            
            # Network/timeout errors - retry
            if "timeout" in error_str or "connection" in error_str:
                if attempt < max_retries - 1:
                    retry_delay = 5 * (2 ** attempt)
                    print(f"⚠️ Network error. Retrying in {retry_delay}s...")
                    time.sleep(retry_delay)
                    continue
            
            # Generic retry for unknown errors
            if attempt < max_retries - 1:
                retry_delay = 5 * (2 ** attempt)
                print(f"⚠️ Error: {type(e).__name__}. Retrying in {retry_delay}s...")
                time.sleep(retry_delay)
                continue
            else:
                print(f"❌ Failed after {max_retries} attempts")
                raise e
    
    # If we get here, we've exhausted retries
    print(f"❌ {agent_name} failed after {max_retries} attempts")
    if logger:
        try:
            logger.log("ERROR", f"{agent_name}: Failed after {max_retries} attempts: {last_error}")
        except:
            pass
    
    raise Exception(f"Failed to call LLM after {max_retries} attempts. Last error: {last_error}")


def _extract_retry_delay_from_error(exception: Exception) -> int:
    """
    Extract retry delay from exception if available.
    
    Args:
        exception: Exception to extract from
    
    Returns:
        Delay in seconds, or 0 if not found
    """
    try:
        if hasattr(exception, 'details'):
            error_details = exception.details.get('error', {}).get('details', [])
            for detail in error_details:
                if detail.get('@type') == 'type.googleapis.com/google.rpc.RetryInfo':
                    delay_str = detail.get('retryDelay', '0s')
                    match = re.search(r'(\d+)', delay_str)
                    if match:
                        return int(match.group(1))
    except:
        pass
    
    return 0

"""
RequirementsAnalystAgent - Analyzes and clarifies requirements.
Maintains backward compatibility with original implementation.
"""
from .base_agent import BaseAgent
from .utils import parse_json_from_response
from .prompt_router import detect_requirements_profile
from prompt_loader import load_versioned_prompt


DEFAULT_REQUIREMENTS_ANALYST_PROMPT = """You are RequirementsAnalystAgent.
Your job is to convert vague user requests into implementation-ready requirements.

Reliability rules:
- Output must be valid JSON only.
- Return exactly two keys: "questions" and "refined_prompt".
- "questions" must be a list of strings.
- "refined_prompt" must be a single string.
- If nothing is unclear, return an empty questions list.

Quality rules:
- Identify missing constraints, edge cases, and non-functional needs.
- Propose sensible MVP defaults when ambiguity exists.
- State explicit scope boundaries and out-of-scope items.
- Keep the refined prompt concrete enough for architecture + planning.

Required output schema:
{
  "questions": ["..."],
  "refined_prompt": "..."
}
"""


class RequirementsAnalystAgent(BaseAgent):
    """
    Requirements Analyst agent for clarifying project requirements.

    Args:
        llm_class: LLM class to use
        llm_args: LLM configuration arguments
    """

    def __init__(self, llm_class, llm_args):
        super().__init__(llm_class, llm_args, temperature=0.2, agent_name="RequirementsAnalystAgent")

    def analyze_requirements(self, user_prompt, conversation_history=""):
        """
        Analyze user prompt and identify ambiguities.

        Args:
            user_prompt: Initial user request
            conversation_history: Previous conversation (optional)

        Returns:
            Dict with "questions" and "refined_prompt" keys
        """
        base_prompt = load_versioned_prompt(
            "requirements_analyst",
            "base",
            DEFAULT_REQUIREMENTS_ANALYST_PROMPT,
        )
        profile = detect_requirements_profile(user_prompt)
        profile_overlay = load_versioned_prompt(
            "requirements_analyst",
            f"profiles/{profile}",
            "",
        )
        system_message = base_prompt + (f"\n\n{profile_overlay}" if profile_overlay else "")

        prompt = "Analyze this user request.\n\n"
        if conversation_history:
            prompt += f"CONVERSATION HISTORY:\n{conversation_history}\n\n"

        prompt += f"CURRENT USER PROMPT:\n{user_prompt}"

        response_str = self._call_llm(system_message, prompt, logger=None)

        # Parse JSON response
        data = parse_json_from_response(response_str)

        if data and "questions" in data and "refined_prompt" in data:
            return data

        print(f"[WARNING] RequirementsAnalystAgent response missing keys. Parsed={data}")
        # Return pass-through to avoid crashing
        return {
            "questions": [],
            "refined_prompt": user_prompt
        }

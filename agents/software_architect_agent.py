"""
SoftwareArchitectAgent - Designs technical architecture.
Improved JSON parsing and validation.
"""
from .base_agent import BaseAgent
from .utils import parse_json_from_response
from .prompt_router import detect_architecture_profile
from aidev_orchestrator.prompt_loader import load_versioned_prompt
import json
import re


DEFAULT_SOFTWARE_ARCHITECT_PROMPT = """You are SoftwareArchitectAgent.
Design a practical technical blueprint that developers can implement directly.

Reliability rules:
- Return valid JSON only.
- No markdown, comments, or extra prose.
- Keep string values single-line where possible.

Required output format:
{
  "technology_stack": "...",
  "file_structure": ["..."],
  "dependencies": {"pip": ["..."], "npm": ["..."]},
  "component_breakdown": {"path": "purpose"},
  "run_command": "..." or {"backend":"...","frontend":"..."}
}

Quality rules:
- Ensure architecture aligns with clarified requirements and local-runtime constraints.
- Keep file structure explicit and implementation-ready.
- Include realistic dependency lists and runnable command(s).
"""


class SoftwareArchitectAgent(BaseAgent):
    """
    Software Architect agent for designing technical blueprints.

    Args:
        llm_class: LLM class to use
        llm_args: LLM configuration arguments
    """

    def __init__(self, llm_class, llm_args):
        super().__init__(llm_class, llm_args, temperature=0.3, agent_name="SoftwareArchitectAgent")

    def design_architecture(self, clarified_prompt, logger):
        """
        Design technical architecture for a project.

        Args:
            clarified_prompt: Clarified requirements from RequirementsAnalyst
            logger: Logger instance

        Returns:
            Dict with architecture details or None on failure
        """
        base_prompt = load_versioned_prompt(
            "software_architect",
            "base",
            DEFAULT_SOFTWARE_ARCHITECT_PROMPT,
        )
        profile = detect_architecture_profile(clarified_prompt)
        profile_overlay = load_versioned_prompt(
            "software_architect",
            f"profiles/{profile}",
            "",
        )
        system_message = base_prompt + (f"\n\n{profile_overlay}" if profile_overlay else "")

        prompt = f"""Design the technical architecture for this project.

Project Requirements:
{clarified_prompt}

Remember: Output ONLY valid JSON with required keys.
"""

        max_retries = 5
        for attempt in range(max_retries):
            response_str = self._call_llm(system_message, prompt, logger)

            # Enhanced JSON extraction
            data = self._extract_and_parse_json(response_str, attempt)

            if data:
                # Validate required keys
                required_keys = [
                    "technology_stack",
                    "file_structure",
                    "dependencies",
                    "component_breakdown",
                    "run_command"
                ]

                if all(key in data for key in required_keys):
                    # Additional validation
                    if self._validate_architecture(data):
                        return data
                    print(f"[WARNING] Architecture validation failed (attempt {attempt + 1})")
                else:
                    missing = [key for key in required_keys if key not in data]
                    print(f"[WARNING] Missing keys: {missing} (attempt {attempt + 1})")
            else:
                print(f"[WARNING] Failed to parse JSON (attempt {attempt + 1})")

            if attempt < max_retries - 1:
                prompt = f"""{prompt}

PREVIOUS ATTEMPT FAILED. Fix formatting and include all required keys exactly.
"""

        print("[ERROR] SoftwareArchitectAgent failed after all retries.")
        return None

    def _extract_and_parse_json(self, response_str, attempt_num):
        """Enhanced JSON extraction with multiple fallback strategies"""

        # Strategy 1: Direct JSON parse
        try:
            return json.loads(response_str)
        except json.JSONDecodeError:
            pass

        # Strategy 2: Extract from markdown code block
        json_match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', response_str, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass

        # Strategy 3: Find JSON object boundaries
        start = response_str.find('{')
        end = response_str.rfind('}')

        if start != -1 and end != -1 and end > start:
            json_candidate = response_str[start:end+1]

            # Strategy 4: Clean common issues
            json_candidate = self._clean_json_string(json_candidate)

            try:
                return json.loads(json_candidate)
            except json.JSONDecodeError as e:
                print(f"[ERROR] JSON decode error: {e}")
                if len(json_candidate) < 500:
                    print(f"--- Extracted JSON ---\n{json_candidate}\n---")

        # Strategy 5: Try parse_json_from_response utility
        try:
            return parse_json_from_response(response_str)
        except Exception:
            pass

        return None

    def _clean_json_string(self, json_str):
        """Clean common JSON formatting issues"""
        # Remove // comments (preserve URLs)
        json_str = re.sub(r'(?<!:)//[^\n]*', '', json_str)

        # Remove trailing commas
        json_str = re.sub(r',(\s*[}\]])', r'\1', json_str)

        return json_str

    def _validate_architecture(self, data):
        """Validate architecture data structure"""

        if not isinstance(data.get("technology_stack"), str):
            return False
        if not isinstance(data.get("file_structure"), list):
            return False
        if not isinstance(data.get("dependencies"), dict):
            return False
        if not isinstance(data.get("component_breakdown"), dict):
            return False
        if not isinstance(data.get("run_command"), (str, dict)):
            return False
        if len(data["file_structure"]) == 0:
            return False
        return True


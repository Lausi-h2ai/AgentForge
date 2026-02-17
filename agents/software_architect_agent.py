"""
SoftwareArchitectAgent - Designs technical architecture.
Improved JSON parsing and validation.
"""
from .base_agent import BaseAgent
from .utils import parse_json_from_response
import json
import re


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
        system_message = """You are an expert Software Architect. Design the high-level technical BLUEPRINT.

**CRITICAL JSON RULES:**
1. Output ONLY valid JSON - no markdown, no comments, no explanations
2. String values must be single-line (use \\n for newlines)
3. NO // comments in JSON
4. NO unescaped quotes or control characters
5. NO markdown formatting inside JSON strings

**OUTPUT FORMAT (STRICT JSON):**
{
  "technology_stack": "Single-line string describing the stack",
  "file_structure": ["array", "of", "file", "paths"],
  "dependencies": {
    "pip": ["Flask==3.0.0"],
    "npm": ["react@18.2.0"]
  },
  "component_breakdown": {
    "filename.py": "Purpose description"
  },
  "run_command": "python app.py" or {"backend": "cmd1", "frontend": "cmd2"}
}

**Example - Python Web App:**
{
  "technology_stack": "Python backend with Flask and SQLAlchemy, HTML/CSS frontend",
  "file_structure": [
    "app.py",
    "models.py",
    "requirements.txt",
    "templates/index.html"
  ],
  "dependencies": {
    "pip": [
      "Flask==3.0.0",
      "Flask-SQLAlchemy==3.1.1"
    ]
  },
  "component_breakdown": {
    "app.py": "Main Flask application with routes and initialization",
    "models.py": "SQLAlchemy database models"
  },
  "run_command": "python app.py"
}

IMPORTANT: Return ONLY the JSON object. No text before { or after }.
"""
        
        prompt = f"""Design the technical architecture for this project.

Project Requirements:
{clarified_prompt}

Remember: Output ONLY valid JSON. No markdown, no comments, single-line strings only.
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
                    else:
                        print(f"⚠️ Architecture validation failed (attempt {attempt + 1})")
                else:
                    missing = [key for key in required_keys if key not in data]
                    print(f"⚠️ Missing keys: {missing} (attempt {attempt + 1})")
            else:
                print(f"⚠️ Failed to parse JSON (attempt {attempt + 1})")
            
            if attempt < max_retries - 1:
                prompt = f"""{prompt}

PREVIOUS ATTEMPT FAILED. Issues detected:
- Ensure all string values are on a single line (use \\n for line breaks)
- Remove ALL // comments from the JSON
- Remove ALL markdown formatting from string values
- Ensure JSON is properly closed with all braces matched

Try again with STRICT JSON formatting."""
        
        print("❌ Error: SoftwareArchitectAgent failed after all retries.")
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
                print(f"❌ JSON Decode Error: {e}")
                if len(json_candidate) < 500:
                    print(f"--- Extracted JSON ---\n{json_candidate}\n---")
        
        # Strategy 5: Try parse_json_from_response utility
        try:
            return parse_json_from_response(response_str)
        except:
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
        
        # Check technology_stack is string
        if not isinstance(data.get("technology_stack"), str):
            print("⚠️ technology_stack must be a string")
            return False
        
        # Check file_structure is list
        if not isinstance(data.get("file_structure"), list):
            print("⚠️ file_structure must be a list")
            return False
        
        # Check dependencies is dict
        if not isinstance(data.get("dependencies"), dict):
            print("⚠️ dependencies must be a dictionary")
            return False
        
        # Check component_breakdown is dict
        if not isinstance(data.get("component_breakdown"), dict):
            print("⚠️ component_breakdown must be a dictionary")
            return False
        
        # run_command can be string or dict
        run_cmd = data.get("run_command")
        if not isinstance(run_cmd, (str, dict)):
            print("⚠️ run_command must be string or dictionary")
            return False
        
        # Check file_structure not empty
        if len(data["file_structure"]) == 0:
            print("⚠️ file_structure cannot be empty")
            return False
        
        return True

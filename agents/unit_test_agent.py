"""
UnitTestAgent - Generates unit tests for code files.
Maintains backward compatibility.
"""
from .base_agent import BaseAgent


class UnitTestAgent(BaseAgent):
    """
    Unit Test agent for generating pytest tests.
    
    Args:
        llm_class: LLM class to use
        llm_args: LLM configuration arguments
    """
    
    def __init__(self, llm_class, llm_args):
        super().__init__(llm_class, llm_args, temperature=0.1, agent_name="UnitTestAgent")
    
    def write_tests(self, filename, file_content, logger):
        """
        Generate unit tests for a given file.
        
        Args:
            filename: Name of the file to test
            file_content: Content of the file
            logger: Logger instance
        
        Returns:
            Test code as string
        """
        system_message = f"""You are an expert Software Development Engineer in Test (SDET).
Write clear, effective, comprehensive unit tests using the `pytest` framework for Python.

You will be given the content of a Python file (`{filename}`).
Your task is to write a corresponding test file named `test_{filename}`.

**Your testing philosophy:**
- Focus on testing public-facing functions/classes
- Test expected success cases
- Test edge cases (e.g., empty inputs, invalid data)
- Test expected failure cases (functions that should raise errors)
- Use `pytest.fixture` for necessary setup
- If code interacts with database, mock the database session or use in-memory database
- For Flask-SQLAlchemy apps, set up test client and application context

Generate only the Python code for the test file. No other text, explanations, or Markdown.
"""
        
        prompt = f"""
Here is the content of the file `{filename}` to be tested:
```python
{file_content}
```

Now, generate the complete code for test_{filename}.
"""
        
        # Use _call_llm from base class
        test_code_content = self._call_llm(system_message, prompt, logger)
        return test_code_content

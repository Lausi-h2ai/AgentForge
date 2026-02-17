"""
DocumentationAgent - Generates project documentation.
Maintains backward compatibility.
"""
from .base_agent import BaseAgent


class DocumentationAgent(BaseAgent):
    """
    Documentation agent for generating README and docs.
    
    Args:
        llm_class: LLM class to use
        llm_args: LLM configuration arguments
    """
    
    def __init__(self, llm_class, llm_args):
        super().__init__(llm_class, llm_args, temperature=0.2, agent_name="DocumentationAgent")
    
    def write_documentation(self, project_name, project_structure, run_command, requirements_content, logger):
        """
        Generate README.md for the project.
        
        Args:
            project_name: Name of the project
            project_structure: String representation of file structure
            run_command: Command to run the application
            requirements_content: Content of requirements file
            logger: Logger instance
        
        Returns:
            README content as string
        """
        system_message = f"""You are a senior technical writer. Create a clear, comprehensive README.md.

You will be given the project name, file structure, run command, and requirements file contents.

Structure your README.md as follows:
1. **Project Title:** Use the provided project name.
2. **Overview:** Brief one-paragraph summary based on file structure and dependencies.
3. **File Structure:** Present the file structure in clean, readable format.
4. **Prerequisites:** List dependencies from requirements file.
5. **Installation & Setup:** Step-by-step guide:
    - Create virtual environment
    - Install dependencies using `pip install -r requirements.txt`
    - Mention any database initialization if needed
6. **Running the Application:** State the command to run the project.
7. **Usage:** Briefly explain how to use the application.

Generate only the Markdown content for README.md. No other text or explanations.
"""
        
        prompt = f"""
Project Name: {project_name}

File Structure:
{project_structure}

Run Command:
`{run_command}`

Requirements (`requirements.txt`):
{requirements_content}
"""
        
        # Use _call_llm from base class
        readme_content = self._call_llm(system_message, prompt, logger)
        return readme_content

"""
TesterAgent - Runs quality gates (linting, testing) in Docker.
Maintains backward compatibility with original implementation.
"""
import docker
import os
import json
from .base_agent import BaseAgent
from .utils import parse_json_from_response


class TesterAgent(BaseAgent):
    """
    Tester agent for running automated quality checks.
    
    Args:
        llm_class: LLM class to use
        llm_args: LLM configuration arguments
        work_dir: Working directory for the project
    """
    
    def __init__(self, llm_class, llm_args, work_dir):
        super().__init__(llm_class, llm_args, temperature=0.1, agent_name="TesterAgent")
        
        # Initialize instance variables AFTER super().__init__()
        self.work_dir = os.path.abspath(work_dir)
        self.docker_client = docker.from_env()
    
    def generate_test_plan(self, technical_architecture, logger):
        """
        Generate testing and validation plan based on architecture.
        
        Args:
            technical_architecture: Architecture dict from SoftwareArchitectAgent
            logger: Logger instance
        
        Returns:
            Dict with test plan or None on failure
        """
        system_message = """You are an expert DevOps and QA Engineer.
Create a testing and validation plan for a software project based on its architecture.

You will be given the project's architecture (technology stack, dependencies, file structure).

**Your Task:**
Define necessary commands for linting and running tests in a sandboxed Docker environment.

**OUTPUT FORMAT:**
Your response MUST be a valid JSON object with these keys:
- "docker_base_image": Most appropriate base Docker image (e.g., "python:3.9-slim", "node:18-alpine")
- "install_command": Shell command to install dependencies (e.g., "pip install -r requirements.txt", "npm install")
- "lint_command": Shell command to run linter (empty string "" if no linter obvious)
- "test_command": Shell command to run tests (empty string "" if no test framework obvious)

**Example for Python/Flask:**
{
  "docker_base_image": "python:3.9-slim",
  "install_command": "pip install -r requirements.txt flake8 pytest",
  "lint_command": "flake8 --ignore=E501,W503 --max-line-length=88 .",
  "test_command": "pytest"
}

**Example for TypeScript/Express:**
{
  "docker_base_image": "node:18-alpine",
  "install_command": "npm install",
  "lint_command": "npx eslint src/**/*.ts",
  "test_command": "npm test"
}

Generate ONLY the JSON object. No markdown, no explanations.
"""
        
        prompt = f"""
Here is the technical architecture of the project to be tested:
```json
{json.dumps(technical_architecture, indent=2)}
```

Generate the test and validation plan in the specified JSON format.
"""
        
        response_str = self._call_llm(system_message, prompt, logger)
        data = parse_json_from_response(response_str)
        
        required_keys = ["docker_base_image", "install_command", "lint_command", "test_command"]
        
        if data and all(k in data for k in required_keys):
            return data
        else:
            print("❌ Error: TesterAgent failed to generate valid test plan.")
            return None
    
    def _run_docker_command(self, base_image, install_cmd, run_cmd):
        """
        Generic helper to build and run a command in Docker container.
        
        Args:
            base_image: Docker base image
            install_cmd: Installation command
            run_cmd: Command to run
        
        Returns:
            Tuple of (success: bool, output: str)
        """
        if not run_cmd:
            return True, "Command is empty, skipping."
        
        dockerfile_content = f"""
FROM {base_image}
WORKDIR /app
COPY . .
RUN {install_cmd if install_cmd else "echo 'No install command'"}
CMD {json.dumps(run_cmd.split())}
"""
        
        dockerfile_path = os.path.join(self.work_dir, "Dockerfile.test-runner")
        with open(dockerfile_path, "w", encoding="utf-8") as f:
            f.write(dockerfile_content)
        
        try:
            image, _ = self.docker_client.images.build(
                path=self.work_dir,
                dockerfile=dockerfile_path,
                tag="test-runner",
                rm=True
            )
            
            # Run the container and wait
            container = self.docker_client.containers.run(
                "test-runner",
                detach=False,
                remove=True
            )
            output = container.decode('utf-8')
            
            print(f"✅ Docker command '{run_cmd}' completed successfully.")
            print(f"--- Output ---\n{output}\n------------")
            return True, output
        
        except docker.errors.ContainerError as e:
            error_output = e.stderr.decode('utf-8')
            print(f"❌ Docker command '{run_cmd}' failed with exit code {e.exit_status}.")
            return False, error_output
        
        except Exception as e:
            return False, f"Unexpected error during Docker execution: {e}"
    
    def run_quality_gate(self, technical_architecture, logger):
        """
        Main entry point for tester. Generate plan then execute.
        
        Args:
            technical_architecture: Architecture dict
            logger: Logger instance
        
        Returns:
            Tuple of (success: bool, message: str)
        """
        # Store logger for later use
        self.logger = logger
        
        self.logger.log_phase("Quality Assurance Gate")
        
        # 1. Generate test plan
        self.logger.log_task(1, 1, "Generating QA Plan")
        self.logger.start_step(1, 1)
        test_plan = self.generate_test_plan(technical_architecture, logger)
        
        if not test_plan:
            return False, "Could not generate test plan."
        
        # 2. Execute the plan
        base_image = test_plan["docker_base_image"]
        install_cmd = test_plan["install_command"]
        
        # Run Linter
        self.logger.log_task(1, 2, "Executing Linter")
        self.logger.start_step(1, 1)
        lint_success, lint_output = self._run_docker_command(
            base_image,
            install_cmd,
            test_plan["lint_command"]
        )
        
        if not lint_success:
            return False, f"Linting failed:\n{lint_output}"
        
        # Run Unit Tests
        self.logger.log_task(2, 2, "Executing Unit Tests")
        self.logger.start_step(1, 1)
        test_success, test_output = self._run_docker_command(
            base_image,
            install_cmd,
            test_plan["test_command"]
        )
        
        if not test_success:
            return False, f"Unit tests failed:\n{test_output}"
        
        return True, "All automated quality checks (Linting & Unit Tests) passed."

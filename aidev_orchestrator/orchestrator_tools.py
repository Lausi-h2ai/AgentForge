import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Dict, Any, List, Literal, Optional
from tools import get_code_summary
from tools.universal_refactoring import add_code_block as _add_code_block,    refactor_rename_symbol as _refactor_rename_symbol, delete_code_block as _delete_code_block

try:
    from pydantic import BaseModel, Field
except ImportError:  # pragma: no cover - exercised only in minimal installs
    class BaseModel:
        def __init__(self, **kwargs):
            for key, value in kwargs.items():
                setattr(self, key, value)

        @classmethod
        def model_validate(cls, obj):
            if isinstance(obj, cls):
                return obj
            if isinstance(obj, dict):
                return cls(**obj)
            return cls()

        def model_dump(self):
            return dict(self.__dict__)

    def Field(*_args, **_kwargs):
        return None


class ReviewIssue(BaseModel):
    """Single code review issue."""
    severity: Literal["critical", "major", "minor", "suggestion"] = Field(
        description="Severity level of the issue"
    )
    type: Literal[
        "typo", "style_violation", "import_error", "naming_convention",
        "missing_feature", "incomplete_feature", "logic_bug", "integration_issue",
        "syntax_error"
    ] = Field(
        description="Category of the issue"
    )
    file: str = Field(
        description="Full path of the file containing the issue"
    )
    line: int = Field(
        description="Line number where the issue occurs (approximate)"
    )
    description: str = Field(
        description="Clear one-sentence explanation of what is wrong"
    )
    suggestion: str = Field(
        description="Simple recommendation on how to fix the issue"
    )


class ReviewReport(BaseModel):
    """The complete set of issues found in a code review. This is the required input for the finish_review tool."""
    issues: List[ReviewIssue] = Field(
        description="A list of all issue objects found. If no issues were found, this MUST be an empty list []."
    )
    confidence: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Reviewer confidence score from 0.0 to 1.0"
    )


class OrchestratorTools:
    def __init__(self, orchestrator_instance):
        """
        Initializes the tool suite with a reference to the main orchestrator.
        This allows tools to access the orchestrator's state (files, project_dir, etc.).
        """
        self.orchestrator = orchestrator_instance

    def _validate_file_path(self, filename):
        """
        Validate file path works on Windows, Linux, and macOS.
        Prevents path traversal attacks.
        """
        if not filename:
            raise ValueError("Filename cannot be empty")

        if isinstance(filename, str):
            trimmed = filename.strip()
            if trimmed.startswith("workspace/"):
                filename = trimmed[len("workspace/"):]
            elif trimmed.startswith("workspace\\"):
                filename = trimmed[len("workspace\\"):]

        # Step 1: Normalize the path (handles / and \ on all platforms)
        normalized = os.path.normpath(filename)

        # Step 2: Check for absolute paths or parent directory references
        if os.path.isabs(normalized):
            raise ValueError(
                f"Invalid file path: {filename}. "
                "Absolute paths are not allowed."
            )

        if normalized.startswith(".."):
            raise ValueError(
                f"Invalid file path: {filename}. "
                "Parent directory references (..) are not allowed."
            )

        # Step 3: Build full path and resolve it (handles case and symlinks)
        full_path = os.path.join(self.orchestrator.project_dir, normalized)

        # realpath() is KEY for Windows:
        # - Resolves symlinks
        # - Normalizes case (C:\ vs c:\)
        # - Resolves . and ..
        real_full_path = os.path.realpath(full_path)
        real_project_dir = os.path.realpath(self.orchestrator.project_dir)

        # Step 4: Ensure path is within project directory
        # Use os.path.commonpath to handle Windows case-insensitivity
        try:
            # commonpath raises ValueError if paths are on different drives
            common = os.path.commonpath([real_full_path, real_project_dir])

            # The common path must be exactly the project directory
            if os.path.normcase(common) != os.path.normcase(real_project_dir):
                raise ValueError(
                    f"File path escapes project directory: {filename}"
                )
        except ValueError:
            # Different drives on Windows (C:\ vs D:\)
            raise ValueError(
                f"File path is on a different drive: {filename}"
            )

        # Return the normalized path (not the real path, to preserve user's intent)
        return normalized

    def add_code_block(
        self,
        filepath: str = None,
        new_code: str = None,
        location: str = "end_of_file",
        target_name: str = None,
        properties: Optional[Dict[str, Any]] = None,
    ) -> dict:
        """Add code block at semantic location."""
        if properties and isinstance(properties, dict):
            filepath = filepath or properties.get("filepath")
            new_code = new_code or properties.get("new_code")
            location = properties.get("location", location)
            target_name = properties.get("target_name", target_name)

        if not filepath or new_code is None:
            return {
                "success": False,
                "error": "add_code_block requires filepath and new_code",
            }

        filename = self._validate_file_path(filepath)
        filepath = os.path.join(self.orchestrator.project_dir, filename)
        if not os.path.exists(filepath):
            return {
                "success": False,
                "error": f"File {filename} does not exist, use tool write_file instead",
            }
        return _add_code_block(filepath, new_code, location, target_name)

    def recall_memory(
        self,
        query: str,
        agent_name: Optional[str] = None,
        top_k: int = 5,
        max_chars: int = 2000,
    ) -> dict:
        """
        Read-only memory recall for agent context.
        Returns relevant memory context text for the provided query.
        """
        if not query or not str(query).strip():
            return {"success": False, "error": "Query is required for recall_memory."}

        memory = getattr(self.orchestrator, "memory", None)
        if not memory or not getattr(memory, "enabled", False):
            return {"success": False, "error": "Memory unavailable or disabled."}

        project_name = getattr(self.orchestrator, "project_name", None)
        if not project_name:
            return {"success": False, "error": "Project context is unavailable for memory recall."}

        try:
            context = memory.recall_combined(
                query=query,
                project_name=project_name,
                agent_name=agent_name,
                top_k=top_k,
                max_chars=max_chars,
            )
            return {
                "success": True,
                "memory_context": context or "",
                "message": "Memory recall complete.",
            }
        except Exception as e:
            return {"success": False, "error": f"Memory recall failed: {str(e)}"}

    def refactor_rename_symbol(
        self,
        filepath: str,
        old_name: str,
        new_name: str,
        symbol_type: str = "all"
    ) -> dict:
        """Safely rename a symbol."""
        filepath = self._validate_file_path(filepath)
        filepath = os.path.join(self.orchestrator.project_dir, filepath)
        return _refactor_rename_symbol(filepath, old_name, new_name, symbol_type)

    def delete_code_block(
        self,
        filepath: str,
        block_name: str,
        block_type: str = "auto"
    ) -> dict:
        """Delete a code block by name."""
        filepath = self._validate_file_path(filepath)
        filepath = os.path.join(self.orchestrator.project_dir, filepath)

        return _delete_code_block(filepath, block_name, block_type)

    def replace_text(self, filename, old_text, new_text, count=1):
        """
        Replace text in an existing file.
        
        CRITICAL FIX: Decode escape sequences in both old and new text
        """
        try:
            validated_filename = self._validate_file_path(filename)
        except ValueError as e:
            return {"success": False, "error": str(e)}
        filepath = Path(self.orchestrator.project_dir) / validated_filename
        
        if not filepath.exists():
            return {
                "success": False,
                    "error": f"File '{validated_filename}' does not exist."
            }
        
        try:
            # Read current content
            with open(filepath, 'r', encoding='utf-8') as f:
                current_content = f.read()
            
            if old_text not in current_content:
                return {
                    "success": False,
                    "error": f"Text to replace not found: {old_text[:50]}..."
                }
            
            # Replace text
            new_content = current_content.replace(old_text, new_text, count)
            
            # Write updated content
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(new_content)
            
            occurrences = current_content.count(old_text)
            replaced = min(count, occurrences)
            
            return {
                "success": True,
                "message": f"Replaced {replaced} occurrence(s) in '{validated_filename}'."
            }
        
        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to replace text: {str(e)}"
            }

    def insert_text(self, filename, content_to_insert, before_text=None, after_text=None):
        """
        Insert text into an existing file.
        
        CRITICAL FIX: Also decode escape sequences here
        """
        try:
            validated_filename = self._validate_file_path(filename)
        except ValueError as e:
            return {"success": False, "error": str(e)}
        filepath = Path(self.orchestrator.project_dir) / validated_filename
        
        if not filepath.exists():
            return {
                "success": False,
                "error": f"File '{validated_filename}' does not exist. Use write_file to create it."
            }
        
        try:
            # Read current content
            with open(filepath, 'r', encoding='utf-8') as f:
                current_content = f.read()
            
            # Find insertion point
            if before_text:
                if before_text not in current_content:
                    return {
                        "success": False,
                        "error": f"Anchor text not found: {before_text[:50]}..."
                    }
                new_content = current_content.replace(before_text, content_to_insert + before_text, 1)
            
            elif after_text:
                if after_text not in current_content:
                    return {
                        "success": False,
                        "error": f"Anchor text not found: {after_text[:50]}..."
                    }
                new_content = current_content.replace(after_text, after_text + content_to_insert, 1)
            
            else:
                # Append to end of file
                new_content = current_content + content_to_insert
            
            # Write updated content
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(new_content)
            
            return {
                "success": True,
                "message": f"Text inserted into '{validated_filename}'."
            }
        
        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to insert text: {str(e)}"
            }

    def read_file(self, filename: str, **kwargs) -> dict:
        filename = self._validate_file_path(filename)
        filepath = os.path.join(self.orchestrator.project_dir, filename)
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                return {"success": True, "content": f.read()}
        except FileNotFoundError:
            return {"success": False, "error": f"Error: file '{filename}' does not exist."}
        except Exception as e:
            return {"success": False, "error": f"Error reading file '{filename}': {e}"}

    def create_directory(self, dirname: str) -> dict:
        if not dirname:
            return {"success": False, "error": "folder name has not been specified."}
        try:
            validated_dirname = self._validate_file_path(dirname)
        except ValueError as e:
            return {"success": False, "error": str(e)}
        dirpath = os.path.join(self.orchestrator.project_dir, validated_dirname)
        if os.path.exists(dirpath):
            return {"success": False, "error": f"Folder '{validated_dirname}' already exists."}
        os.makedirs(dirpath)
        return {"success": True, "message": f"Folder '{validated_dirname}' successsfully created."}
    
    def directory_exists(self, dirname: str, **kwargs) -> bool:
        if not dirname:
            return {"success": False, "error": "Directory name has not been specified."}
        dirpath = os.path.join(self.orchestrator.project_dir, dirname)
        try:
            exists = os.path.isdir(dirpath)
            return {
                "success": True, 
                "exists": exists,
                "message": f"Directory '{dirname}' " + ("exists ✅" if exists else "does NOT exist ❌")
            }
        except Exception as e:
            return {"success": False, "error": f"Error checking directory '{dirname}': {e}"}

    def list_directories(self) -> List[str]:
        if not self.orchestrator.repo:
            return "Error: Git repository not initialized."
        return [item.path for item in self.orchestrator.repo.tree().traverse() if item.type == 'tree']

    def list_files(self, **kwargs):
        if not self.orchestrator.repo:
            return ["Error: Git repository not initialized."]
        
        workspace_path = Path(self.orchestrator.repo.working_dir)
        files = []
        
        for root, dirs, filenames in os.walk(workspace_path):
            dirs[:] = [d for d in dirs if d not in {'.git', '__pycache__'}]
            for filename in filenames:
                if not filename.endswith('.pyc'):
                    full_path = Path(root) / filename
                    rel_path = full_path.relative_to(workspace_path)
                    files.append(str(rel_path).replace('\\', '/'))
        
        return sorted(files) if files else ["(no files)"]

    def autoformat_code(self, filename) -> dict:
        filename = self._validate_file_path(filename)
        filepath = os.path.join(self.orchestrator.project_dir, filename)
        # A simple implementation using a local formatter
        # A better one would use Docker for security and consistency
        try:
            if filename.endswith(".py"):
                # Assuming 'black' is installed in the orchestrator's environment
                result = subprocess.run(
                    ['black', filepath], capture_output=True, text=True)
                if result.returncode != 0:
                    return {"success": False, "error": f"Error formatting file: {result.stderr}"}
                return {"success": True, "message": f"File '{filename}' was auto-formatted successfully."}
            elif filename.endswith((".ts", ".tsx", ".js", ".jsx")):
                # Assuming 'prettier' is installed in the orchestrator's environment
                result = subprocess.run(
                    ['prettier', '--write', filepath], capture_output=True, text=True)
                if result.returncode != 0:
                    return {"success": False, "error": f"Error formatting file: {result.stderr}"}
                return {"success": True, "message": f"File '{filename}' was auto-formatted successfully."}
            elif filename.endswith((".c", ".cpp", ".cc", ".cxx", ".h", ".hpp")):
                # Assuming 'clang-format' is installed in the orchestrator's environment
                result = subprocess.run(
                    ['clang-format', '-i', filepath], capture_output=True, text=True)
                if result.returncode != 0:
                    return {"success": False, "error": f"Error formatting file: {result.stderr}"}
                return {"success": True, "message": f"File '{filename}' was auto-formatted successfully."}
            else:
                return {"success": False, "error": f"no autoformatter provider for {filename}"}
        except Exception as e:
            return {"success": False, "error": f"Failed to run autoformatter: {e}"}

    def delete_file(self, filename: str) -> dict:
        """
        Securely deletes a file within the project workspace.

        Args:
            filename: The path of the file to delete, relative to the project root.

        Returns:
            A dictionary indicating the success or failure of the operation.
        """
        try:
            # SECURITY: Validate the path is within the project and contains no ".." traversal.
            validated_filename = self._validate_file_path(filename)
            filepath = os.path.join(self.orchestrator.project_dir, validated_filename)

            # Check 1: Does the path exist?
            if not os.path.exists(filepath):
                return {"success": False, "error": f"File '{validated_filename}' does not exist and cannot be deleted."}

            # Check 2: Is it a file and not a directory?
            if not os.path.isfile(filepath):
                return {"success": False, "error": f"Path '{validated_filename}' is a directory, not a file. Use a 'delete_directory' tool instead."}

            # Delete the file
            os.remove(filepath)

            # CRITICAL UPDATE: The RAG index must be updated to "forget" this file.
            # The simplest way is to rebuild the index from the current disk state.
            self.orchestrator.logger.log(
                "INFO", f"File '{validated_filename}' deleted. Updating RAG index.")
            self.orchestrator._build_index_from_disk()

            return {"success": True, "message": f"File '{validated_filename}' was successfully deleted."}

        except ValueError as e:
            # Error raised by _validate_file_path
            return {"success": False, "error": str(e)}
        except Exception as e:
            # Other potential errors (e.g., file system permissions)
            return {"success": False, "error": f"An unexpected error occurred while deleting file '{filename}': {e}"}

    def write_file(self, filename, content):
        """
        Create a new file with content - robust version.
        Preserve Unicode and literal escapes in the supplied source text.
        """
        try:
            validated_filename = self._validate_file_path(filename)
        except ValueError as e:
            return {"success": False, "error": str(e)}
        filepath = Path(self.orchestrator.project_dir) / validated_filename
        
        if filepath.exists():
            return {
                "success": False,
                "error": "File already exists. Use insert_text or replace_text to modify it."
            }
        
        try:
            filepath.parent.mkdir(parents=True, exist_ok=True)
            
            # Tool arguments are already decoded by the transport. Preserve source text.
            # Write the file
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)
            
            # Auto-format if available
            try:
                format_result = self.orchestrator.format_file(str(filepath))
                if format_result.get('success'):
                    return {
                        "success": True,
                        "message": f"File '{validated_filename}' created and formatted successfully."
                    }
            except:
                pass
            
            return {
                "success": True,
                "message": f"File '{validated_filename}' created successfully."
            }
        
        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to create file: {str(e)}"
            }

    def get_code_summary(self, filename: str, **kwargs) -> Dict[str, Any]:
        filename = self._validate_file_path(filename)
        filepath = os.path.join(self.orchestrator.project_dir, filename)
        summary = get_code_summary(filepath)
        return json.dumps(summary, indent=2, ensure_ascii=False)

    def submit_review(self, report: Optional[ReviewReport] = None, **kwargs) -> dict:
        """
         Call this tool ONLY when your investigation is complete to submit your final report.

         Args:
             report: A ReviewReport object containing a list of all issues found.
        """
        # The 'report' argument will be a validated Pydantic object
        if report is None:
            if "report" in kwargs:
                report = kwargs["report"]
            elif "issues" in kwargs:
                report = {"issues": kwargs.get("issues"), "confidence": kwargs.get("confidence")}
        if not isinstance(report, ReviewReport):
            validated_report = ReviewReport.model_validate(report)
        else:
            validated_report = report
        issues_list: List[Dict[str, Any]] = []
        for issue in validated_report.issues:
            if isinstance(issue, ReviewIssue):
                issues_list.append(issue.model_dump())
            elif isinstance(issue, str):
                issues_list.append(ReviewIssue(
                    severity="major",
                    type="integration_issue",
                    file="N/A",
                    line=0,
                    description=issue,
                    suggestion="Review issue details and apply fix."
                ).model_dump())
            elif isinstance(issue, dict):
                issues_list.append(ReviewIssue.model_validate(issue).model_dump())
            else:
                issues_list.append(ReviewIssue(
                    severity="major",
                    type="integration_issue",
                    file="N/A",
                    line=0,
                    description=str(issue),
                    suggestion="Review issue details and apply fix."
                ).model_dump())
        return {
            "success": True,
            "message": f"Review submitted with {len(issues_list)} issue(s)",
            "issues": issues_list,
            "confidence": validated_report.confidence
        }

    async def call_agent(self, agent_name: str, message: str) -> str:
        """
        Call another agent to ask for help, clarification, or a review.
        Args:
            agent_name: The name of the agent to call (e.g., "CodeReviewerAgent", "ProductOwnerAgent", "SoftwareArchitectAgent").
            message: The question or request for the agent.
        """
        agent = self.orchestrator.get_agent_by_name(agent_name)
        if not agent:
            return f"Error: Agent '{agent_name}' not found. Available agents: {self.orchestrator.get_available_agent_names()}"

        # We use the standardized chat method
        try:
            response = await agent.chat(message)

            return response
        except Exception as e:
            return f"Error calling agent {agent_name}: {str(e)}"

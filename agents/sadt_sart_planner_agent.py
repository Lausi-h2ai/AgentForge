"""
Enhanced SADTSARTPlannerAgent with Complexity-Based Task & Action Granularity

Features:
- Complexity detection (simple, medium, complex)
- Complexity-branched task counts (3, 6-12, 20-30 tasks)
- Complexity-branched action counts (1-2, 2-3, 3-8 actions per task)
- Detailed subtask guidance for complex projects
- Better handling of multi-layer feature breakdown
- More nuanced impossible task detection
"""

from .base_agent import BaseAgent
import json
import os
import re
from typing import List
from prompt_loader import load_versioned_prompt


DEFAULT_PLANNER_BASE_PROMPT = """You are a task planning expert for software projects.
Create a detailed, executable plan for coding agents.

Reliability rules:
- Output valid JSON only.
- Do not include tasks that require running commands, installing packages, or manual actions.
- Every task must produce concrete file changes.

Quality rules:
- Plans should be complete, scoped, and implementation-ready.
- Include error handling and realistic integration steps where needed.
"""


class SADTSARTPlannerAgent(BaseAgent):
    def __init__(self, llm_class, llm_args):
        super().__init__(llm_class, llm_args, temperature=0.2,
                         agent_name="SADTSARTPlannerAgent")

    def _detect_project_complexity(self, project_context: str) -> str:
        """
        Detect if project is simple, medium, or complex.
        Returns: "simple", "medium", or "complex"
        """
        context_lower = project_context.lower()

        # CRITICAL: Hello world is ALWAYS simple
        if "hello world" in context_lower or "hello, world" in context_lower:
            return "simple"

        # Simple indicators (expanded)
        simple_indicators = [
            "simple script", "basic test", "single file",
            "just test", "one file", "2 file", "two file",
            "basic script", "minimal", "trivial"
        ]

        # Complex indicators - expanded for large projects
        complex_indicators = [
            "microservice", "kubernetes", "docker-compose",
            "multiple database", "authentication system",
            "payment", "real-time", "websocket", "multi-tenant",
            "10+ file", "many component", "full-stack",
            "comprehensive", "complete specification", "production-ready",
            "advanced", "rest api", "orm", "react", "fastapi",
            "receipt ocr", "ai recipe", "ollama"
        ]

        # Count indicators
        simple_count = sum(1 for indicator in simple_indicators if indicator in context_lower)
        complex_count = sum(1 for indicator in complex_indicators if indicator in context_lower)

        # Decision logic
        if simple_count > 0 and complex_count == 0:
            return "simple"
        elif complex_count >= 2:  # Multiple complex indicators = complex
            return "complex"
        elif complex_count > 0:
            return "medium"
        else:
            # Check file count
            if "1-3 file" in context_lower or "2-3 file" in context_lower:
                return "simple"
            elif "10+" in context_lower or "many file" in context_lower:
                return "complex"
            else:
                return "medium"

    def _contains_impossible_tasks(self, plan: dict, logger=None) -> tuple:
        """
        Check if plan contains tasks that agents cannot execute.
        Returns: (has_impossible_tasks: bool, error_messages: list)
        """
        # Use regex patterns to catch execution commands, not mere mentions
        impossible_patterns = [
            # Installation commands
            (r'\b(pip\s+install|npm\s+install|yarn\s+add|composer\s+install)\b',
             "Installation commands (agents cannot run pip/npm/yarn)"),
            # Execution commands (run/execute + tool/app name)
            (r'\b(run|execute|launch|start)\s+(pytest|test|the\s+test|application|server|app)\b',
             "Execution commands (agents cannot run applications or tests)"),
            # Git operations
            (r'\b(git\s+commit|git\s+push|git\s+add|stage\s+files)\b',
             "Git operations (handled by orchestrator automatically)"),
            # Deployment
            #(r'\b(deploy|deployment|publish\s+to)\b',
            # "Deployment operations (agents cannot deploy)"),
        ]

        errors = []

        def check_task(task, path=""):
            task_id = task.get("id", "unknown")
            title = task.get("title", "").lower()
            description = task.get("description", "").lower()
            combined = f"{title} {description}"

            # Check each pattern
            for pattern, reason in impossible_patterns:
                if re.search(pattern, combined):
                    match = re.search(pattern, combined).group()
                    errors.append(f"Task {task_id}: Contains '{match}' - {reason}")
                    return True

            # Check subtasks recursively
            for subtask in task.get("subtasks", []):
                if check_task(subtask, f"{path}/{task_id}"):
                    return True

            return False

        # Check all top-level tasks
        has_impossible = False
        for task in plan.get("tasks", []):
            if check_task(task):
                has_impossible = True

        return has_impossible, errors

    def generate_workplan(self, project_title, project_context, logger=None):
        """
        Enhanced workplan generation with complexity-aware task & subtask planning.
        Complexity-branched max_tasks and depth_limit.
        """
        # Detect complexity
        complexity = self._detect_project_complexity(project_context)

        if logger:
            logger.log("INFO", f"📊 Detected project complexity: {complexity.upper()}")

        print(f"\n📊 Project Complexity: {complexity.upper()}")

        # Adjust instructions HEAVILY based on complexity
        if complexity == "simple":
            max_tasks = 3
            depth_limit = 2
            max_subtask_depth = 1

            complexity_note = """
**PROJECT COMPLEXITY: SIMPLE** (e.g., hello world, basic script)

**CRITICAL RULES:**

1. Generate EXACTLY 2-3 TOP-LEVEL TASKS (no more!)
2. NO subtasks - keep flat and simple
3. NO separate create + modify tasks - combine them!
4. NO verification tasks - agent will verify automatically
5. NO setup/installation tasks - agent cannot execute them

**GOOD PLAN FOR HELLO WORLD:**

```json
{
  "tasks": [
    {
      "id": "T1",
      "title": "Create hello_world.py",
      "description": "Create hello_world.py with print('Hello, World!') and comments",
      "subtasks": []
    },
    {
      "id": "T2",
      "title": "Create test_hello_world.py",
      "description": "Create test file with pytest test that verifies output",
      "subtasks": []
    }
  ]
}
```

**2 tasks total!**
"""

        elif complexity == "medium":
            max_tasks = 12
            depth_limit = 3
            max_subtask_depth = 2

            complexity_note = """
**PROJECT COMPLEXITY: MEDIUM** (e.g., multi-file backend, basic CRUD app)

**TASK GENERATION RULES:**

1. Generate 8-12 TOP-LEVEL TASKS (one per significant feature/module)
2. Each top-level task may have 1-2 SUBTASKS (for related operations)
3. Group related file operations (create + add content = 1 task)
4. Avoid verification/execution tasks
5. Avoid installation tasks

**EXAMPLE TASK STRUCTURE FOR CRUD API:**

```json
{
  "tasks": [
    {
      "id": "T1",
      "title": "Create database models",
      "description": "Create models.py with User and Item SQLAlchemy models with relationships",
      "subtasks": []
    },
    {
      "id": "T2",
      "title": "Create User CRUD API endpoints",
      "description": "Create routers/users.py with GET, POST, PUT, DELETE endpoints including validation",
      "subtasks": []
    },
    {
      "id": "T3",
      "title": "Create Item CRUD API endpoints",
      "description": "Create routers/items.py with GET, POST, PUT, DELETE endpoints including validation",
      "subtasks": []
    }
  ]
}
```

Task strategy:
- One task per significant module/feature
- Combine create + populate in one task
- No micro-splitting
"""

        else:  # complex
            max_tasks = 30
            depth_limit = 3
            max_subtask_depth = 3

            complexity_note = """
**PROJECT COMPLEXITY: COMPLEX** (e.g., full-stack app, microservices, AI integration)

**TASK GENERATION RULES - HIERARCHICAL BREAKDOWN:**

1. Generate 20-30 TOP-LEVEL TASKS organized by major feature/component areas.

2. EACH TOP-LEVEL TASK should have 2-4 meaningful SUBTASKS covering:
   - Data models / schemas
   - API endpoints (success + error handling)
   - Validation & error paths
   - Frontend/UI components
   - Integration / wiring

3. Example hierarchical structure:

```json
{
  "tasks": [
    {
      "id": "T1",
      "title": "Pantry Management - Backend",
      "description": "Create all backend APIs and models for pantry CRUD operations",
      "subtasks": [
        {
          "id": "T1.1",
          "title": "Create PantryItem SQLAlchemy model",
          "description": "Define PantryItem model with id, ingredient_name, quantity, unit, category, timestamps"
        },
        {
          "id": "T1.2",
          "title": "Create pantry CRUD router",
          "description": "Create routers/pantry.py with GET (all items), POST (add), PATCH (update), DELETE (remove) endpoints"
        },
        {
          "id": "T1.3",
          "title": "Add pantry validation & error handling",
          "description": "Add Pydantic validators, try/catch blocks, appropriate HTTP status codes to routers/pantry.py"
        }
      ]
    },
    {
      "id": "T2",
      "title": "Pantry Management - Frontend",
      "description": "Create React components for pantry UI with forms, modals, grid display",
      "subtasks": [
        {
          "id": "T2.1",
          "title": "Create PantryGrid component",
          "description": "Create components/PantryGrid.jsx to display pantry items in responsive 3-col grid (desktop) with loading/error states"
        },
        {
          "id": "T2.2",
          "title": "Create AddItemModal component",
          "description": "Create components/AddItemModal.jsx with form (ingredient autocomplete, quantity, unit), validation, API call integration"
        },
        {
          "id": "T2.3",
          "title": "Create EditItemModal component",
          "description": "Create components/EditItemModal.jsx for inline editing of pantry items"
        },
        {
          "id": "T2.4",
          "title": "Add API client methods for pantry",
          "description": "Add axios calls to api/pantryClient.js: getItems(), addItem(), updateItem(), deleteItem()"
        }
      ]
    },
    {
      "id": "T3",
      "title": "Recipe Generation - Backend (Ollama Integration)",
      "description": "Create recipe generation endpoints using Ollama LLM",
      "subtasks": [
        {
          "id": "T3.1",
          "title": "Create OllamaClient service",
          "description": "Create services/ollama_client.py with connect(), generate_recipe(), handle_failures() methods"
        },
        {
          "id": "T3.2",
          "title": "Create recipe router",
          "description": "Create routers/recipes.py with POST /recipes/generate endpoint that accepts cuisine/time/difficulty preferences"
        },
        {
          "id": "T3.3",
          "title": "Create Recipe SQLAlchemy model",
          "description": "Define Recipe model with title, ingredients_json, instructions_json, cuisine, time_minutes, difficulty"
        }
      ]
    },
    {
      "id": "T4",
      "title": "Recipe Generation - Frontend",
      "description": "Create React UI for recipe generation with preferences and display",
      "subtasks": [
        {
          "id": "T4.1",
          "title": "Create RecipeGenerator component",
          "description": "Create components/RecipeGenerator.jsx with form (cuisine, time slider, difficulty, avoid ingredients), loading spinner, error handling"
        },
        {
          "id": "T4.2",
          "title": "Create RecipeCard component",
          "description": "Create components/RecipeCard.jsx to display generated recipe (title, ingredients, instructions, metadata)"
        },
        {
          "id": "T4.3",
          "title": "Add recipe API client methods",
          "description": "Add to api/recipeClient.js: generateRecipe(), saveRecipe(), getRecipes()"
        }
      ]
    },
    {
      "id": "T5",
      "title": "Receipt Parsing - Backend",
      "description": "Create receipt upload and parsing endpoints",
      "subtasks": [
        {
          "id": "T5.1",
          "title": "Create Receipt SQLAlchemy model",
          "description": "Define Receipt model with file_path, raw_text, parsed_items_json, status"
        },
        {
          "id": "T5.2",
          "title": "Create receipt parser service (regex + LLM)",
          "description": "Create services/receipt_parser.py with parse_with_regex() and parse_with_ollama() functions"
        },
        {
          "id": "T5.3",
          "title": "Create receipt router",
          "description": "Create routers/receipts.py with POST /upload, POST /parse, POST /apply-to-pantry endpoints"
        }
      ]
    },
    {
      "id": "T6",
      "title": "Receipt Parsing - Frontend",
      "description": "Create UI for receipt upload, preview, and item selection",
      "subtasks": [
        {
          "id": "T6.1",
          "title": "Create ReceiptUploadZone component",
          "description": "Create components/ReceiptUploadZone.jsx with drag-drop, file preview, upload button"
        },
        {
          "id": "T6.2",
          "title": "Create ReceiptPreview component",
          "description": "Create components/ReceiptPreview.jsx to display parsed items in table (item, qty, unit, confidence) with checkboxes"
        },
        {
          "id": "T6.3",
          "title": "Add receipt API client methods",
          "description": "Add to api/receiptClient.js: uploadReceipt(), parseReceipt(), applyToPantry()"
        }
      ]
    },
    {
      "id": "T7",
      "title": "Styling & Design System",
      "description": "Create cohesive visual design with CSS variables, components, responsive layouts",
      "subtasks": [
        {
          "id": "T7.1",
          "title": "Create design system CSS",
          "description": "Create styles/design-system.css with color palette, typography, spacing, shadows, animations"
        },
        {
          "id": "T7.2",
          "title": "Create layout & component styles",
          "description": "Create styles/components.css with button, input, modal, card, badge, toast styles"
        },
        {
          "id": "T7.3",
          "title": "Create responsive grid & layout utilities",
          "description": "Create styles/layout.css with grid, flex, responsive breakpoints (mobile/tablet/desktop)"
        }
      ]
    },
    {
      "id": "T8",
      "title": "Meal History & Diversity",
      "description": "Create endpoints and UI for tracking meals and preventing repetition",
      "subtasks": [
        {
          "id": "T8.1",
          "title": "Create MealHistory model & router",
          "description": "Define MealHistory model, create routers/history.py with POST (record meal), GET (history), GET (diversity summary)"
        },
        {
          "id": "T8.2",
          "title": "Create diversity calculation service",
          "description": "Create services/diversity.py with analyze_recent_meals(), get_repeated_ingredients(), suggest_cuisine_variety()"
        }
      ]
    }
  ]
}
```

**Key principles for complex projects:**

- One top-level task = one major feature area or module
- Subtasks = concrete, verifiable file operations
- Each subtask should be completable in <1 hour by an agent
- Organize by component (backend models → endpoints → frontend UI)
- Include validation/error handling explicitly
- Separate data layer from API layer from UI layer
"""

        planner_base = load_versioned_prompt(
            "planner",
            "base",
            DEFAULT_PLANNER_BASE_PROMPT,
        )
        complexity_note = load_versioned_prompt(
            "planner",
            f"complexity/{complexity}",
            complexity_note,
        )

        system_message = f"""{planner_base}

{complexity_note}

**AGENTS CAN DO:**

✅ Create files with content
✅ Modify existing files  
✅ Read files
✅ Delete files

**AGENTS CANNOT DO:**

❌ Run commands (pip install, pytest, python script.py)
❌ Execute applications
❌ Git operations (handled automatically)
❌ Deploy anything

**IMPORTANT: Tool/Framework Names Are OK In Descriptions**

✅ GOOD: "Create test_app.py with pytest test functions"
✅ GOOD: "Write code using Ollama framework"
❌ BAD: "Run pytest command" or "Execute Ollama inference"

The word "pytest" or "Ollama" is fine - just don't ask agent to RUN it!

**JSON FORMAT:**

{{
  "project_title": "string",
  "context": "string",
  "tasks": [
    {{
      "id": "T1",
      "title": "string",
      "description": "string",
      "icom": {{
        "input": ["item1"],
        "control": ["constraint1"],
        "output": ["result1"],
        "mechanism": ["tool1"]
      }},
      "subtasks": [
        {{
          "id": "T1.1",
          "title": "string",
          "description": "string"
        }}
      ]
    }}
  ]
}}

**RULES:**

- Maximum {max_tasks} top-level tasks
- Maximum {depth_limit} levels deep
- Maximum {max_subtask_depth} subtask levels
- Combine file creation with content addition
- No verification tasks (automatic)
- No installation/execution tasks
- NO placeholders, empty files, stubs, or TODO comments
- Never say "empty file", "placeholder", "stub", or "template" in tasks
- Output ONLY valid JSON (no markdown, no comments)
"""

        prompt = f"""PROJECT: {project_title}

CONTEXT:

{project_context}

COMPLEXITY: {complexity.upper()}

Generate a comprehensive workplan with {max_tasks} tasks maximum.
For COMPLEX projects: Create 20-30 top-level tasks, each with 2-4 subtasks.
For MEDIUM projects: Create 8-12 top-level tasks, each with 0-2 subtasks.
For SIMPLE projects: Create 2-3 flat tasks with no subtasks.

Organize by feature/component area. No installation/execution tasks."""

        max_retries = 5

        for attempt in range(max_retries):
            if logger:
                logger.log("INFO", f"Workplan generation attempt {attempt + 1}/{max_retries}")

            response_str = self._call_llm(system_message, prompt, logger)

            plan = self._extract_and_parse_json(response_str, logger)

            if not plan:
                if logger:
                    logger.log("WARNING", f"Attempt {attempt+1} failed validation")
                prompt += f"\n\n**ATTEMPT {attempt+1} FAILED: Invalid JSON**\nEnsure valid JSON format."
                continue

            validation_errors = self._collect_plan_validation_errors(
                plan=plan,
                project_context=project_context,
                max_tasks=max_tasks,
                depth_limit=depth_limit,
                max_subtask_depth=max_subtask_depth,
                logger=logger,
            )

            if not validation_errors:
                if logger:
                    logger.log("INFO", f"✅ Valid workplan generated on attempt {attempt + 1}")
                total_tasks = len(plan.get('tasks', []))
                total_subtasks = sum(len(t.get('subtasks', [])) for t in plan.get('tasks', []))
                print(f"✅ Plan accepted: {total_tasks} top-level tasks, {total_subtasks} subtasks")
                return plan

            if logger:
                logger.log("WARNING", f"Attempt {attempt+1} failed validation")

            # First try deterministic correction using the current plan instead of full regeneration.
            corrected_plan = None
            if attempt < max_retries - 1:
                corrected_plan = self._attempt_plan_correction(
                    project_title=project_title,
                    project_context=project_context,
                    complexity=complexity,
                    existing_plan=plan,
                    validation_errors=validation_errors,
                    system_message=system_message,
                    max_tasks=max_tasks,
                    depth_limit=depth_limit,
                    max_subtask_depth=max_subtask_depth,
                    logger=logger,
                )

            if corrected_plan:
                if logger:
                    logger.log("INFO", f"✅ Corrected workplan accepted on attempt {attempt + 1}")
                total_tasks = len(corrected_plan.get('tasks', []))
                total_subtasks = sum(len(t.get('subtasks', [])) for t in corrected_plan.get('tasks', []))
                print(f"✅ Plan accepted after correction: {total_tasks} top-level tasks, {total_subtasks} subtasks")
                return corrected_plan

            # Fallback: continue normal regeneration with explicit failure feedback.
            prompt += f"\n\n**PREVIOUS ATTEMPT FAILED - VALIDATION ERRORS:**\n"
            for err in validation_errors:
                prompt += f"- {err}\n"
            prompt += "\nRegenerate a complete valid plan that fixes all errors."

        if logger:
            logger.log("ERROR", "❌ Failed to generate valid workplan after all attempts")

        print(f"\n❌ Plan generation failed after {max_retries} attempts")

        return None

    def _collect_plan_validation_errors(
        self,
        plan: dict,
        project_context: str,
        max_tasks: int,
        depth_limit: int,
        max_subtask_depth: int,
        logger=None,
    ) -> List[str]:
        errors: List[str] = []

        if not self._validate_workplan(plan, logger, max_tasks, depth_limit, max_subtask_depth):
            errors.append("Structural validation failed (required fields/types/depth/limits).")
            missing_keys = [k for k in ["project_title", "context", "tasks"] if k not in plan]
            if missing_keys:
                errors.append(f"Missing required keys: {missing_keys}")
            if isinstance(plan, dict) and isinstance(plan.get("tasks"), list) and len(plan["tasks"]) > max_tasks:
                errors.append(f"Too many tasks ({len(plan['tasks'])} > {max_tasks})")
            return errors

        if self._contains_placeholder_tasks(plan):
            errors.append("Plan contains placeholder/stub/TODO tasks.")

        missing_topics = self._check_required_topics(plan, project_context)
        if missing_topics:
            errors.append(f"Plan missing required topics: {', '.join(missing_topics)}")

        has_impossible, impossible_errors = self._contains_impossible_tasks(plan, logger)
        if has_impossible:
            errors.extend(impossible_errors or ["Plan contains impossible tasks."])

        return errors

    def _attempt_plan_correction(
        self,
        project_title: str,
        project_context: str,
        complexity: str,
        existing_plan: dict,
        validation_errors: List[str],
        system_message: str,
        max_tasks: int,
        depth_limit: int,
        max_subtask_depth: int,
        logger=None,
    ) -> dict | None:
        correction_prompt = f"""PROJECT: {project_title}

CONTEXT:

{project_context}

COMPLEXITY: {complexity.upper()}

You previously generated a plan that is close but invalid.
Fix ONLY the listed validation errors while preserving valid task IDs/titles/order where possible.

VALIDATION ERRORS:
{chr(10).join(f"- {e}" for e in validation_errors)}

EXISTING PLAN (JSON):
{json.dumps(existing_plan, ensure_ascii=False, indent=2)}

Output ONLY the full corrected JSON plan with keys: project_title, context, tasks.
Do not output markdown.
"""

        if logger:
            logger.log("INFO", "Attempting plan correction using existing plan context.")

        corrected_response = self._call_llm(system_message, correction_prompt, logger)
        corrected_plan = self._extract_and_parse_json(corrected_response, logger)
        if not corrected_plan:
            return None

        remaining_errors = self._collect_plan_validation_errors(
            plan=corrected_plan,
            project_context=project_context,
            max_tasks=max_tasks,
            depth_limit=depth_limit,
            max_subtask_depth=max_subtask_depth,
            logger=logger,
        )
        if remaining_errors:
            if logger:
                logger.log("WARNING", f"Corrected plan still invalid: {'; '.join(remaining_errors[:4])}")
            return None

        return corrected_plan

    def generate_atomic_actions_for_task(self, task, complexity="medium", logger=None, max_actions_override=None):
        """
        Generate atomic actions with complexity-aware granularity.

        complexity: "simple", "medium", or "complex"
        - simple: 1 action per task (everything in one go)
        - medium: 2-3 actions per task
        - complex: 3-8 actions per task (fine-grained breakdown)
        """

        # Set action count based on complexity
        if complexity == "simple":
            max_actions = 1
            action_guidance = f"{max_actions} action (do everything in one go)"
        elif complexity == "medium":
            max_actions = 3
            action_guidance = f"2-{max_actions} actions (small grouped operations)"
        else:  # complex
            max_actions = 8
            action_guidance = f"3-{max_actions} actions (fine-grained per-step breakdown)"
        if isinstance(max_actions_override, int) and max_actions_override > 0:
            max_actions = min(max_actions, max_actions_override)

        system_message = f"""You are an expert at breaking down tasks into atomic, executable actions.

**COMPLEXITY LEVEL: {complexity.upper()}**

**TASK:**
{{task details}}

**ACTION GENERATION RULES FOR {complexity.upper()} PROJECTS:**

Generate {action_guidance}.

**For SIMPLE projects (1 action max):**
- Combine all operations into one atomic action
- Example: "Create models.py with User, Item, and Relationship definitions"

**For MEDIUM projects (2-3 actions):**
- Group related file operations
- Separate major concerns (data layer, API layer, UI layer)
- Example: 
  - "Create models.py with User and Item SQLAlchemy models"
  - "Create routers/users.py with GET/POST/PUT/DELETE endpoints"

**For COMPLEX projects (3-8 actions, fine-grained):**
- One action per file or per major concern
- Separate: model definition, validation, API endpoints (GET), (POST), (PUT), (DELETE), error handling
- Example for a single task:
  1. "Create PantryItem SQLAlchemy model with id, ingredient_name, quantity, unit, category, timestamps"
  2. "Create pantry router with GET /pantry endpoint (list all items)"
  3. "Create pantry router with POST /pantry endpoint (add item with validation)"
  4. "Create pantry router with PATCH /pantry/{{id}} endpoint (update quantity/unit)"
  5. "Create pantry router with DELETE /pantry/{{id}} endpoint (remove item)"
  6. "Add error handling & HTTP status codes to all pantry endpoints"

**AGENTS CAN ONLY:**

✅ Create/modify/read/delete files
✅ Write code to files
✅ Structure/organize files

❌ Execute commands or run applications
❌ Install packages
❌ Deploy

**Using framework names OK in descriptions:**

✅ GOOD: "Create test.py with pytest test functions"
✅ GOOD: "Add FastAPI route decorator and validation"
❌ BAD: "Run pytest command"
❌ BAD: "Execute the application"

**JSON FORMAT:**

[
  {{
    "action_id": "T1.a",
    "task_id": "T1",
    "instruction": "Clear, specific file operation",
    "constraints": ["constraint1"],
    "expected_output_description": "What this produces"
  }}
]

**IMPORTANT:**
- Generate {max_actions} actions maximum
- Each action should be concrete and file-scoped
- Combine file creation with initial content in one action
- Output ONLY valid JSON array (no markdown, no comments)
"""

        prompt = f"""Task:

{json.dumps(task, indent=2)}

COMPLEXITY: {complexity.upper()}

Generate {max_actions} atomic file operations. 
For complex projects: separate by major concern (model → validation → each HTTP verb → error handling).
For medium: group logically (models, endpoints, UI).
For simple: combine everything.

NO execution commands. Output ONLY valid JSON array."""

        max_retries = 3

        for attempt in range(max_retries):
            response_str = self._call_llm(system_message, prompt, logger)

            actions = self._extract_and_parse_json(response_str, logger)

            if actions and self._validate_actions(actions, task.get('id', 'UNKNOWN'), logger):
                return actions

            if attempt < max_retries - 1:
                prompt += "\n\n**FAILED: Ensure valid JSON array format with correct field names**"

        if logger:
            logger.log("WARNING", f"Failed to generate actions for {task.get('id')}, using fallback")

        return self._create_fallback_action(task)

    # ============ Helper Methods (unchanged from original) ============

    def _extract_and_parse_json(self, response_str, logger):
        """Multi-strategy JSON extraction"""
        if not response_str:
            return None

        try:
            return json.loads(response_str)
        except json.JSONDecodeError:
            pass

        json_match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', response_str, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass

        start = response_str.find('[') if response_str.find('[') != -1 and (response_str.find('{') == -1 or response_str.find('[') < response_str.find('{')) else response_str.find('{')

        if start == -1:
            return None

        opener = response_str[start]
        closer = ']' if opener == '[' else '}'

        balance = 1
        idx_end = -1
        in_string = False
        escape = False

        for i in range(start + 1, len(response_str)):
            char = response_str[i]

            if escape:
                escape = False
                continue

            if char == '\\':
                escape = True
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
            json_str = response_str[start:idx_end]
            json_str = re.sub(r'(,\s*})|(,\s*])', lambda m: m.group(0)[1:], json_str)

            try:
                return json.loads(json_str)
            except json.JSONDecodeError:
                pass

        return None

    def _validate_workplan(self, plan, logger, max_tasks, depth_limit=None, max_subtask_depth=None):
        """Validate workplan structure"""
        if not isinstance(plan, dict):
            return False

        if not all(k in plan for k in ["project_title", "context", "tasks"]):
            return False

        if not isinstance(plan["tasks"], list):
            return False

        if len(plan["tasks"]) > max_tasks:
            return False

        if depth_limit is not None:
            actual_depth = self._max_task_depth(plan.get("tasks", []))
            if actual_depth > depth_limit:
                if logger:
                    logger.log("WARNING", f"Plan depth {actual_depth} exceeds limit {depth_limit}")
                return False

        if max_subtask_depth is not None:
            actual_subtask_depth = self._max_subtask_depth(plan.get("tasks", []))
            if actual_subtask_depth > max_subtask_depth:
                if logger:
                    logger.log("WARNING", f"Subtask depth {actual_subtask_depth} exceeds limit {max_subtask_depth}")
                return False

        for i, task in enumerate(plan["tasks"]):
            if not self._validate_task_structure(task, f"tasks[{i}]", logger):
                return False

        return True

    def _validate_task_structure(self, task, path, logger):
        """Validate task structure"""
        if not isinstance(task, dict):
            return False

        required_fields = ["id", "title", "description"]
        if not all(f in task for f in required_fields):
            if logger:
                missing = [f for f in required_fields if f not in task]
                logger.log("WARNING", f"{path} missing: {missing}")
            return False

        if "subtasks" in task and not isinstance(task["subtasks"], list):
            return False

        for i, subtask in enumerate(task.get("subtasks", [])):
            if not self._validate_task_structure(subtask, f"{path}.subtasks[{i}]", logger):
                return False

        return True

    def _validate_actions(self, actions, task_id, logger=None):
        """Validate actions array"""
        if not isinstance(actions, list) or len(actions) == 0:
            return False

        for action in actions:
            if not isinstance(action, dict):
                return False

            if "instruction" not in action:
                return False

        return True

    def _max_task_depth(self, tasks, current_depth=1):
        """Compute max depth of task tree (top-level = 1)."""
        max_depth = current_depth
        for task in tasks or []:
            subtasks = task.get("subtasks", [])
            if subtasks:
                depth = self._max_task_depth(subtasks, current_depth + 1)
                if depth > max_depth:
                    max_depth = depth
        return max_depth

    def _max_subtask_depth(self, tasks):
        """Compute max subtask depth (depth beyond top-level)."""
        max_depth = 0
        for task in tasks or []:
            subtasks = task.get("subtasks", [])
            if subtasks:
                depth = self._max_task_depth(subtasks, 1)
                if depth > max_depth:
                    max_depth = depth
        return max_depth

    def _create_fallback_action(self, task):
        """Create fallback action"""
        task_id = task.get('id', 'UNKNOWN')

        return [{
            "action_id": f"{task_id}.a",
            "task_id": task_id,
            "instruction": task.get('description') or task.get('title', 'Complete this task'),
            "constraints": task.get('icom', {}).get('control', []),
            "expected_output_description": task.get('icom', {}).get('output', ["completed task"])[0] if task.get('icom', {}).get('output') else "completed task"
        }]

    def _contains_placeholder_tasks(self, plan: dict) -> bool:
        """Detect placeholder/stub tasks in a plan."""
        text = self._plan_text(plan).lower()
        patterns = [
            r'\bplaceholder\b',
            r'\bempty file\b',
            r'\bempty\b',
            r'\bstub\b',
            r'\btemplate\b',
            r'\btodo\b',
        ]
        return any(re.search(p, text) for p in patterns)

    def _plan_text(self, plan: dict) -> str:
        """Combine all task titles/descriptions into one text blob."""
        parts = []
        for task in plan.get("tasks", []):
            parts.append(task.get("title", ""))
            parts.append(task.get("description", ""))
            for sub in task.get("subtasks", []):
                parts.append(sub.get("title", ""))
                parts.append(sub.get("description", ""))
        return " ".join(parts)

    def _check_required_topics(self, plan: dict, project_context: str) -> List[str]:
        """Ensure plan includes topics explicitly mentioned in the prompt/context."""
        context_lower = (project_context or "").lower()
        plan_text = self._plan_text(plan).lower()

        required_map = {
            "ollama": "Ollama integration (LLM)",
            "receipt": "Receipt upload/parsing",
            "ocr": "OCR parsing",
            "recipe": "Recipe generation",
            "pantry": "Pantry CRUD",
            "meal history": "Meal history tracking",
            "preferences": "User preferences",
            "docker": "Docker setup",
            "docker-compose": "Docker Compose setup",
            "tests": "Tests (backend/integration)",
            "pytest": "Pytest coverage",
        }

        missing = []
        for token, label in required_map.items():
            if token in context_lower and token not in plan_text:
                missing.append(label)

        return missing
    def _flatten_tasks(self, tasks, parent_id=""):
        """Flatten task hierarchy"""
        flat_tasks = []

        for t in tasks:
            flat_tasks.append(t)
            if t.get("subtasks"):
                flat_tasks.extend(self._flatten_tasks(t["subtasks"], t.get("id", "")))

        return flat_tasks

    def create_plan(self, functional_prompt, technical_architecture, logger):
        """Main planning entry point"""
        project_title = "Software Development Project"

        project_context = f"""Functional Requirements:

{functional_prompt}

Technical Architecture:

{json.dumps(technical_architecture, ensure_ascii=False, indent=2)}

"""

        logger.log("INFO", "Generating SADT/SART hierarchical workplan...")

        workplan = self.generate_workplan(project_title, project_context, logger)

        if not workplan:
            logger.log("ERROR", "generate_workplan returned None")
            return [], ""

        if "tasks" not in workplan:
            logger.log("ERROR", f"Workplan missing 'tasks' key")
            return [], ""

        # Detect complexity to pass to action generator
        complexity = self._detect_project_complexity(project_context)
        logger.log("INFO", f"Using complexity level '{complexity}' for action generation")

        all_tasks = self._flatten_tasks(workplan.get("tasks", []))

        logger.log("INFO", f"Flattened {len(all_tasks)} tasks from hierarchy")

        final_plan_strings = []
        # Allow unlimited actions unless an explicit cap is set via environment variable.
        # Set SADT_MAX_ACTIONS to a positive integer to enforce a budget.
        max_total_actions = None
        max_actions_env = os.getenv("SADT_MAX_ACTIONS")
        if max_actions_env is not None:
            try:
                max_actions_value = int(max_actions_env)
                if max_actions_value > 0:
                    max_total_actions = max_actions_value
            except ValueError:
                if logger:
                    logger.log("WARNING", f"Invalid SADT_MAX_ACTIONS='{max_actions_env}', ignoring.")
        remaining_actions = max_total_actions

        for task in all_tasks:
            # Skip non-leaf tasks (those with subtasks)
            if task.get("subtasks") and len(task.get("subtasks")) > 0:
                continue
            if remaining_actions is not None and remaining_actions <= 0:
                logger.log("WARNING", f"Action budget exhausted ({max_total_actions}). Truncating plan.")
                break

            task_id = task.get('id', 'UNKNOWN')
            logger.log("DEBUG", f"Processing leaf task {task_id}")

            # Pass complexity to action generator
            actions = self.generate_atomic_actions_for_task(
                task,
                complexity=complexity,
                logger=logger,
                max_actions_override=remaining_actions
            )

            if not actions:
                logger.log("WARNING", f"No actions for {task_id}, using fallback")
                actions = self._create_fallback_action(task)

            for action in actions:
                if remaining_actions is not None and remaining_actions <= 0:
                    break
                instruction = action.get("instruction", "")
                constraints = action.get("constraints", [])
                output_desc = action.get("expected_output_description", "")
                action_id = action.get("action_id", f"{task_id}.a")

                task_str = f"[{action_id}] {instruction}"

                if constraints:
                    constraints_str = ", ".join(str(c) for c in constraints) if isinstance(constraints, list) else str(constraints)
                    if constraints_str.strip():
                        task_str += f" (Constraints: {constraints_str})"

                if output_desc and str(output_desc).strip():
                    task_str += f" (Output: {output_desc})"

                final_plan_strings.append(task_str)
                if remaining_actions is not None:
                    remaining_actions -= 1

        if max_total_actions is None:
            logger.log("INFO", f"✅ Generated {len(final_plan_strings)} atomic action items (no action budget limit)")
        else:
            logger.log("INFO", f"✅ Generated {len(final_plan_strings)} atomic action items (budget {max_total_actions})")

        run_command = self._extract_run_command(technical_architecture, logger)

        return final_plan_strings, run_command

    def _extract_run_command(self, technical_architecture, logger):
        """Extract run command"""
        if isinstance(technical_architecture, dict):
            run_cmd = technical_architecture.get("run_command")
            if run_cmd:
                if isinstance(run_cmd, str):
                    return run_cmd
                elif isinstance(run_cmd, dict):
                    commands = list(run_cmd.values())
                    if commands:
                        return commands[0]

        arch_str = str(technical_architecture).lower()

        if "fastapi" in arch_str or "uvicorn" in arch_str:
            return "uvicorn app.main:app --reload"
        elif "flask" in arch_str:
            return "python app.py"
        elif "django" in arch_str:
            return "python manage.py runserver"
        else:
            return "python app.py"

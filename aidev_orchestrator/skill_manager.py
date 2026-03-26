# skill_manager.py
"""
Intelligent skill management system for AI development agents.

Dynamically loads relevant skills based on task context, manages context window
usage, and provides skill summaries to avoid token bloat.
"""

import os
import json
import hashlib
from pathlib import Path
from typing import List, Dict, Optional, Set
import re


class SkillManager:
    """
    Manages skills (knowledge files) for AI agents.
    
    Features:
    - Dynamic skill detection based on task keywords
    - Context-aware loading (only load what's needed)
    - Skill summarization to reduce token usage
    - Caching for performance
    - Token budget management
    """
    
    def __init__(self, skills_directory: str = "./skills", cache_dir: str = "./skill_cache"):
        self.skills_dir = Path(skills_directory)
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(exist_ok=True)
        
        # Skill registry: maps skill names to their metadata
        self.skills: Dict[str, Dict] = {}
        
        # Keyword mappings: which keywords trigger which skills
        self.keyword_map: Dict[str, Set[str]] = {}
        
        # Load and index all skills
        self._scan_skills()
        
        print(f"📚 SkillManager initialized: {len(self.skills)} skills loaded")
    
    def _scan_skills(self):
        """Scan skills directory and build index."""
        if not self.skills_dir.exists():
            print(f"⚠️ Skills directory not found: {self.skills_dir}")
            return
        
        # Find all SKILL.md files
        skill_files = list(self.skills_dir.rglob("SKILL.md"))
        
        for skill_file in skill_files:
            self._index_skill(skill_file)
    
    def _index_skill(self, skill_file: Path):
        """Index a single skill file."""
        skill_name = skill_file.parent.name
        
        try:
            with open(skill_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Extract metadata from skill file
            metadata = self._extract_metadata(content)
            
            self.skills[skill_name] = {
                'path': str(skill_file),
                'name': skill_name,
                'content': content,
                'size': len(content),
                'keywords': metadata.get('keywords', []),
                'description': metadata.get('description', ''),
                'priority': metadata.get('priority', 50),
            }
            
            # Build keyword index
            for keyword in metadata.get('keywords', []):
                if keyword not in self.keyword_map:
                    self.keyword_map[keyword] = set()
                self.keyword_map[keyword].add(skill_name)
            
            print(f"  ✓ Indexed skill: {skill_name}")
            
        except Exception as e:
            print(f"  ⚠️ Failed to index {skill_file}: {e}")
    
    def _extract_metadata(self, content: str) -> Dict:
        """
        Extract metadata from skill file.
        
        Expected format at the top of SKILL.md:
        ```
        # Skill Name
        
        ## Metadata
        - Keywords: web, frontend, react, component, styling
        - Description: Guide for creating web components
        - Priority: 80 (0-100, higher = more important)
        ```
        """
        metadata = {
            'keywords': [],
            'description': '',
            'priority': 50
        }
        
        # Extract keywords
        keywords_match = re.search(r'Keywords?:\s*(.+)', content, re.IGNORECASE)
        if keywords_match:
            keywords_text = keywords_match.group(1)
            metadata['keywords'] = [k.strip().lower() for k in keywords_text.split(',')]
        
        # Extract description
        desc_match = re.search(r'Description:\s*(.+)', content, re.IGNORECASE)
        if desc_match:
            metadata['description'] = desc_match.group(1).strip()
        
        # Extract priority
        priority_match = re.search(r'Priority:\s*(\d+)', content, re.IGNORECASE)
        if priority_match:
            metadata['priority'] = int(priority_match.group(1))
        
        # Auto-detect keywords from content if none specified
        if not metadata['keywords']:
            metadata['keywords'] = self._auto_detect_keywords(content)
        
        return metadata
    
    def _auto_detect_keywords(self, content: str) -> List[str]:
        """Auto-detect keywords from skill content."""
        content_lower = content.lower()
        
        # Common keyword patterns
        keyword_patterns = {
            'react': ['react', 'jsx', 'component', 'useState', 'useEffect'],
            'frontend': ['frontend', 'ui', 'web', 'html', 'css'],
            'backend': ['backend', 'api', 'endpoint', 'database', 'flask'],
            'styling': ['css', 'styling', 'design', 'responsive'],
            'database': ['database', 'sql', 'query', 'model', 'schema'],
            'testing': ['test', 'testing', 'unittest', 'pytest'],
            'production': ['production', 'deployment', 'ready', 'complete'],
        }
        
        detected = []
        for category, patterns in keyword_patterns.items():
            if any(pattern in content_lower for pattern in patterns):
                detected.append(category)
        
        return detected
    
    def detect_relevant_skills(self, context: str, max_skills: int = 3) -> List[str]:
        """
        Detect which skills are relevant for the given context.
        
        Args:
            context: Task description or context to analyze
            max_skills: Maximum number of skills to return
            
        Returns:
            List of skill names, sorted by relevance
        """
        context_lower = context.lower()
        
        # Score each skill based on keyword matches
        scores = {}
        
        for skill_name, skill_data in self.skills.items():
            score = 0
            
            # Keyword matches
            for keyword in skill_data['keywords']:
                if keyword in context_lower:
                    score += 10
            
            # Exact name match
            if skill_name.lower() in context_lower:
                score += 20
            
            # Priority boost
            score += skill_data['priority'] / 10
            
            if score > 0:
                scores[skill_name] = score
        
        # Sort by score and return top N
        sorted_skills = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        return [skill_name for skill_name, _ in sorted_skills[:max_skills]]
    
    def get_skill_content(self, skill_name: str, summarize: bool = False, 
                         max_tokens: int = 2000) -> Optional[str]:
        """
        Get the content of a skill.
        
        Args:
            skill_name: Name of the skill
            summarize: If True, return a summary instead of full content
            max_tokens: Maximum tokens for summary (rough estimate: 4 chars = 1 token)
            
        Returns:
            Skill content or summary
        """
        if skill_name not in self.skills:
            return None
        
        skill_data = self.skills[skill_name]
        content = skill_data['content']
        
        if not summarize:
            return content
        
        # Check cache first
        cache_key = f"{skill_name}_{max_tokens}"
        cached_summary = self._get_cached_summary(cache_key)
        if cached_summary:
            return cached_summary
        
        # Generate summary
        summary = self._summarize_skill(content, max_tokens)
        
        # Cache it
        self._cache_summary(cache_key, summary)
        
        return summary
    
    def _summarize_skill(self, content: str, max_tokens: int) -> str:
        """
        Summarize skill content to fit within token budget.
        
        Strategy:
        1. Extract key sections (rules, examples, checklists)
        2. Keep section headers
        3. Truncate long examples
        4. Preserve critical information
        """
        max_chars = max_tokens * 4  # Rough estimate
        
        if len(content) <= max_chars:
            return content
        
        # Extract key sections
        sections = {
            'rules': [],
            'examples': [],
            'checklists': [],
            'requirements': []
        }
        
        lines = content.split('\n')
        current_section = None
        
        for line in lines:
            line_lower = line.lower()
            
            # Detect section type
            if any(word in line_lower for word in ['rule', 'critical', 'required', 'must']):
                current_section = 'rules'
            elif any(word in line_lower for word in ['example', '```']):
                current_section = 'examples'
            elif any(word in line_lower for word in ['checklist', '- [ ]', '☐']):
                current_section = 'checklists'
            elif 'requirement' in line_lower:
                current_section = 'requirements'
            
            # Add to section
            if current_section and line.strip():
                sections[current_section].append(line)
        
        # Build summary prioritizing critical info
        summary_parts = [
            "# SKILL SUMMARY (Auto-generated)\n",
            "\n## Critical Rules\n",
            '\n'.join(sections['rules'][:20]),  # Top 20 rules
            "\n\n## Requirements\n",
            '\n'.join(sections['requirements'][:15]),
            "\n\n## Checklists\n",
            '\n'.join(sections['checklists'][:10]),
            "\n\n## Example Patterns\n",
            '\n'.join(sections['examples'][:5]),  # Just a few examples
            "\n\n[Full skill available if needed]"
        ]
        
        summary = '\n'.join(summary_parts)
        
        # Final truncation if still too long
        if len(summary) > max_chars:
            summary = summary[:max_chars] + "\n\n[Truncated - request full skill if needed]"
        
        return summary
    
    def _get_cached_summary(self, cache_key: str) -> Optional[str]:
        """Get cached summary."""
        cache_file = self.cache_dir / f"{cache_key}.md"
        if cache_file.exists():
            try:
                with open(cache_file, 'r', encoding='utf-8') as f:
                    return f.read()
            except:
                pass
        return None
    
    def _cache_summary(self, cache_key: str, summary: str):
        """Cache a summary."""
        cache_file = self.cache_dir / f"{cache_key}.md"
        try:
            with open(cache_file, 'w', encoding='utf-8') as f:
                f.write(summary)
        except Exception as e:
            print(f"⚠️ Failed to cache summary: {e}")
    
    def get_skills_for_task(self, task_description: str, 
                           token_budget: int = 4000) -> str:
        """
        Get relevant skills for a task, formatted and ready to inject into prompt.
        
        Args:
            task_description: Description of the task
            token_budget: Maximum tokens to use for skills
            
        Returns:
            Formatted string with relevant skills
        """
        # Detect relevant skills
        relevant_skills = self.detect_relevant_skills(task_description, max_skills=5)
        
        if not relevant_skills:
            return ""
        
        # Calculate budget per skill
        budget_per_skill = token_budget // len(relevant_skills)
        
        # Gather skills
        skill_contents = []
        
        for skill_name in relevant_skills:
            skill_data = self.skills[skill_name]
            
            # Decide whether to summarize
            skill_size = skill_data['size']
            should_summarize = skill_size > (budget_per_skill * 4)
            
            content = self.get_skill_content(
                skill_name, 
                summarize=should_summarize,
                max_tokens=budget_per_skill
            )
            
            if content:
                skill_contents.append(f"""
{'=' * 80}
SKILL: {skill_name.upper()}
{'=' * 80}

{content}
""")
        
        if not skill_contents:
            return ""
        
        # Format for injection
        formatted = f"""
{'=' * 80}
RELEVANT SKILLS LOADED
{'=' * 80}

The following skills have been loaded to help you complete this task.
Review them carefully before proceeding.

{''.join(skill_contents)}

{'=' * 80}
END OF SKILLS
{'=' * 80}
"""
        
        return formatted
    
    def list_available_skills(self) -> List[Dict]:
        """List all available skills with metadata."""
        return [
            {
                'name': name,
                'description': data['description'],
                'keywords': data['keywords'],
                'size': data['size'],
                'priority': data['priority']
            }
            for name, data in self.skills.items()
        ]


# Integration with agents

def inject_skills_into_system_message(base_system_message: str, 
                                     task_description: str,
                                     skill_manager: SkillManager,
                                     token_budget: int = 4000) -> str:
    """
    Helper function to inject skills into agent system message.
    
    Usage in agent:
    ```python
    system_message = inject_skills_into_system_message(
        base_system_message=self.base_system_message,
        task_description=task_description,
        skill_manager=self.skill_manager,
        token_budget=4000
    )
    ```
    """
    skills_content = skill_manager.get_skills_for_task(task_description, token_budget)
    
    if skills_content:
        return f"{base_system_message}\n\n{skills_content}"
    else:
        return base_system_message


# Example usage

if __name__ == "__main__":
    # Initialize skill manager
    skill_manager = SkillManager(skills_directory="./skills")
    
    # Example 1: Detect skills for a frontend task
    print("\n=== Example 1: Frontend Task ===")
    task1 = "Create a React component for managing pantry items with styled UI"
    skills1 = skill_manager.detect_relevant_skills(task1)
    print(f"Task: {task1}")
    print(f"Relevant skills: {skills1}")
    
    # Example 2: Get formatted skills for injection
    print("\n=== Example 2: Get Formatted Skills ===")
    formatted = skill_manager.get_skills_for_task(task1, token_budget=3000)
    print(f"Formatted output length: {len(formatted)} chars")
    print(f"Preview:\n{formatted[:500]}...")
    
    # Example 3: List all available skills
    print("\n=== Example 3: Available Skills ===")
    all_skills = skill_manager.list_available_skills()
    for skill in all_skills:
        print(f"  - {skill['name']}: {skill['description']}")
        print(f"    Keywords: {', '.join(skill['keywords'])}")
        print(f"    Size: {skill['size']} chars, Priority: {skill['priority']}")

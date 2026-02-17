# Quick Reference Guide - Orchestrator Improvements

## What's New?

### 🔄 Feedback Loop System
**What it does**: Reviewer and tester feedback now informs subsequent development attempts.

**How it works**:
```
Task Attempt 1:
  Developer → Code Review → Issues Found
  
Task Attempt 2:
  Developer (with review feedback) → Better Code → Code Review → Tests → Test Fails
  
Task Attempt 3:
  Developer (with review + test feedback) → Fixed Code → All Pass ✅
```

**Benefits**:
- Agents learn from mistakes
- Faster convergence to working code
- Less manual intervention needed

---

### 🏗️ Architecture Compliance Validation
**What it does**: Automatically checks if code follows the technical architecture.

**Supported Patterns**:
- **Layered Architecture** - Validates layer separation
- **Microservices** - Checks service boundaries  
- **MVC** - Ensures proper file organization

**Example Output**:
```
⚠️ Architecture violations detected:
  - ui/dashboard.py: Presentation layer importing from data layer (models.user)
  - user_service.py: Service file not in services/ directory
```

**What happens on violation**:
- Task is marked for retry
- Violations added to feedback
- Developer receives specific fix instructions

---

### 💾 Task Checkpointing
**What it does**: Saves progress after each step, enables recovery from failures.

**Checkpoint Locations**:
- `projects/<project_name>/checkpoints.json`
- Updated after each task phase
- Persists across program restarts

**Task Lifecycle**:
```
PENDING → IN_PROGRESS → DEVELOPED → REVIEWED → TESTED → 
  ARCHITECTURE_VALIDATED → COMPLETED
  
Any phase can fail and retry with feedback
```

**Recovery Example**:
```bash
# Program crashes during task 5
$ python orchestrator.py my_project

Output:
🔄 Resuming task 5 from checkpoint (attempt 2)
✅ Using feedback from previous attempt
```

---

## Common Scenarios

### Scenario 1: Code Review Finds Issues
```
1. Developer writes code
2. Code review finds critical bug
3. Task status → DEVELOPED (needs retry)
4. Checkpoint saves review feedback
5. Next attempt: Developer gets feedback in prompt
6. Developer fixes issue based on feedback
7. Review passes → Continue
```

### Scenario 2: Tests Fail
```
1. Code passes review
2. Tests run → 3 tests fail
3. Task status → DEVELOPED (needs retry)
4. Test failure details saved to checkpoint
5. Next attempt: Developer sees test output
6. Developer debugs and fixes
7. Tests pass → Continue
```

### Scenario 3: Architecture Violation
```
1. Developer creates ui/user_view.py
2. File imports from data.repositories directly
3. Architecture validation → VIOLATION
4. Task status → DEVELOPED (needs retry)
5. Violation: "Presentation layer importing from data layer"
6. Next attempt: Developer uses service layer instead
7. Validation passes → Continue
```

### Scenario 4: Max Retries Exceeded
```
1. Task attempts: 1, 2, 3 (all fail)
2. retry_count reaches max_retry_attempts (3)
3. Program halts with error:
   "Task 5 exceeded max retries. Halting."
4. Manual intervention required
5. Fix the issue manually or adjust requirements
6. Resume with: python orchestrator.py my_project
```

---

## Configuration Options

### Retry Limit
```python
# In __init__:
self.max_retry_attempts = 3  # Change this value
```

### Enable/Disable Testing
```bash
# Enable tests (includes validation)
python orchestrator.py my_project --with-tests

# Disable tests (faster, less validation)
python orchestrator.py my_project
```

### Architecture Validation
- **Automatic**: Enabled for all projects
- **Based on**: Content of `technical_architecture` variable
- **Customizable**: Add new checks in `_check_*` methods

---

## Debugging Failed Tasks

### View Checkpoint Data
```python
import json

with open('projects/my_project/checkpoints.json', 'r') as f:
    data = json.load(f)
    
# Find failed task
for task_id, checkpoint in data.items():
    if checkpoint['status'] == 'failed':
        print(f"Task {task_id}: {checkpoint['task_description']}")
        print(f"Attempts: {checkpoint['retry_count']}")
        print(f"Review: {checkpoint['review_feedback']}")
        print(f"Tests: {checkpoint['test_results']}")
```

### Manual Recovery
```bash
# 1. Fix the issue manually in the workspace
cd projects/my_project/workspace
# ... make your fixes ...

# 2. Update checkpoint to mark as completed
# Edit checkpoints.json, change status to "completed"

# 3. Resume orchestrator
python orchestrator.py my_project
```

### Force Restart Specific Task
```bash
# 1. Edit state.json
# Set "last_completed_task_index" to task before the one you want to redo

# 2. Delete checkpoint for that task
# Edit checkpoints.json, remove the task entry

# 3. Restart
python orchestrator.py my_project
```

---

## Performance Tips

### Large Projects
- Checkpoints grow with project size
- Consider periodic cleanup of old checkpoints
- RAG index rebuilds on each task (can be slow)

### Optimization Ideas
```python
# Reduce RAG index updates
self._update_index_incrementally()  # Only when needed

# Limit checkpoint retention
# Keep only last N checkpoints

# Disable architecture checks for specific tasks
# Add flag to skip validation for non-critical tasks
```

---

## Error Messages Explained

### "Task X exceeded max retries"
**Meaning**: Task failed 3 times  
**Solution**: Check checkpoint for details, fix manually, or adjust requirements

### "Architecture violations detected"
**Meaning**: Code doesn't follow architecture pattern  
**Solution**: Review violation details, refactor code to match architecture

### "Git commit failed"
**Meaning**: Git operation failed  
**Solution**: Check workspace directory, ensure git is initialized, check permissions

### "Development failed for task X"
**Meaning**: Developer agent couldn't complete task  
**Solution**: Review task complexity, check if requirements are clear, try with simpler task

---

## Best Practices

### 1. Clear Architecture Definition
```markdown
# Good Architecture Description
"Use a 3-tier layered architecture:
- Presentation: UI and API controllers (no direct DB access)
- Business: Services and domain logic
- Data: Repositories and models"

# Bad Architecture Description  
"Make it clean and organized"
```

### 2. Incremental Requirements
- Start with simple tasks
- Build complexity gradually
- Each task should be independently testable

### 3. Monitor Checkpoints
- Review checkpoint file periodically
- Identify patterns in failures
- Adjust approach based on retry counts

### 4. Use Feedback
- Don't just retry blindly
- Review feedback between attempts
- Adjust requirements if same issue repeats

---

## Quick Commands

```bash
# Start new project with all features
python orchestrator.py my_app --prompt req.txt --new --with-tests

# Resume existing project
python orchestrator.py my_app

# Force restart (ignore checkpoints)
python orchestrator.py my_app --new

# View project state
cat projects/my_app/state.json

# View checkpoints
cat projects/my_app/checkpoints.json | jq '.'

# View architecture
cat projects/my_app/architecture.md

# View requirements
cat projects/my_app/requirements.md
```

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| Infinite retry loop | Check max_retry_attempts, review feedback |
| Architecture checks too strict | Customize validation in _check_* methods |
| Checkpoints too large | Implement checkpoint cleanup |
| RAG index slow | Reduce similarity_top_k or update less frequently |
| Git conflicts | Ensure workspace is clean before starting |
| Agent timeout | Increase timeout in agent configuration |

---

## Contact & Support

For issues or questions:
1. Check IMPROVEMENTS.md for detailed documentation
2. Review checkpoint data for failure details
3. Enable debug logging in config.py
4. Check agent logs in project directory

---

**Version**: 2.0  
**Last Updated**: 2026-01-24  
**Compatibility**: Python 3.8+

"""
Fixed DeveloperAgent with:
- Loop detection (stops trying same failed tool)
- Simpler prompts (gemma3:4b can't handle 200+ lines)
- Better error understanding
- Explicit fallback strategies
"""
import asyncio
import traceback
import time
import re
from typing import List, Dict, Optional, Tuple
from collections import defaultdict, deque
from .base_agent import BaseAgent
from skill_manager import inject_skills_into_system_message
from llama_index.core.tools import FunctionTool
from llama_index.core.agent import ReActAgent
from llama_index.core.workflow import Context, StopEvent
from llama_index.core.agent.workflow import AgentStream, ToolCallResult, AgentOutput


class DeveloperAgent(BaseAgent):
    def __init__(self, llm_class, llm_args, orchestrator_tools, logger, skill_manager=None):
        super().__init__(llm_class, llm_args, temperature=0.1, agent_name="DeveloperAgent")
        
        self.logger = logger
        self.streaming = True
        self.orchestrator_tools = orchestrator_tools
        self.skill_manager = skill_manager
        
        tools = [
            FunctionTool.from_defaults(
                fn=orchestrator_tools.add_code_block,
                name="add_code_block",
                description="Add a code block at a semantic location. Use AST for placement."
            ),
            FunctionTool.from_defaults(
                fn=orchestrator_tools.write_file,
                name="write_file",
                description="Create a NEW file. ONLY for files that don't exist yet!"
            ),
            FunctionTool.from_defaults(
                fn=orchestrator_tools.delete_code_block,
                name="delete_code_block",
                description="Delete a code block by name."
            ),
            FunctionTool.from_defaults(
                fn=orchestrator_tools.read_file,
                name="read_file",
                description="Read an existing file."
            ),
            FunctionTool.from_defaults(
                fn=orchestrator_tools.insert_text,
                name="insert_text",
                description="Add text to an existing file."
            ),
            FunctionTool.from_defaults(
                fn=orchestrator_tools.replace_text,
                name="replace_text",
                description="Replace text in an existing file."
            ),
            FunctionTool.from_defaults(
                fn=orchestrator_tools.list_files,
                name="list_files",
                description="See all files in project."
            ),
            FunctionTool.from_defaults(
                fn=orchestrator_tools.delete_file,
                name="delete_file",
                description="Delete a file (PERMANENT)."
            ),
            FunctionTool.from_defaults(
                fn=orchestrator_tools.create_directory,
                name="create_directory",
                description="Create a new directory."
            ),
            FunctionTool.from_defaults(
                fn=orchestrator_tools.directory_exists,
                name="directory_exists",
                description="Check if a directory is present."
            ),
            FunctionTool.from_defaults(
                fn=orchestrator_tools.get_code_summary,
                name="get_code_summary",
                description="Get structure of a file (classes, functions)."
            ),
            FunctionTool.from_defaults(
                fn=orchestrator_tools.refactor_rename_symbol,
                name="refactor_rename_symbol",
                description="Safely rename a symbol using AST."
            ),
        ]
        
        self.available_tool_names = {tool.metadata.name for tool in tools}
        
        # MUCH SIMPLER system message for weak LLMs
        self.base_system_message = """You are an expert software developer. You write code by creating and modifying files.

YOUR ONLY TOOLS:
- write_file: Create NEW files (not for existing files!)
- read_file: Read files
- insert_text: Add to existing files
- replace_text: Change text in existing files
- list_files: See what files exist
- delete_file: Remove files
- create_directory: Make new directories
- directory_exists: Check if a directory exists
- get_code_summary: Get structure of a file (classes, functions)
- add_code_block: Add a code block at a semantic location using AST
- delete_code_block: Delete a code block by name
- refactor_rename_symbol: Safely rename a symbol using AST

THESE TOOLS DON'T EXIST (DON'T TRY THEM):
- Answer (just finish your thought)
- modify_file (use insert_text or replace_text instead)
- Any other tools

CRITICAL RULES:
1. Create files WITH CONTENT in one step
   Good: write_file("app.py", "print('hello')")
   Bad: write_file("app.py", "") then insert_text(...)

2. NEVER use write_file on existing files
   If file exists: use insert_text or replace_text

3. When stuck, try a DIFFERENT tool
   If insert_text fails 2 times, try replace_text instead

4. File paths: Simple names only
   Good: "app.py" or "src/main.py"  
   Bad: "./app.py" or "projects/test/app.py"

5. When done with tools, just finish your thought
   Don't try to call "Answer" tool - it doesn't exist

EXAMPLE:
Task: Create hello.py that prints "Hello"

Thought: I need to create a new Python file
Action: write_file
Action Input: {"filename": "hello.py", "content": "print('Hello')"}
Observation: File created successfully
Thought: Done! File created with the print statement.
"""
        self.enhanced_system_message = EHANCED_DEVELOPER_SYSTEM_MESSAGE
        self.system_message = self.base_system_message + "\n\n" + self.enhanced_system_message


        self.agent = ReActAgent(
            llm=self.llm,
            tools=tools,
            system_prompt=self.system_message,
            verbose=True,
            max_iterations=20,  # Reduced from 30
            streaming=self.streaming
        )
    
    async def run(
        self,
        task: str,
        retry_context: Optional[str] = None,
        system_prompt: Optional[str] = None
    ) -> Tuple[bool, Optional[str], List[Dict]]:
        """Execute development task with loop detection"""
        
        if self.logger:
            self.logger.log("INFO", f"DeveloperAgent starting: {task[:100]}")
        
        full_prompt = task
        allow_skill_injection = True
        if system_prompt is not None:
            self.agent.system_prompt = system_prompt
            allow_skill_injection = False
        else:
            self.agent.system_prompt = self.system_message

        if self.skill_manager and allow_skill_injection:
            improved_system_message = inject_skills_into_system_message(
                self.system_message,
                task,
                self.skill_manager,
                token_budget=32000
            )
            self.agent.system_prompt = improved_system_message

        
        if retry_context:
            full_prompt = f"""PREVIOUS ATTEMPT HAD ISSUES:
{retry_context}

NOW TRY AGAIN:
{task}

Fix the issues mentioned above."""
        
        ctx = Context(self.agent)
        handler = self.agent.run(full_prompt, ctx=ctx)
        
        tool_calls = []
        final_answer_str = ""
        files_created = set()
        files_modified = set()
        run_start = time.monotonic()
        stream_event_count = 0

        # Loop detection
        tool_failure_counts = defaultdict(int)
        last_tool_name = None
        consecutive_same_tool = 0
        invalid_tool_calls = 0
        # Detect repeated text-mode pseudo tool calls (no real ToolCallResult events)
        recent_action_chunks = deque(maxlen=12)
        repeated_action_streak = 0
        action_signature_streak = 0
        last_action_signature = None
        stream_buffer = ""
        no_tool_call_timeout_seconds = 45
        no_tool_call_max_stream_events = 140
        
        if self.streaming:
            try:
                async for ev in handler.stream_events():
                    if isinstance(ev, ToolCallResult):
                        tool_name = ev.tool_name
                        tool_kwargs = ev.tool_kwargs
                        tool_output = ev.tool_output
                        
                        # Validate tool exists
                        if tool_name not in self.available_tool_names:
                            print(f"\n⛔ ERROR: Tool '{tool_name}' DOES NOT EXIST!")
                            print(f"Available tools: {', '.join(sorted(self.available_tool_names))}")
                            print("This tool will not be executed. Try a different approach.")
                            tool_failure_counts[tool_name] += 1
                            invalid_tool_calls += 1
                            if invalid_tool_calls >= 3:
                                print("\nðŸ›‘ CIRCUIT BREAKER: Too many invalid tool calls")
                                return False, "Agent tried invalid tools repeatedly", tool_calls
                            continue
                        
                        # Loop detection
                        if tool_name == last_tool_name:
                            consecutive_same_tool += 1
                        else:
                            consecutive_same_tool = 1
                            last_tool_name = tool_name
                        
                        # Circuit breaker: If same tool fails 3 times in a row, stop
                        output_str = str(tool_output.content) if hasattr(tool_output, 'content') else str(tool_output)
                        is_error = ("error" in output_str.lower() or 
                                   "fail" in output_str.lower() or 
                                   "rejected" in output_str.lower() or
                                   "success" in output_str.lower() and "false" in output_str.lower())
                        
                        if is_error:
                            tool_failure_counts[tool_name] += 1
                            
                            if consecutive_same_tool >= 3:
                                print(f"\n🛑 CIRCUIT BREAKER: Same tool '{tool_name}' failed {consecutive_same_tool} times in a row")
                                print(f"Stopping to prevent infinite loop. Last error: {output_str[:200]}")
                                return False, f"Agent stuck in loop trying '{tool_name}' repeatedly", tool_calls
                        
                        print(f"\n[Developer] 🔧 {tool_name}({tool_kwargs})")
                        print(f"[Developer] ↪ {output_str[:150]}...")
                        
                        # Track file operations
                        if tool_name == "write_file" and "success" in output_str.lower() and "true" in output_str.lower():
                            filename = tool_kwargs.get('filename', '')
                            if filename:
                                files_created.add(filename)
                        
                        elif tool_name in ["insert_text", "replace_text"]:
                            if "success" in output_str.lower() and "true" in output_str.lower():
                                filename = tool_kwargs.get('filename', '')
                                if filename:
                                    files_modified.add(filename)
                        
                        tool_calls.append({
                            "tool_name": tool_name,
                            "tool_args": tool_kwargs
                        })
                    
                    elif isinstance(ev, StopEvent):
                        print("\n[Developer] 🛑 Complete")
                        break
                    
                    elif isinstance(ev, AgentOutput):
                        final_answer_str = str(ev.response)
                    
                    elif isinstance(ev, AgentStream):
                        delta = str(ev.delta or "")
                        print(f"{delta}", end="", flush=True)
                        stream_event_count += 1
                        if delta:
                            stream_buffer += delta
                            if len(stream_buffer) > 12000:
                                stream_buffer = stream_buffer[-12000:]

                        # Heuristic: repeated "Action: ..." text without real tool calls indicates stuck formatting loop.
                        normalized = re.sub(r"\s+", " ", delta).strip().lower()
                        if normalized and ("action:" in normalized or "action input:" in normalized):
                            recent_action_chunks.append(normalized[:240])
                            if len(recent_action_chunks) >= 2 and recent_action_chunks[-1] == recent_action_chunks[-2]:
                                repeated_action_streak += 1
                            else:
                                repeated_action_streak = 0
                            if len(tool_calls) == 0 and repeated_action_streak >= 6:
                                print("\n🛑 CIRCUIT BREAKER: Repeated text-mode Action loop without real tool calls.")
                                return False, "Agent stuck repeating Action text without invoking tools", tool_calls

                        # Stronger loop detection: repeated Action + Action Input signature in streamed text
                        action_matches = re.findall(
                            r"Action:\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*(?:\n|\r\n?)\s*Action Input:\s*(\{[\s\S]*?\})",
                            stream_buffer,
                            flags=re.IGNORECASE
                        )
                        if action_matches and len(tool_calls) == 0:
                            action_name, action_payload = action_matches[-1]
                            payload_norm = re.sub(r"\s+", " ", action_payload).strip().lower()[:500]
                            signature = f"{action_name.lower()}|{payload_norm}"
                            if signature == last_action_signature:
                                action_signature_streak += 1
                            else:
                                last_action_signature = signature
                                action_signature_streak = 1
                            if action_signature_streak >= 5:
                                print("\n[Developer] CIRCUIT BREAKER: Repeated Action signature without any tool execution.")
                                return False, "Agent repeating identical Action/Action Input without invoking tools", tool_calls

                        if len(tool_calls) == 0:
                            elapsed = time.monotonic() - run_start
                            if elapsed > no_tool_call_timeout_seconds or stream_event_count > no_tool_call_max_stream_events:
                                print("\n🛑 CIRCUIT BREAKER: No tool calls executed within safety window.")
                                return False, "No tool calls executed (timeout/iteration guard)", tool_calls
                
                print(f"\n[Developer] ✅ Used {len(tool_calls)} tools")
                
                # Basic file verification
                if files_created:
                    print(f"[Developer] 📁 Created: {', '.join(files_created)}")
                if files_modified:
                    print(f"[Developer] 📝 Modified: {', '.join(files_modified)}")
            
            except asyncio.TimeoutError:
                print("\n❌ Timeout")
                return False, None, tool_calls
            
            except Exception as e:
                print(f"\n❌ Error: {type(e).__name__}: {e}")
                traceback.print_exc()
                return False, None, tool_calls
        
        if not self.streaming:
            # Non-streaming fallback path
            try:
                result = await handler
                if isinstance(result, AgentOutput):
                    final_answer_str = str(result.response)
                return True, final_answer_str, tool_calls
            except Exception as e:
                print(f"\nâŒ Error (non-streaming): {type(e).__name__}: {e}")
                traceback.print_exc()
                return False, None, tool_calls

        return True, final_answer_str, tool_calls
    
    async def chat(self, message: str) -> str:
        """Handle consultation"""
        chat_system_message = """You are a developer. Answer questions directly and helpfully."""
        
        chat_agent = ReActAgent(
            llm=self.llm,
            tools=self.agent.tools,
            system_prompt=chat_system_message,
            verbose=False,
            streaming=True
        )
        
        ctx = Context(chat_agent)
        handler = chat_agent.run(message, ctx=ctx)
        
        final_answer_str = ""
        
        try:
            async for ev in handler.stream_events():
                if isinstance(ev, AgentOutput):
                    final_answer_str = str(ev.response)
            
            return final_answer_str
        
        except Exception as e:
            return f"Error: {str(e)}"



EHANCED_DEVELOPER_SYSTEM_MESSAGE = """
You are an expert software developer creating PRODUCTION-READY, FULLY FUNCTIONAL code.

═══════════════════════════════════════════════════════════════
CRITICAL: ZERO TOLERANCE FOR PLACEHOLDER CODE
═══════════════════════════════════════════════════════════════

❌ NEVER create code like this:
```javascript
const handleClick = () => {
  console.log('Clicked');  // ← FORBIDDEN
  // TODO: Implement API call  // ← FORBIDDEN
};

<div>  // ← FORBIDDEN (no styling)
  <button>Click</button>
</div>

const items = [  // ← FORBIDDEN (fake data)
  { id: 1, name: 'Sample Item' }
];
```

✅ ALWAYS create code like this:
```javascript
const handleClick = async () => {
  setLoading(true);
  try {
    const response = await api.post('/items', data);
    setItems([...items, response.data]);
    toast.success('Item added!');
  } catch (error) {
    toast.error('Failed to add item');
  } finally {
    setLoading(false);
  }
};

<div className="items-container">  // ← STYLED
  <button onClick={handleClick} className="btn-primary">
    {loading ? 'Adding...' : 'Add Item'}
  </button>
</div>

// Real data from API
useEffect(() => {
  const fetchItems = async () => {
    const data = await api.get('/items');
    setItems(data);
  };
  fetchItems();
}, []);
```

═══════════════════════════════════════════════════════════════
MANDATORY REQUIREMENTS FOR EVERY FILE
═══════════════════════════════════════════════════════════════

### Frontend Components (React/JS):

1. **API Integration (REQUIRED)**
```javascript
   import * as api from './api';  // Always import
   
   // Always use real API calls
   const response = await api.post('/endpoint', data);
   const data = await api.get('/endpoint');
   const updated = await api.put('/endpoint/:id', data);
   await api.del('/endpoint/:id');
```

2. **State Management (REQUIRED)**
```javascript
   const [data, setData] = useState([]);
   const [loading, setLoading] = useState(false);
   const [error, setError] = useState(null);
```

3. **Complete CRUD Operations (REQUIRED)**
```javascript
   // Create
   const create = async (item) => {
     try {
       const result = await api.post('/items', item);
       setData([...data, result]);
       toast.success('Created!');
     } catch (err) {
       toast.error(err.message);
     }
   };
   
   // Read
   useEffect(() => {
     const fetch = async () => {
       const result = await api.get('/items');
       setData(result);
     };
     fetch();
   }, []);
   
   // Update
   const update = async (id, updates) => {
     const result = await api.put(`/items/${id}`, updates);
     setData(data.map(item => item.id === id ? result : item));
   };
   
   // Delete
   const remove = async (id) => {
     await api.del(`/items/${id}`);
     setData(data.filter(item => item.id !== id));
   };
```

4. **Styling (REQUIRED)**
```javascript
   // Always import CSS
   import './ComponentName.css';
   
   // Always use CSS classes
   <div className="component-container">
     <h1 className="component-title">Title</h1>
     <button className="btn-primary">Action</button>
   </div>
```

5. **Error Handling (REQUIRED)**
```javascript
   try {
     // Operation
   } catch (error) {
     toast.error(error.response?.data?.message || 'Operation failed');
     console.error(error);
   }
```

6. **Loading States (REQUIRED)**
```javascript
   {loading ? (
     <div className="loading-spinner">
       <Spinner />
     </div>
   ) : (
     // Actual content
   )}
```

7. **Empty States (REQUIRED)**
```javascript
   {data.length === 0 && !loading && (
     <div className="empty-state">
       <p>No items yet</p>
       <button onClick={handleAdd}>Add First Item</button>
     </div>
   )}
```

### Backend APIs (Python/Flask):

1. **Database Operations (REQUIRED)**
```python
   # ALWAYS interact with real database
   
   # Create
   @app.route('/items', methods=['POST'])
   def create_item():
       data = request.json
       item = Item(**data)
       db.session.add(item)
       db.session.commit()
       return item.to_dict(), 201
   
   # Read
   @app.route('/items', methods=['GET'])
   def get_items():
       items = Item.query.all()
       return [item.to_dict() for item in items], 200
   
   # Update
   @app.route('/items/<id>', methods=['PUT'])
   def update_item(id):
       item = Item.query.get_or_404(id)
       data = request.json
       for key, value in data.items():
           setattr(item, key, value)
       db.session.commit()
       return item.to_dict(), 200
   
   # Delete
   @app.route('/items/<id>', methods=['DELETE'])
   def delete_item(id):
       item = Item.query.get_or_404(id)
       db.session.delete(item)
       db.session.commit()
       return {'message': 'Deleted'}, 200
```

2. **Error Handling (REQUIRED)**
```python
   try:
       # Operation
       db.session.commit()
       return result, 201
   except IntegrityError:
       db.session.rollback()
       return {'error': 'Duplicate entry'}, 409
   except Exception as e:
       db.session.rollback()
       return {'error': str(e)}, 500
```

3. **Validation (REQUIRED)**
```python
   if not data.get('name'):
       return {'error': 'Name is required'}, 400
   
   if data.get('quantity', 0) <= 0:
       return {'error': 'Quantity must be positive'}, 400
```

4. **Security (REQUIRED)**
```python
   # Use parameterized queries (SQLAlchemy does this)
   item = Item.query.filter_by(id=id).first()  # ✅ Safe
   
   # NEVER use string formatting
   # cursor.execute(f"SELECT * FROM items WHERE id={id}")  # ❌ SQL injection!
```

### CSS Styling (REQUIRED for ALL components):

1. **Create Separate CSS File**
```css
   /* ComponentName.css */
   
   .component-container {
     max-width: 1200px;
     margin: 0 auto;
     padding: 2rem;
     background: #ffffff;
     border-radius: 8px;
     box-shadow: 0 2px 4px rgba(0,0,0,0.1);
   }
   
   .component-title {
     font-size: 2rem;
     font-weight: 600;
     color: #1a1a1a;
     margin-bottom: 1rem;
   }
   
   .btn-primary {
     background: #007bff;
     color: white;
     padding: 0.75rem 1.5rem;
     border: none;
     border-radius: 4px;
     cursor: pointer;
     font-size: 1rem;
     transition: background 0.2s;
   }
   
   .btn-primary:hover {
     background: #0056b3;
   }
   
   .btn-primary:disabled {
     opacity: 0.6;
     cursor: not-allowed;
   }
```

2. **Design System Variables**
```css
   :root {
     --primary: #007bff;
     --secondary: #6c757d;
     --success: #28a745;
     --danger: #dc3545;
     --warning: #ffc107;
     
     --spacing-xs: 0.25rem;
     --spacing-sm: 0.5rem;
     --spacing-md: 1rem;
     --spacing-lg: 1.5rem;
     --spacing-xl: 2rem;
     
     --border-radius: 4px;
     --box-shadow: 0 2px 4px rgba(0,0,0,0.1);
   }
```

3. **Responsive Design**
```css
   @media (max-width: 768px) {
     .component-container {
       padding: 1rem;
     }
     
     .grid {
       grid-template-columns: 1fr;
     }
   }
```

═══════════════════════════════════════════════════════════════
FILE CREATION WORKFLOW
═══════════════════════════════════════════════════════════════

When creating a feature like "PantryManager", create ALL of these files:

1. **Backend Model** (`models.py` or add to existing):
```python
   class PantryItem(db.Model):
       __tablename__ = 'pantry_items'
       id = db.Column(db.Integer, primary_key=True)
       name = db.Column(db.String(100), nullable=False)
       quantity = db.Column(db.Integer, default=1)
       category = db.Column(db.String(50))
       created_at = db.Column(db.DateTime, default=datetime.utcnow)
```

2. **Backend API** (`pantry_service.py`):
```python
   from flask import Blueprint, request
   from models import PantryItem, db
   
   pantry_bp = Blueprint('pantry', __name__)
   
   @pantry_bp.route('/items', methods=['GET', 'POST'])
   def handle_items():
       # Full CRUD implementation
```

3. **Frontend Component** (`PantryManager.jsx`):
```jsx
   import React, { useState, useEffect } from 'react';
   import * as api from './api';
   import './PantryManager.css';
   
   function PantryManager() {
       // Full implementation with API calls
   }
```

4. **Component Styles** (`PantryManager.css`):
```css
   .pantry-manager {
       /* Complete styling */
   }
```

═══════════════════════════════════════════════════════════════
VALIDATION CHECKLIST
═══════════════════════════════════════════════════════════════

Before considering code complete, verify:

Backend:
- [ ] Real database operations (db.session.add/commit/delete)
- [ ] All CRUD endpoints (GET, POST, PUT, DELETE)
- [ ] Input validation with error messages
- [ ] Error handling with try/catch
- [ ] Appropriate HTTP status codes
- [ ] SQL injection prevention (parameterized queries)

Frontend:
- [ ] Real API calls (api.get/post/put/del)
- [ ] State management (useState for data, loading, error)
- [ ] Loading states shown to user
- [ ] Error handling with user feedback (toast/alert)
- [ ] Success feedback on operations
- [ ] Empty state handling
- [ ] Form validation
- [ ] CSS file imported and used

Styling:
- [ ] CSS file exists
- [ ] All elements have CSS classes
- [ ] Responsive design (@media queries)
- [ ] Hover states on interactive elements
- [ ] Consistent spacing and colors
- [ ] Professional appearance

Integration:
- [ ] Frontend calls correct backend endpoints
- [ ] Data persists to database
- [ ] UI updates after operations
- [ ] Errors are caught and displayed
- [ ] User can perform full workflow (add, view, edit, delete)

═══════════════════════════════════════════════════════════════
EXAMPLES OF COMPLETE vs INCOMPLETE CODE
═══════════════════════════════════════════════════════════════

❌ INCOMPLETE (DO NOT CREATE):
```jsx
function TodoList() {
  const [todos, setTodos] = useState([
    { id: 1, text: 'Sample todo' }  // Fake data
  ]);
  
  const handleAdd = () => {
    console.log('Add clicked');  // No real action
  };
  
  return (
    <div>  // No styling
      <button onClick={handleAdd}>Add</button>
      {todos.map(todo => <div>{todo.text}</div>)}
    </div>
  );
}
```

✅ COMPLETE (ALWAYS CREATE):
```jsx
import React, { useState, useEffect } from 'react';
import * as api from './api';
import './TodoList.css';

function TodoList() {
  const [todos, setTodos] = useState([]);
  const [loading, setLoading] = useState(true);
  const [newTodo, setNewTodo] = useState('');
  
  useEffect(() => {
    fetchTodos();
  }, []);
  
  const fetchTodos = async () => {
    try {
      const data = await api.get('/todos');
      setTodos(data);
    } catch (error) {
      toast.error('Failed to load todos');
    } finally {
      setLoading(false);
    }
  };
  
  const handleAdd = async (e) => {
    e.preventDefault();
    if (!newTodo.trim()) return;
    
    try {
      const created = await api.post('/todos', { text: newTodo });
      setTodos([...todos, created]);
      setNewTodo('');
      toast.success('Todo added!');
    } catch (error) {
      toast.error('Failed to add todo');
    }
  };
  
  const handleDelete = async (id) => {
    try {
      await api.del(`/todos/${id}`);
      setTodos(todos.filter(t => t.id !== id));
      toast.success('Todo deleted!');
    } catch (error) {
      toast.error('Failed to delete todo');
    }
  };
  
  if (loading) return <div className="loading">Loading...</div>;
  
  return (
    <div className="todo-list">
      <h1 className="todo-title">My Todos</h1>
      
      <form onSubmit={handleAdd} className="todo-form">
        <input
          type="text"
          value={newTodo}
          onChange={(e) => setNewTodo(e.target.value)}
          placeholder="What needs to be done?"
          className="todo-input"
        />
        <button type="submit" className="btn-primary">Add</button>
      </form>
      
      {todos.length === 0 ? (
        <div className="empty-state">
          <p>No todos yet. Add one above!</p>
        </div>
      ) : (
        <div className="todo-items">
          {todos.map(todo => (
            <div key={todo.id} className="todo-item">
              <span className="todo-text">{todo.text}</span>
              <button 
                onClick={() => handleDelete(todo.id)}
                className="btn-danger btn-small"
              >
                Delete
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default TodoList;
```

═══════════════════════════════════════════════════════════════
FINAL REMINDERS
═══════════════════════════════════════════════════════════════

1. **NO PLACEHOLDERS**: Every function must do real work
2. **NO MOCK DATA**: All data must come from API/database
3. **NO UNSTYLED ELEMENTS**: Every component needs CSS
4. **NO CONSOLE.LOG**: Use proper error handling and user feedback
5. **NO TODO COMMENTS**: Code must be complete

6. **YES TO**:
   - Real API calls (api.post/get/put/del)
   - Real database operations (db.session.add/commit)
   - CSS files and classes
   - Error handling with try/catch
   - User feedback with toasts/alerts
   - Loading and empty states
   - Professional, production-ready code

Your goal is to create code that could be deployed to production immediately.
Every file you create should be COMPLETE and FUNCTIONAL.

If you're unsure about any detail, choose the most complete implementation.
NEVER leave TODO comments or placeholder implementations.
"""

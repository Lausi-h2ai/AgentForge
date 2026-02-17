# Production-Ready Code

## Metadata
- Keywords: production, complete, functional, api, database, styling, frontend, backend, react, flask
- Description: Guidelines for creating production-ready, fully functional code with no placeholders
- Priority: 90

## Purpose

This skill ensures agents create COMPLETE, WORKING code instead of placeholder implementations.

Use this skill when:
- Creating frontend components
- Building backend APIs
- Implementing CRUD operations
- Generating any production code

## Critical Rules

### Rule 1: NO Placeholder Code

❌ FORBIDDEN:
```javascript
const handleClick = () => {
  console.log('Clicked');  // Placeholder
  // TODO: Implement API call
};
```

✅ REQUIRED:
```javascript
const handleClick = async () => {
  try {
    const result = await api.post('/items', data);
    setItems([...items, result]);
    toast.success('Item added!');
  } catch (error) {
    toast.error('Failed to add item');
  }
};
```

### Rule 2: Frontend Must Use Real APIs

Every React component that displays or modifies data MUST:

```javascript
// 1. Import API service
import * as api from './api';

// 2. State management
const [data, setData] = useState([]);
const [loading, setLoading] = useState(false);
const [error, setError] = useState(null);

// 3. Fetch on mount
useEffect(() => {
  const fetchData = async () => {
    const result = await api.get('/endpoint');
    setData(result);
  };
  fetchData();
}, []);

// 4. CRUD operations
const create = async (item) => {
  const result = await api.post('/endpoint', item);
  setData([...data, result]);
};
```

### Rule 3: Backend Must Use Real Database

Every API endpoint MUST interact with the database:

```python
@app.route('/items', methods=['POST'])
def create_item():
    data = request.json
    
    # Validation
    if not data.get('name'):
        return {'error': 'Name required'}, 400
    
    # Database operation
    item = Item(**data)
    db.session.add(item)
    db.session.commit()
    
    return item.to_dict(), 201
```

### Rule 4: ALL Elements Must Be Styled

```javascript
// Import CSS
import './Component.css';

// Use className on EVERY element
<div className="container">
  <h1 className="title">Title</h1>
  <button className="btn-primary">Action</button>
</div>
```

## Requirements Checklist

Frontend:
- [ ] Imports api service
- [ ] Makes real API calls (not console.log)
- [ ] Has useState for data/loading/error
- [ ] Has useEffect to fetch on mount
- [ ] Error handling with try/catch
- [ ] User feedback (toasts)
- [ ] Loading states
- [ ] Empty states
- [ ] CSS file created and imported
- [ ] All elements have className

Backend:
- [ ] Real database operations (db.session)
- [ ] Input validation
- [ ] Error handling with try/except
- [ ] Appropriate HTTP status codes
- [ ] Parameterized queries (no SQL injection)
- [ ] Logging

## Anti-Patterns

### ❌ Mock Data

```javascript
const items = [
  { id: 1, name: 'Sample Item' }
];
```

### ✅ Real Data from API

```javascript
const [items, setItems] = useState([]);

useEffect(() => {
  const fetch = async () => {
    const data = await api.get('/items');
    setItems(data);
  };
  fetch();
}, []);
```

## Validation

Before considering code complete:
1. Can user perform action? (click button)
2. Does action trigger real API call?
3. Does API update database?
4. Does UI update to reflect change?
5. Does user see feedback?
6. Is component styled?
7. Are errors handled?

ALL must be YES.
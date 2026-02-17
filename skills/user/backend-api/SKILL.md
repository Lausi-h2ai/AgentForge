# Backend API Development

## Metadata
- Keywords: backend, api, endpoint, flask, database, crud, validation, error
- Description: Guidelines for creating robust backend APIs with proper database operations
- Priority: 85

## Purpose

Ensures backend APIs have real database operations, validation, and error handling.

## Critical Rules

### Rule 1: Complete CRUD Operations

Every resource needs all four operations:

```python
# CREATE
@app.route('/items', methods=['POST'])
def create_item():
    data = request.json
    item = Item(**data)
    db.session.add(item)
    db.session.commit()
    return item.to_dict(), 201

# READ (list)
@app.route('/items', methods=['GET'])
def get_items():
    items = Item.query.all()
    return [item.to_dict() for item in items], 200

# READ (single)
@app.route('/items/<int:id>', methods=['GET'])
def get_item(id):
    item = Item.query.get_or_404(id)
    return item.to_dict(), 200

# UPDATE
@app.route('/items/<int:id>', methods=['PUT'])
def update_item(id):
    item = Item.query.get_or_404(id)
    data = request.json
    for key, value in data.items():
        setattr(item, key, value)
    db.session.commit()
    return item.to_dict(), 200

# DELETE
@app.route('/items/<int:id>', methods=['DELETE'])
def delete_item(id):
    item = Item.query.get_or_404(id)
    db.session.delete(item)
    db.session.commit()
    return {'message': 'Deleted'}, 200
```

### Rule 2: Input Validation

ALWAYS validate before database operations:

```python
def validate_item(data):
    errors = {}
    
    if not data.get('name'):
        errors['name'] = 'Name is required'
    
    if not data.get('quantity') or data['quantity'] <= 0:
        errors['quantity'] = 'Quantity must be positive'
    
    return errors

@app.route('/items', methods=['POST'])
def create_item():
    data = request.json
    
    errors = validate_item(data)
    if errors:
        return {'error': 'Validation failed', 'fields': errors}, 400
    
    # Proceed with creation...
```

### Rule 3: Error Handling

Wrap ALL database operations:

```python
@app.route('/items', methods=['POST'])
def create_item():
    try:
        data = request.json
        item = Item(**data)
        db.session.add(item)
        db.session.commit()
        return item.to_dict(), 201
    
    except IntegrityError:
        db.session.rollback()
        return {'error': 'Duplicate entry'}, 409
    
    except Exception as e:
        db.session.rollback()
        app.logger.error(f'Error creating item: {e}')
        return {'error': 'Internal server error'}, 500
```

### Rule 4: SQL Injection Prevention

ALWAYS use parameterized queries:

```python
# ✅ CORRECT - Parameterized (SQLAlchemy does this)
item = Item.query.filter_by(name=user_input).first()

# ❌ WRONG - String formatting (SQL injection!)
# query = f"SELECT * FROM items WHERE name='{user_input}'"
```

## Requirements

Every endpoint must have:
- [ ] Real database operation (no mock data)
- [ ] Input validation
- [ ] Error handling with try/except
- [ ] Appropriate HTTP status codes (200, 201, 400, 404, 500)
- [ ] db.session.rollback() on errors
- [ ] Logging
- [ ] SQL injection prevention
- [ ] Authentication (if needed)

## Common Patterns

### Pagination

```python
@app.route('/items', methods=['GET'])
def get_items():
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    
    pagination = Item.query.paginate(page=page, per_page=per_page)
    
    return {
        'items': [item.to_dict() for item in pagination.items],
        'total': pagination.total,
        'page': page,
        'pages': pagination.pages
    }, 200
```

### Filtering

```python
@app.route('/items', methods=['GET'])
def get_items():
    category = request.args.get('category')
    search = request.args.get('search')
    
    query = Item.query
    
    if category:
        query = query.filter_by(category=category)
    
    if search:
        query = query.filter(Item.name.ilike(f'%{search}%'))
    
    items = query.all()
    return [item.to_dict() for item in items], 200
```
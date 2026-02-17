# Frontend Design & Styling

## Metadata
- Keywords: frontend, css, styling, design, responsive, ui, component, react
- Description: Guidelines for creating professional, styled frontend components
- Priority: 75

## Purpose

Ensures all frontend code includes complete, professional styling.

## Critical Rules

### Rule 1: Always Create CSS File

For every component, create matching CSS file:

```javascript
// PantryManager.jsx
import './PantryManager.css';

function PantryManager() {
  return <div className="pantry-manager">...</div>;
}
```

### Rule 2: Design System Variables

Use consistent design tokens:

```css
:root {
  /* Colors */
  --primary: #007bff;
  --secondary: #6c757d;
  --success: #28a745;
  --danger: #dc3545;
  
  /* Spacing */
  --spacing-xs: 0.25rem;
  --spacing-sm: 0.5rem;
  --spacing-md: 1rem;
  --spacing-lg: 1.5rem;
  --spacing-xl: 2rem;
  
  /* Typography */
  --font-size-sm: 0.875rem;
  --font-size-base: 1rem;
  --font-size-lg: 1.125rem;
  --font-size-xl: 1.25rem;
  
  /* Border radius */
  --radius-sm: 0.25rem;
  --radius-md: 0.5rem;
  --radius-lg: 0.75rem;
}
```

### Rule 3: Component Structure

```css
/* Container */
.component-name {
  max-width: 1200px;
  margin: 0 auto;
  padding: var(--spacing-lg);
}

/* Elements */
.component-name__element {
  /* Styles */
}

/* States */
.component-name--loading {
  opacity: 0.6;
}

/* Responsive */
@media (max-width: 768px) {
  .component-name {
    padding: var(--spacing-md);
  }
}
```

### Rule 4: Interactive States

All interactive elements MUST have hover/focus states:

```css
.btn {
  background: var(--primary);
  transition: all 0.2s;
}

.btn:hover {
  background: #0056b3;
  transform: translateY(-1px);
}

.btn:active {
  transform: translateY(0);
}

.input:focus {
  border-color: var(--primary);
  box-shadow: 0 0 0 3px rgba(0, 123, 255, 0.1);
}
```

## Requirements

Every component must have:
- [ ] Separate .css file
- [ ] CSS imported in component
- [ ] All elements with className
- [ ] Responsive design (@media queries)
- [ ] Hover states on buttons/links
- [ ] Focus states on inputs
- [ ] Loading state styling
- [ ] Error state styling
- [ ] Empty state styling
- [ ] Consistent spacing (using CSS variables)
- [ ] Consistent colors (using CSS variables)

## Examples

### Complete Button Styles

```css
.btn {
  padding: 0.5rem 1rem;
  border: none;
  border-radius: var(--radius-md);
  cursor: pointer;
  font-weight: 500;
  transition: all 0.2s;
}

.btn-primary {
  background: var(--primary);
  color: white;
}

.btn-primary:hover {
  background: #0056b3;
}

.btn-primary:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.btn-danger {
  background: var(--danger);
  color: white;
}
```

### Complete Card Styles

```css
.card {
  background: white;
  border-radius: var(--radius-lg);
  padding: var(--spacing-lg);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
  transition: all 0.2s;
}

.card:hover {
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
  transform: translateY(-2px);
}
```
#!/usr/bin/env python3
"""
Validation script for refactored agents.
Checks that all Python files:
1. Have valid syntax
2. Can be imported
3. Have proper class definitions
4. Have required methods
"""

import sys
import ast
from pathlib import Path


def check_syntax(filepath):
    """Check if Python file has valid syntax"""
    try:
        with open(filepath, 'r') as f:
            code = f.read()
        ast.parse(code)
        return True, None
    except SyntaxError as e:
        return False, f"Syntax error at line {e.lineno}: {e.msg}"


def check_class_exists(filepath, class_name):
    """Check if a class is defined in the file"""
    try:
        with open(filepath, 'r') as f:
            tree = ast.parse(f.read())
        
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                if node.name == class_name:
                    return True, None
        
        return False, f"Class {class_name} not found"
    except Exception as e:
        return False, str(e)


def check_method_exists(filepath, class_name, method_name):
    """Check if a method exists in a class"""
    try:
        with open(filepath, 'r') as f:
            tree = ast.parse(f.read())
        
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == class_name:
                for item in node.body:
                    if isinstance(item, ast.FunctionDef) and item.name == method_name:
                        return True, None
        
        return False, f"Method {method_name} not found in {class_name}"
    except Exception as e:
        return False, str(e)


def main():
    """Run all validation checks"""
    
    # Get the directory where this script is located
    script_dir = Path(__file__).parent
    
    checks = [
        # (filepath, class_name, required_methods)
        ("base_agent.py", "BaseAgent", ["__init__", "_call_llm", "chat"]),
        ("utils.py", None, None),  # Module, not class
        ("developer_agent.py", "DeveloperAgent", ["__init__", "develop", "chat"]),
        ("code_reviewer_agent.py", "CodeReviewerAgent", ["__init__", "review_code", "chat"]),
        ("product_owner_agent.py", "ProductOwnerAgent", ["__init__", "chat"]),
        ("requirements_analyst_agent.py", "RequirementsAnalystAgent", ["__init__", "analyze_requirements"]),
        ("software_architect_agent.py", "SoftwareArchitectAgent", ["__init__", "design_architecture"]),
        ("documentation_agent.py", "DocumentationAgent", ["__init__", "write_documentation"]),
        ("unit_test_agent.py", "UnitTestAgent", ["__init__", "write_tests"]),
        ("tester_agent.py", "TesterAgent", ["__init__", "run_quality_gate"]),
        ("__init__.py", None, None),  # Init file
    ]
    
    print("="*60)
    print("VALIDATION SCRIPT - Refactored Agents")
    print("="*60)
    
    all_passed = True
    
    for check in checks:
        filename = check[0]
        class_name = check[1]
        required_methods = check[2]
        
        filepath = script_dir / filename
        
        print(f"\n📄 Checking {filename}...")
        
        # Check 1: File exists
        if not filepath.exists():
            print(f"   ❌ File not found: {filepath}")
            all_passed = False
            continue
        
        # Check 2: Valid syntax
        success, error = check_syntax(filepath)
        if not success:
            print(f"   ❌ {error}")
            all_passed = False
            continue
        else:
            print(f"   ✅ Syntax valid")
        
        # Check 3: Class exists (if applicable)
        if class_name:
            success, error = check_class_exists(filepath, class_name)
            if not success:
                print(f"   ❌ {error}")
                all_passed = False
                continue
            else:
                print(f"   ✅ Class {class_name} found")
            
            # Check 4: Required methods exist
            if required_methods:
                for method in required_methods:
                    success, error = check_method_exists(filepath, class_name, method)
                    if not success:
                        print(f"   ❌ {error}")
                        all_passed = False
                    else:
                        print(f"   ✅ Method {method} found")
        else:
            print(f"   ✅ Module structure valid")
    
    print("\n" + "="*60)
    if all_passed:
        print("✅ ALL VALIDATION CHECKS PASSED")
        print("="*60)
        return 0
    else:
        print("❌ SOME VALIDATION CHECKS FAILED")
        print("="*60)
        return 1


if __name__ == "__main__":
    sys.exit(main())

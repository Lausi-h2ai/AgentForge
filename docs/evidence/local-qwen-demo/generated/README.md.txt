# eval_20261006T121320549219_slugify

A minimal Python utility for converting text into URL-friendly slugs using only the standard library. This project implements a `slugify` function that normalizes text by lowercasing, retaining only ASCII letters and digits, replacing non-retained characters with hyphens, and stripping leading/trailing hyphens.

## Overview

This project consists of three core files:
- **slugify.py**: Contains the core logic for text normalization.
- **test_slugify.py**: Provides comprehensive `unittest` test cases covering normal usage, edge cases, and Unicode handling.
- **run_tests.py**: A script to execute the test suite.

The implementation strictly adheres to the requirement of using only standard library modules (`re` and `string`), ensuring no external dependencies are needed.

## File Structure

```text
workspace/
  .gitignore
  README.md
  run_tests.py
  slugify.py
  test_slugify.py
  __pycache__/
    slugify.cpython-312.pyc
    test_slugify.cpython-312-pytest-9.1.1.pyc
```

## Prerequisites

- Python 3.x
- No external packages required (uses only the standard library).

## Installation & Setup

1. Navigate to the project directory (`workspace/`).
2. Create a virtual environment (optional but recommended):
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```
3. Install dependencies (though none are strictly required for this standard-library-only project, this step follows standard practice):
   ```bash
   pip install -r requirements.txt
   ```
   *Note: Since the project uses only the standard library, `requirements.txt` is effectively empty or contains no runtime dependencies.*

## Running the Application

To run the test suite and verify the functionality:

```bash
python -m unittest test_slugify.py
```

Alternatively, you can use the provided runner script:

```bash
python run_tests.py
```

## Usage

The `slugify` function is imported from `slugify.py`. It accepts a string and returns a normalized slug based on the following rules:

- **Lowercasing**: All ASCII letters are converted to lowercase.
- **Retention**: Only ASCII letters and digits are kept.
- **Replacement**: Runs of non-retained characters (including non-ASCII characters) are replaced with a single hyphen (`-`).
- **Trimming**: Leading and trailing hyphens are removed.
- **Empty Handling**: Returns an empty string for empty input or input containing only non-retained characters.
- **Unicode**: Does **not** transliterate Unicode characters (e.g., `é` is treated as a non-retained character and removed, resulting in an empty string for input `"é"`).

### Examples

| Input | Output |
| :--- | :--- |
| `"  Hello, WORLD!  "` | `"hello-world"` |
| `"a---b___c"` | `"a-b-c"` |
| `"A/B"` | `"a-b"` |
| `"!!!"` | `""` |
| `""` | `""` |
| `"héllo wörld"` | `"h-llo-w-rld"` |
| `"é"` | `""` |
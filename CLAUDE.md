# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

MONK is a Django web application for managing and accessing Nihon-Kohden MFER medical waveform data (`.mwf` files). It provides role-based access control, data anonymization, and waveform visualization for healthcare/research use.

## Bootstrap on GNU/Guix

The repo has a `manifest.scm` and `.envrc` for direnv. On first `cd` into the repo, direnv will:
1. Activate the Guix environment from `manifest.scm` (all standard deps)
2. Clone monklib with its pybind11 submodule into `.monklib-src/`
3. Build monklib and install it into `.venv/` (inheriting Guix packages)

```bash
# One-time: authorize the project directory for guix shell auto-loading
echo $PWD >> ~/.config/guix/shell-authorized-directories

# One-time: allow direnv to run .envrc
direnv allow
```

On first `cd` into the repo, direnv will clone monklib, build it (takes ~1 min), and cache it in `.venv/`. On subsequent entries the cached venv is reused.

```bash
# Apply Django migrations (once after bootstrap)
cd monksystem && python manage.py migrate

# Run tests
pytest base/tests/
```

`monklib` is a C++/CMake/pybind11 extension not in Guix — the `.envrc` builds it with `--no-build-isolation` so Guix's cmake/ninja are used instead of pip's downloaded cmake wrapper. If the build fails, delete `.venv/` and re-enter the directory.

## Commands

All commands run from `monksystem/` directory (with `.venv` active):

```bash
# Run development server
python manage.py runserver

# Database migrations
python manage.py migrate
python manage.py makemigrations

# Run all tests
pytest

# Run a single test file
pytest base/tests/test_views.py

# Run a specific test
pytest base/tests/test_views.py::TestClassName::test_method_name

# Run with coverage
pytest --cov=base

# Code formatting
black .

# Linting
pylint base/
flake8 base/
```

## Architecture

### Core Models (`base/models.py`)

- **UserProfile** — Extends Django's User with name and mobile fields; created on registration
- **File** — Uploaded `.mwf` waveform files with anonymization flag and upload timestamp
- **Subject** — Patient/subject extracted from MFER file headers (linked to a File)
- **Project** — Groups users (M2M) and subjects (M2M) for access control
- **FileImport** — Audit trail linking users to files they imported

### Access Control Pattern

File access is controlled via two conditions in views: (1) the user imported the file (`FileImport` record exists), or (2) the user is a member of a project that contains the subject linked to the file. Most views use `@login_required`.

### Medical Data Processing (`base/utils.py`)

The `monklib` library (external dependency, not in this repo) handles raw MFER file parsing. Key utilities:
- `process_and_create_subject()` — Parses MFER headers via `monklib.get_header()` and creates `Subject` records
- `anonymize_data()` — Strips PII from medical files before export
- `plot_graph()` — Generates interactive Plotly visualizations from waveform channels
- `download_format_csv()` — Exports selected channels as CSV using `monklib.convert_to_csv()`

### URL Structure

All app routes are in `base/urls.py`. Main route groups:
- Auth: `/login/`, `/register/`, `/logout/`
- Files: `/import_file/`, `/import_multiple_files/`, `/view_files/`, `/file/<id>/`
- Projects: `/add_project/`, `/edit_project/<id>/`, `/view_projects/`, `/leave_project/<id>/`
- Subjects: `/view_subjects/`, `/subject/<id>/`
- Export/Viz: `/download-MFER-Header/<id>/`, `/download-MWF/<id>/`, `/download-CSV-Format/<id>/`, `/plot_graph/<id>/`

### Testing

- Unit tests: `base/tests/` — covers models, forms, views, URLs
- Functional tests: `base/functional_tests/` — Selenium tests requiring ChromeDriver
- Test framework: pytest with pytest-django

### Settings

- Time zone: `Europe/Oslo`
- Uploaded files stored in `nihon_kohden_files/` (gitignored)
- SQLite database (`db.sqlite3`) for development

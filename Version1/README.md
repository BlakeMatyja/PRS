# Patient Record System (PRS) - Version 1

Original AI-generated implementation (unmodified). Command-line interface, Python 3.8+, SQLite.
Uses the Python standard library only - nothing to install.

## Run
    python main.py

Data is stored in `prs.db` (created on first run) and persists between runs.
Delete `prs.db` to start fresh.

## Demo accounts (synthetic)
| Username | Password   | Role    |
|----------|------------|---------|
| staff1   | staff123   | staff   |
| staff2   | staff456   | staff   |
| manager1 | manager123 | manager |

## Optional: real AI categorization
    export ANTHROPIC_API_KEY=your-key      (Windows: set ANTHROPIC_API_KEY=your-key)
Without a key, a keyword matcher is used and labeled "Keyword fallback (NOT an AI model)".
If the AI is unreachable or unsure, the note is still saved and staff can pick a category or skip.

## Layout
    main.py                  CLI (user interface)
    prs/authentication.py    login, roles, clearance checks
    prs/patient.py           Patient + PatientService
    prs/visit.py             VisitNote + VisitService
    prs/persistence.py       SQLite repositories
    prs/ai_integration.py    AI adapter + fallback
    prs/exceptions.py        custom errors

## Features
Register patient (unique ID), search by ID, edit (never the ID), visit notes with auto date/user,
visit history, AI-suggested category (accept/reject/manual), audit log, manager-only delete and clearance.

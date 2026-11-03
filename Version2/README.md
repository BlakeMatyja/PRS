# Patient Record System (PRS) - Version 2

Revised implementation (corrected and refactored from Version 1).
Command-line interface, Python 3.8+, SQLite. Standard library only - nothing to install.

## Run
From this `Version2` folder:

    python main.py          (Windows: py main.py)

Data is stored in `prs.db` in the current folder (created on first run) and persists between runs.
Delete `prs.db` to start fresh. A `prs.db` created by Version 1 also works; the Patient ID
trigger is added to it the first time Version 2 opens it.

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
    main.py                  entry point
    prs/app.py               PRSApplication: builds database, repositories, services
    prs/cli.py               PRSConsole: menus, prompts, output
    prs/formatting.py        display formatting for patients, notes, audit rows
    prs/authentication.py    User, AuthService, login and role checks
    prs/patient.py           Patient (read-only patient_id) + PatientService
    prs/visit.py             VisitNote + VisitService
    prs/persistence.py       SQLite schema and repositories
    prs/ai_integration.py    AI categorizer, keyword fallback, CategorizationService
    prs/exceptions.py        custom errors

## Features
Register patient (unique, permanent ID), search by ID, edit permitted fields, visit notes with
automatic date and user, visit history, AI-suggested category (accept/reject/manual), audit log,
manager-only delete, clearance and audit log view.

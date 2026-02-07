# Cogitus

> [!NOTE]
>
> This is still in the very-early stages of development and functionality is
> likely to change.

**Cogitus — a fast, searchable terminal workspace for capturing and evolving
programming ideas.**

Cogitus is a Python-based TUI (Terminal User Interface) built with Textual. It
is designed specifically for developers who want a structured, keyboard-driven
way to capture, explore, and refine programming ideas without leaving the
terminal. This is not a generic note-taking app and not a task manager. Cogitus
is focused on structured idea capture, iteration, and discovery.

---

## Goals

- Fast, local-first idea capture
- Fully keyboard-driven workflow
- Searchable and structured storage
- Minimal, distraction-free UI
- Designed specifically for programming and technical concepts

---

## Core Concepts

Cogitus treats ideas as structured entities rather than loose notes. Each idea
can include:

- Title
- Body/description (Markdown-friendly text - edit in markdown, display rendered
  using `Textual`/`Rich` native functionality)
- Tags
- Timestamps (created/updated)

Future versions may introduce:

- Idea linking (relationships between ideas)
- Graph views
- Scoring or priority signals
- SQLite FTS5-powered full-text search
- AI-assisted idea expansion

---

## Architecture

- UI: Built with Textual
- Database: SQLite (local file, WAL mode)
- Data Access: `sqliter-py`
- Package Management: `uv` (not pip)

The project intentionally separates:

- Textual UI layer (screens and widgets)
- Repository/service layer for database access
- Schema and migration management

Cogitus is also a real-world validation project for `sqliter-py`.

---

## Planned MVP (v0.1)

- Create new ideas
- Edit existing ideas
- List ideas
- Tag ideas
- Basic search (SQLite `LIKE`)
- View idea details

Search will initially be simple but structured to evolve into FTS5.

---

## Roadmap

### v0.2

- Full-text search (FTS5)
- Tag filtering
- Improved navigation and keyboard shortcuts

### v0.3 - Idea linking (graph-style relationships)

- Enhanced search scoring
- Richer metadata

---

## Target Users

- Solo developers
- Indie hackers
- Open-source maintainers
- Engineers who think in terminals

If you sketch ideas in README files, TODO lists, or scattered Markdown files
across projects, Cogitus aims to centralize that thinking into a structured,
searchable workspace.

---

## Installation (Planned)

```bash
uv tool install cogitus
```

or as a project dependency:

```bash
uv add cogitus
```

---

## Development

This project uses:

- `uv` for dependency and environment management
- SQLite for local storage
- Textual for UI
- Standard formatting and linting tools defined in the repository

---

## Philosophy

Cogitus is designed to be:

- Local-first
- Minimal
- Fast
- Developer-centric
- Extensible without becoming bloated

It should feel like a serious engineering tool — not a productivity app with a
marketing layer

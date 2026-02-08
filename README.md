# Cogitus

> [!NOTE]
>
> Cogitus is currently in `v0.1` MVP/alpha stage. Core workflows are available,
> and interfaces may continue to evolve in subsequent releases.

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

## MVP (v0.1)

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

- SQLite FTS5 search backend
- Better ranking/snippet presentation
- Tag filtering and combined query UX
- Navigation and keybinding polish
- In-place right-pane Markdown edit mode (view/edit toggle in content pane)
- Contextual dynamic toolbar/actions by mode
- Evaluate SQLite write tuning (`PRAGMA synchronous=NORMAL`) as an optional
  performance optimization, backed by benchmark and risk assessment.

### v0.3

- Idea linking (explicit relationships)
- Relationship browsing primitives
- Richer metadata and prioritization signals

### v0.4

- Add non-TUI CLI tasks for idea management:
  - list ideas,
  - dump/export ideas,
  - delete ideas.
- Ensure CLI task layer reuses the same repository/service abstractions as the
  TUI.

### v0.5+

- Graph-oriented idea exploration views
- Scoring heuristics (impact/effort/confidence)
- Optional AI-assisted idea expansion and prompt-to-structure workflows

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

## Installation

```bash
uv tool install cogitus
```

## Usage

```bash
cogitus
```

---

## Clipboard Support

Cogitus uses two clipboard strategies for maximum compatibility:

- **OSC 52** (primary) — works in most modern terminals (Ghostty, iTerm2, Kitty,
  Alacritty, WezTerm, Windows Terminal) and through tmux/SSH
- **pyperclip** (fallback) — uses system tools like `xclip`, `xsel`, or
  `pbcopy` for terminals that don't support OSC 52 (e.g. Gnome Terminal, macOS
  Terminal)

**tmux users:** You need `set-clipboard` enabled in your `~/.tmux.conf` for
OSC 52 to pass through:

```tmux
set -g set-clipboard on
```

**Linux users without OSC 52 support:** Install `xclip` or `xsel` for the
pyperclip fallback to work:

```bash
sudo apt-get install xclip   # Debian/Ubuntu
sudo pacman -S xclip          # Arch
sudo dnf install xclip        # Fedora
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

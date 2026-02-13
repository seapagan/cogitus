# Todo

Ideas to add to Cogitus

## UI

- Allow key customization (using the `Textual` built-in functionality and the
  config file). eg Ctrl-S on my system is mapped to tmux
- continue navigation and keybinding polish.
- add in-place right-pane markdown edit mode (view/edit toggle).
- add contextual dynamic toolbar/actions by mode.

## CLI

None

## Search and Filtering

- add tag filtering and combined query UX.
- add SQLite FTS5 search backend.
- improve result ranking/snippet presentation.
- define and lock a stable search service interface so `LIKE` can be swapped
  for FTS5 without UI contract changes.
- add compatibility tests to ensure UI/search call contracts stay unchanged
  when moving from `LIKE` to FTS5.

## Export, Import, and Backup

- add export to assorted file-types both on the tags, group and idea level.
- save and load either entire database or individual ideas

## Undo and History

- add full undo ability (basically with git-like functionality, but not using
  git - a journal that we can unwind?) Include edited, created and deleted
  ideas at first, more as the need arises. How would we store this?
- Allow linking to a Git repository holding the database. On change to the
  database, create a commit mentioning the change (which Idea was
  added/editied etc). Push either after any save, or more likely on exit (give
  option? After create/edit/save is prob better)

## Profiles and Multi-Device

- add profiles, link ideas to a profile, optionally password protected.
- cloud database, allows reading/writing from multiple machines.

## Relationships and Idea Graph

- add explicit idea linking relationships.
- add relationship browsing primitives.
- add richer metadata and prioritization signals.
- add graph-oriented idea exploration views.
- add scoring heuristics (impact/effort/confidence).

## Data Layer and Performance

- evaluate optional SQLite write tuning (`PRAGMA synchronous=NORMAL`) with
  benchmark and risk assessment.
- optimize group-reassignment path to avoid per-row updates in
  `IdeaRepository.bulk_move_group` (prefer set-based `UPDATE ... WHERE`).
- investigate adding bulk update support to `sqliter-py` (similar to existing
  bulk insert support) for efficient repository operations.
- once `sqliter-py` bulk update support exists, refactor
  `IdeaRepository.bulk_move_group` to remove inline SQL and use the ORM API.
- once sqliter-py issue #126 is fixed, remove `_fk_cache`-based group
  hydration workaround from `IdeaRepository` and use pure eager loading in
  relation-aware fetch paths.

## AI Assistance

- explore optional AI-assisted idea expansion and prompt-to-structure
  workflows.

# Todo

Ideas to add to Cogitus

## UI

- Allow key customization (using the `Textual` built-in functionality and the
  config file). eg Ctrl-S on my system is mapped to tmux
- continue navigation and keybinding polish.
- add in-place right-pane markdown edit mode (view/edit toggle).
- add contextual dynamic toolbar/actions by mode.
- add a tag management dialog with usage counts, rename/edit support, and
  explicit stale-tag pruning (selected/all stale with confirmation).
- extract shared autocomplete lifecycle logic currently duplicated across
  `IdeaListPanel` and `IdeaFormScreen` into a common helper/mixin to reduce
  divergence risk.

## CLI

None

## Search and Filtering

- add SQLite FTS5 search backend.
- improve result ranking/snippet presentation.
- optimize advanced search query execution to reduce multi-pass PK collection
  and re-fetch overhead as dataset size grows.
- add compatibility tests to ensure UI/search call contracts stay unchanged
  when moving from `LIKE` to FTS5.

## Export, Import, and Backup

- add export to assorted file-types both on the tags, group and idea level.
- save and load either entire database or individual ideas
- On creating an Idea, allow to use a local or remote file as the seed (ie get a
  todo from a github repo or local code)
- Allow to export an Idea to a remote file (this would be more difficult and
  need assorted auth additions)

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
- once `sqliter-py` issue `#132` (aggregate/group-by support) is resolved,
  replace raw SQL in `TagRepository.list_with_usage()` with ORM/query-builder
  aggregation.
- once `sqliter-py` issue `#133` (public M2M metadata for junction/column
  names) is resolved, replace hardcoded M2M SQL identifier constants in
  `TagRepository` with metadata read from the relationship descriptors.

## AI Assistance

- explore optional AI-assisted idea expansion and prompt-to-structure
  workflows.

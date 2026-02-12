# Development Workflow

## Local Documentation Commands

Use the existing project tasks:

- `poe docs:serve` for local live preview
- `poe docs:build` to build the static site
- `poe docs:publish` to deploy via GitHub Pages

## Build-Time Included Pages

The project TODO and Changelog docs pages are build-time includes.

- Edit `TODO.md` at repository root for TODO content changes.
- Edit `CHANGELOG.md` at repository root for changelog content changes.
- Do not duplicate that content in `docs/`; wrapper pages include these files
  during build.

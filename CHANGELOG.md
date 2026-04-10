# Changelog

This is an auto-generated log of all the changes that have been made to the
project since the first release, with the latest changes at the top.

This project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).


## [0.9.0](https://github.com/seapagan/cogitus/releases/tag/0.9.0) (April 10, 2026)

**New Features**

- Add fastapi api and remote backend mode ([#52](https://github.com/seapagan/cogitus/pull/52)) by [seapagan](https://github.com/seapagan)

**Dependency Updates**

- Deps: update cryptography and aiohttp to fix security alerts ([#54](https://github.com/seapagan/cogitus/pull/54)) by [seapagan](https://github.com/seapagan)
- Chore(deps): update dependency pygments to v2.20.0 [security] ([#53](https://github.com/seapagan/cogitus/pull/53)) by [renovate[bot]](https://github.com/apps/renovate)

[`Full Changelog`](https://github.com/seapagan/cogitus/compare/0.8.0...0.9.0) | [`Diff`](https://github.com/seapagan/cogitus/compare/0.8.0...0.9.0.diff) | [`Patch`](https://github.com/seapagan/cogitus/compare/0.8.0...0.9.0.patch)

## [0.8.0](https://github.com/seapagan/cogitus/releases/tag/0.8.0) (March 28, 2026)

**New Features**

- Read `About` license from metadata instead of hardcoding ([#48](https://github.com/seapagan/cogitus/pull/48)) by [seapagan](https://github.com/seapagan)
- Chore: update package metadata for PEP 639 ([#47](https://github.com/seapagan/cogitus/pull/47)) by [seapagan](https://github.com/seapagan)
- Feat: add about dialog ([#46](https://github.com/seapagan/cogitus/pull/46)) by [seapagan](https://github.com/seapagan)
- Add metadata-driven version display to CLI and TUI ([#45](https://github.com/seapagan/cogitus/pull/45)) by [seapagan](https://github.com/seapagan)

**Bug Fixes**

- Fix: refresh stale idea timestamps ([#49](https://github.com/seapagan/cogitus/pull/49)) by [seapagan](https://github.com/seapagan)

**Dependency Updates**

- Update deps to fix security alerts and bump others to latest versions ([#50](https://github.com/seapagan/cogitus/pull/50)) by [seapagan](https://github.com/seapagan)
- Chore(deps): update dependency uv_build to >=0.11.1,<0.12.0 ([#43](https://github.com/seapagan/cogitus/pull/43)) by [renovate[bot]](https://github.com/apps/renovate)

[`Full Changelog`](https://github.com/seapagan/cogitus/compare/0.7.0...0.8.0) | [`Diff`](https://github.com/seapagan/cogitus/compare/0.7.0...0.8.0.diff) | [`Patch`](https://github.com/seapagan/cogitus/compare/0.7.0...0.8.0.patch)

## [0.7.0](https://github.com/seapagan/cogitus/releases/tag/0.7.0) (March 24, 2026)

**New Features**

- Refine search result matching and layout ([#41](https://github.com/seapagan/cogitus/pull/41)) by [seapagan](https://github.com/seapagan)
- Refine left pane tree hierarchy and layout ([#40](https://github.com/seapagan/cogitus/pull/40)) by [seapagan](https://github.com/seapagan)

**Bug Fixes**

- Fix: scroll text area after enter ([#42](https://github.com/seapagan/cogitus/pull/42)) by [seapagan](https://github.com/seapagan)

**Refactoring**

- Use aggregation for tag usage listing ([#39](https://github.com/seapagan/cogitus/pull/39)) by [seapagan](https://github.com/seapagan)
- Use M2M metadata in tag repository ([#38](https://github.com/seapagan/cogitus/pull/38)) by [seapagan](https://github.com/seapagan)

[`Full Changelog`](https://github.com/seapagan/cogitus/compare/0.6.0...0.7.0) | [`Diff`](https://github.com/seapagan/cogitus/compare/0.6.0...0.7.0.diff) | [`Patch`](https://github.com/seapagan/cogitus/compare/0.6.0...0.7.0.patch)

## [0.6.0](https://github.com/seapagan/cogitus/releases/tag/0.6.0) (March 10, 2026)

**New Features**

- Add contextual rename for ideas and groups ([#35](https://github.com/seapagan/cogitus/pull/35)) by [seapagan](https://github.com/seapagan)
- Add dedicated search results mode ([#28](https://github.com/seapagan/cogitus/pull/28)) by [seapagan](https://github.com/seapagan)
- Overhaul search with fts5 and keyboard navigation ([#27](https://github.com/seapagan/cogitus/pull/27)) by [seapagan](https://github.com/seapagan)
- Add autocomplete flows for search and tag inputs ([#26](https://github.com/seapagan/cogitus/pull/26)) by [seapagan](https://github.com/seapagan)

**Bug Fixes**

- Confirm before discarding dirty idea edits ([#34](https://github.com/seapagan/cogitus/pull/34)) by [seapagan](https://github.com/seapagan)
- Fix content pane keyboard focus and footer hints ([#32](https://github.com/seapagan/cogitus/pull/32)) by [seapagan](https://github.com/seapagan)
- Fix modal button layout ([#31](https://github.com/seapagan/cogitus/pull/31)) by [seapagan](https://github.com/seapagan)
- Fix idea form tag autocomplete visibility ([#30](https://github.com/seapagan/cogitus/pull/30)) by [seapagan](https://github.com/seapagan)
- Fix search selection state handling ([#29](https://github.com/seapagan/cogitus/pull/29)) by [seapagan](https://github.com/seapagan)

**Refactoring**

- Simplify textual ui interaction helpers ([#36](https://github.com/seapagan/cogitus/pull/36)) by [seapagan](https://github.com/seapagan)

**Dependency Updates**

- Upgrade textual to 8.x ([#33](https://github.com/seapagan/cogitus/pull/33)) by [seapagan](https://github.com/seapagan)

[`Full Changelog`](https://github.com/seapagan/cogitus/compare/0.5.0...0.6.0) | [`Diff`](https://github.com/seapagan/cogitus/compare/0.5.0...0.6.0.diff) | [`Patch`](https://github.com/seapagan/cogitus/compare/0.5.0...0.6.0.patch)

## [0.5.0](https://github.com/seapagan/cogitus/releases/tag/0.5.0) (February 15, 2026)

**New Features**

- Add advanced search query operators ([#24](https://github.com/seapagan/cogitus/pull/24)) by [seapagan](https://github.com/seapagan)
- Add configurable default group setting ([#23](https://github.com/seapagan/cogitus/pull/23)) by [seapagan](https://github.com/seapagan)
- Add contextual new-idea group mode and validation warning ([#22](https://github.com/seapagan/cogitus/pull/22)) by [seapagan](https://github.com/seapagan)

**Refactoring**

- Refactor bulk_move_group to use sqliter update_where() ([#21](https://github.com/seapagan/cogitus/pull/21)) by [seapagan](https://github.com/seapagan)

[`Full Changelog`](https://github.com/seapagan/cogitus/compare/0.4.2...0.5.0) | [`Diff`](https://github.com/seapagan/cogitus/compare/0.4.2...0.5.0.diff) | [`Patch`](https://github.com/seapagan/cogitus/compare/0.4.2...0.5.0.patch)

## [0.4.2](https://github.com/seapagan/cogitus/releases/tag/0.4.2) (February 14, 2026)

**Bug Fixes**

- Fix keybinding and layout issues ([#19](https://github.com/seapagan/cogitus/pull/19)) by [seapagan](https://github.com/seapagan)

[`Full Changelog`](https://github.com/seapagan/cogitus/compare/0.4.1...0.4.2) | [`Diff`](https://github.com/seapagan/cogitus/compare/0.4.1...0.4.2.diff) | [`Patch`](https://github.com/seapagan/cogitus/compare/0.4.1...0.4.2.patch)

## [0.4.1](https://github.com/seapagan/cogitus/releases/tag/0.4.1) (February 13, 2026)

**New Features**

- Remove sqliter fk-cache workaround and use eager loading ([#17](https://github.com/seapagan/cogitus/pull/17)) by [seapagan](https://github.com/seapagan)

**Testing**

- Add tests for idea repo group hydration branches ([#16](https://github.com/seapagan/cogitus/pull/16)) by [seapagan](https://github.com/seapagan)

**GitHub Actions**

- Enable renovate bot and github action to update req*.txt ([#14](https://github.com/seapagan/cogitus/pull/14)) by [seapagan](https://github.com/seapagan)

[`Full Changelog`](https://github.com/seapagan/cogitus/compare/0.4.0...0.4.1) | [`Diff`](https://github.com/seapagan/cogitus/compare/0.4.0...0.4.1.diff) | [`Patch`](https://github.com/seapagan/cogitus/compare/0.4.0...0.4.1.patch)

## [0.4.0](https://github.com/seapagan/cogitus/releases/tag/0.4.0) (February 13, 2026)

**New Features**

- Add CLI subcommands for list, export, and delete ([#11](https://github.com/seapagan/cogitus/pull/11)) by [seapagan](https://github.com/seapagan)
- Improve idea form initial focus and persisted edit cursor modes ([#8](https://github.com/seapagan/cogitus/pull/8)) by [seapagan](https://github.com/seapagan)
- Improve y-copy behavior for rendered idea selection ([#6](https://github.com/seapagan/cogitus/pull/6)) by [seapagan](https://github.com/seapagan)
- Improve idea form layout on small screens ([#5](https://github.com/seapagan/cogitus/pull/5)) by [seapagan](https://github.com/seapagan)

**Documentation**

- Add mkdocs documentation site ([#10](https://github.com/seapagan/cogitus/pull/10)) by [seapagan](https://github.com/seapagan)
- Organize TODO items into thematic sections ([#7](https://github.com/seapagan/cogitus/pull/7)) by [seapagan](https://github.com/seapagan)

[`Full Changelog`](https://github.com/seapagan/cogitus/compare/0.3.0...0.4.0) | [`Diff`](https://github.com/seapagan/cogitus/compare/0.3.0...0.4.0.diff) | [`Patch`](https://github.com/seapagan/cogitus/compare/0.3.0...0.4.0.patch)

## [0.3.0](https://github.com/seapagan/cogitus/releases/tag/0.3.0) (February 11, 2026)

**New Features**

- Add idea groups with tree navigation, safe DB backfill, and responsive edit modal ([#3](https://github.com/seapagan/cogitus/pull/3)) by [seapagan](https://github.com/seapagan)

[`Full Changelog`](https://github.com/seapagan/cogitus/compare/0.2.0...0.3.0) | [`Diff`](https://github.com/seapagan/cogitus/compare/0.2.0...0.3.0.diff) | [`Patch`](https://github.com/seapagan/cogitus/compare/0.2.0...0.3.0.patch)

## [0.2.0](https://github.com/seapagan/cogitus/releases/tag/0.2.0) (February 08, 2026)

**New Features**

- Add clipboard copy support with y key ([#1](https://github.com/seapagan/cogitus/pull/1)) by [seapagan](https://github.com/seapagan)

**Documentation**

- License the project under the MIT License ([#2](https://github.com/seapagan/cogitus/pull/2)) by [seapagan](https://github.com/seapagan)

[`Full Changelog`](https://github.com/seapagan/cogitus/compare/0.1.0...0.2.0) | [`Diff`](https://github.com/seapagan/cogitus/compare/0.1.0...0.2.0.diff) | [`Patch`](https://github.com/seapagan/cogitus/compare/0.1.0...0.2.0.patch)

## [0.1.0](https://github.com/seapagan/cogitus/releases/tag/0.1.0) (February 07, 2026)

Initial Release, basic MVP.

---
*This changelog was generated using [github-changelog-md](http://changelog.seapagan.net/) by [Seapagan](https://github.com/seapagan)*

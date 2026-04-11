# Ideas, Groups, and Tags

## Idea

An idea is the core record in Cogitus and contains:

- Title
- Body (Markdown text)
- Group
- Tags
- Created/updated timestamps

- Ideas can be renamed directly from the main screen with `r`.

## Groups

- Ideas are displayed in the left tree by group.
- New groups can be created with `g`.
- A selected group can be renamed with `r`.
- Deleting a group uses `G` (Shift+g).
- The configured default group cannot be deleted.
- The configured default group cannot be renamed.

!!! note
    The default group name is configurable with `default_group_name`
    in `config.toml` (default: `"default"`).

!!! note
    New idea group preselection is configurable via
    `new_idea_group_mode` in `config.toml`.
    Use `"contextual"` to seed from the left tree selection, or
    `"default_group"` to always start from default-group behavior.

## Tags

- Tags are entered as comma-separated values in the idea form.
- Tags are normalized by the service layer.
- Search can match against tag names as well as title/body.
- Clicking a tag above the idea body opens a `tag:<name>` search.

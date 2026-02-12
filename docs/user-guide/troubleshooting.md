# Troubleshooting

## Clipboard Copy Doesn’t Work

1. Verify terminal OSC 52 support.
2. If using tmux, set:
   - `set -g set-clipboard on`
3. Install fallback clipboard tools (`xclip`/`xsel`/`pbcopy`) where needed.

## `y` Copies Full Body Instead of Selection

In rendered Markdown view, some terminal/context combinations do not expose
selection state to Textual. In that case, `y` intentionally falls back to full
idea-body copy.

## App Starts But No Ideas Appear

- Create a new idea with `n`.
- Ensure search is cleared (`/`, clear text, `Esc`).

## Database Path and Local State

Cogitus uses a local SQLite database and local config state. If behavior seems
unexpected after testing, verify you are running with the intended user/profile
and local filesystem context.

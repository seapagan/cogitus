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

## Remote API Startup Fails

If Cogitus cannot reach the remote API during startup, it shows a recovery
dialog with these options:

- Retry the remote connection.
- Continue with cached remote data in read-only mode.
- Switch to local mode for the current session.

Cached remote mode changes the title to `Cogitus [remote: offline]` and blocks
mutating actions until the API is reachable again.

## Remote Mode Looks Stale or Read-Only

- Confirm the API server is running and reachable at `remote_api_base_url`.
- Check that `remote_api_username` and `remote_api_password` are correct.
- If the title shows `Cogitus [remote: offline]`, you are using cached remote
  data and write actions are intentionally disabled.
- Once the API is reachable again, Cogitus retries sync and restores normal
  remote mode automatically.

## Remote Clone Fails

If `Clone Remote To Local` fails:

- Confirm the remote API is configured in backend settings.
- Confirm the remote API server is reachable.
- Re-check `remote_api_username` and `remote_api_password`.
- If you expected the clone to update your remote session immediately, remember
  that clone writes into the normal local database, not the remote cache.
- If you started the clone from remote mode, you may still be in remote mode
  after success unless you choose `Use Local` in the post-clone prompt.

## Database Path and Local State

Cogitus uses a local SQLite database and local config state. If behavior seems
unexpected after testing, verify you are running with the intended user/profile
and local filesystem context.

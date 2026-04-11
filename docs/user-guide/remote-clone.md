# Clone Remote To Local

Cogitus can copy a full remote snapshot into your normal local database.

This is a destructive operation:

- It overwrites the existing local database contents.
- It does not modify the remote server.
- It does not replace the remote cache database used by normal remote mode.

## When To Use It

Remote-to-local clone is useful when you want to:

- seed a fresh local database from a remote server
- take a current remote copy and then continue working locally
- recover your local database from a known-good remote snapshot

## Requirements

Before cloning, make sure:

- the remote API is configured in Cogitus
- the remote API server is reachable
- the remote API credentials are valid

The clone action can run from either local mode or remote mode, as long as the
remote API settings are present.

## Start a Clone

1. Open the command palette with `Ctrl+P`.
2. Run `Clone Remote To Local`.
3. Confirm the destructive overwrite prompt.

Cogitus then:

1. downloads a full snapshot from the remote API
2. opens the local database target
3. replaces local groups, tags, ideas, and search data from that snapshot

## Clone Progress

During the operation, Cogitus shows a progress dialog with these stages:

- `Download`
- `Groups`
- `Tags`
- `Ideas`

The download stage completes first. The remaining stages reflect snapshot
application into the local database.

## Which Database Gets Replaced?

The clone target is the normal local database:

- by default: `~/.config/cogitus/cogitus.db`
- if you launched Cogitus with an explicit local database path, that file is
  used instead

This is different from the remote cache database, which normally lives at:

- `~/.config/cogitus/cogitus-remote-cache.db`

In other words, cloning gives you a local-mode database populated from the
remote server. It does not rewrite the remote server and it does not just
refresh the remote cache.

## What Gets Preserved?

The clone replaces the main local data with the remote snapshot, but Cogitus
keeps editor cursor positions for ideas that still exist after the clone.

If an idea only exists locally and is not present in the remote snapshot, that
idea is removed along with its cursor state.

## Behavior In Local Mode

If you start the clone while already using local mode:

- Cogitus replaces the local database
- the visible idea list refreshes after success
- you stay in local mode

## Behavior In Remote Mode

If you start the clone while using remote mode:

- Cogitus still writes into the normal local database, not the remote cache
- your current session continues using the remote backend after the clone
- Cogitus can optionally prompt you to switch the current session into local
  mode

If the prompt appears:

- `Stay Remote` keeps the current session on the remote backend
- `Use Local` switches the current session to local mode

Switching to local mode here is a session action. Your persisted backend
configuration remains whatever you last saved in backend settings.

## `prompt_after_clone`

The `prompt_after_clone` setting controls whether Cogitus asks you to switch to
local mode after a successful clone started from remote mode.

- `true` (default): show the `Stay Remote` / `Use Local` prompt
- `false`: keep the session in remote mode and just show a success message

See [Settings](settings.md) for the full setting reference.

## Failure Behavior

If the clone fails:

- Cogitus shows the error in a notification
- the local database is not left half-replaced if snapshot application fails
- the remote server is unchanged

Typical failure causes:

- remote API is not configured
- remote API is unreachable
- authentication fails
- the remote snapshot is inconsistent or invalid

## Related Pages

- [API](api.md)
- [Settings](settings.md)
- [Troubleshooting](troubleshooting.md)

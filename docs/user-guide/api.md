# API

Cogitus includes an optional FastAPI server that exposes ideas, groups, and
tags over HTTP.

!!! warning
    This API is still a work in progress. Basic authentication is now
    available, but the current design is still single-user, SQLite-backed, and
    intended for trusted or local environments. It is not yet hardened for
    serious multi-user or internet-facing deployment.

## Install

Install the API support extra before trying to serve it:

```bash
pip install cogitus[api]
```

If you are working from a local checkout, the existing development environment
already includes the API dependencies.

You only need the `api` extra on the machine that will *serve* the API.
Using the normal Cogitus TUI against an already running remote server does not
require the FastAPI server dependencies.

## Run the Server

Start the server with:

```bash
cogitus api serve
```

By default this binds to `127.0.0.1:8000`, so it is only reachable locally.

Common options:

```bash
cogitus api serve --host 127.0.0.1 --port 8000
cogitus api serve --db-path /path/to/cogitus.db
cogitus api serve --reload
```

Use `--db-path` to point the API at a specific Cogitus SQLite database file.

## Configure Authentication

Before using the protected API routes, configure the single API user:

```bash
cogitus api set-auth --username your-username
```

This command will prompt for the password and confirmation, hash the password,
and save the auth settings in the Cogitus config file.

You can use any username you want here. If you omit `--username`, Cogitus will
prompt for it interactively.

To rotate the JWT signing secret at the same time:

```bash
cogitus api set-auth --username your-username --rotate-secret
```

## Authentication Flow

The API uses a bearer token flow.

1. Configure credentials with `cogitus api set-auth`.
2. Request a token from `/api/v1/auth/token`.
3. Send that token in the `Authorization: Bearer ...` header.

Fetch a token:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/auth/token \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=your-username&password=your-password"
```

Example token response:

```json
{
  "access_token": "eyJhbGciOi...",
  "token_type": "bearer"
}
```

Access tokens expire. By default, Cogitus issues tokens valid for `30`
minutes.

You can change the lifetime with the `api_auth_token_expire_minutes` setting in
the Cogitus config file. After a token expires, request a new one from
`/api/v1/auth/token`.

Use the token against a protected route:

```bash
curl http://127.0.0.1:8000/api/v1/ideas \
  -H "Authorization: Bearer eyJhbGciOi..."
```

When the Cogitus TUI is using remote mode, it handles this token flow for you.
If the access token expires, the client reauthenticates once and retries the
request automatically.

## Use Cogitus with a Remote Server

Before switching a local Cogitus app into remote mode, make sure the remote API
server is already configured and running.

Recommended order:

1. On the server machine, install the API extra with `pip install cogitus[api]`
   if needed.
2. Point the server at the correct SQLite file with `cogitus api serve
   --db-path ...` if you are not using the default database.
3. Configure API auth with `cogitus api set-auth`.
4. Start the API with `cogitus api serve`.
5. On the client machine, open Cogitus and press `Ctrl+P` to open the command
   palette.
6. Run `Backend settings`.
7. Choose `Remote API` and enter the server URL, username, and password.
8. Save the settings.

Cogitus also keeps the existing hidden `c` shortcut for this dialog, but the
command palette is now the primary entry point.

After saving, the app title changes to `Cogitus [remote]`. Local mode shows
`Cogitus [local]`.

### Remote Mode Behavior

- Cogitus keeps a local cache database at
  `~/.config/cogitus/cogitus-remote-cache.db` while in remote mode.
- It syncs the cache when the app starts, when the main screen regains focus or
  resumes, and every 60 seconds while the main screen is active.
- Opening edit-style flows refreshes from the server first, so you usually
  start from the latest remote copy.
- Background syncing is paused while a modal screen is open.
- Writes update the local cache immediately after a successful API request.

### Conflict Handling

- Remote idea updates use optimistic locking based on the idea's last known
  `updated_at` value.
- If another client changes the same idea before you save, the server returns
  `409 Conflict`.
- Today Cogitus does not attempt automatic merges. Reopen or retry the edit
  after reviewing the latest remote version.

### Current Caveats

!!! warning
    Remote mode is still intentionally conservative:

    - The server is still single-user and SQLite-backed.
    - The client stores the remote API URL, username, and password in the
      normal Cogitus config file for now.
    - This is suitable for trusted, light-use environments today, not for
      hardened internet-facing deployment.

## Available Routes

The current API exposes:

- `/api/v1/auth/token` for bearer-token login

Protected CRUD routes for:

- `/api/v1/ideas`
- `/api/v1/groups`
- `/api/v1/tags`

It also exposes:

- `/health` for a simple health check
- `/docs` for the interactive FastAPI docs
- `/openapi.json` for the OpenAPI schema

## Example Output

Health check:

```bash
curl http://127.0.0.1:8000/health
```

```json
{"status":"ok"}
```

List ideas:

```bash
curl http://127.0.0.1:8000/api/v1/ideas \
  -H "Authorization: Bearer eyJhbGciOi..."
```

```json
[
  {
    "pk": 1,
    "created_at": 1743157200,
    "updated_at": 1743157200,
    "title": "Ship FastAPI API",
    "body": "Expose ideas, groups, and tags over HTTP.",
    "group": {
      "pk": 1,
      "created_at": 1743157200,
      "updated_at": 1743157200,
      "name": "default"
    },
    "tags": [
      {
        "pk": 1,
        "created_at": 1743157200,
        "updated_at": 1743157200,
        "name": "api"
      }
    ]
  }
]
```

## Notes

- `/api/v1/ideas`, `/api/v1/groups`, and `/api/v1/tags` now require a valid
  bearer token.
- The ideas list endpoint also accepts `limit`, `offset`, and `query`
  parameters.
- The API uses the same SQLite-backed data model as the local app.
- Server auth configuration is currently stored in the normal Cogitus config
  file.
- This is still intended for light use today, not heavy multi-user deployment.

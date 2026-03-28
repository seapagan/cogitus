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
- Auth configuration is currently stored in the normal Cogitus config file.
- This is still intended for light use today, not heavy multi-user deployment.

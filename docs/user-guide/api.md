# API

Cogitus includes an optional FastAPI server that exposes ideas, groups, and
tags over HTTP.

!!! warning
    This API is still a work in progress. There is currently no
    authentication, authorization, or other hardening for untrusted networks.
    Use it only in trusted or local environments for now.

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

## Available Routes

The current API exposes CRUD routes for:

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
curl http://127.0.0.1:8000/api/v1/ideas
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

- The ideas list endpoint also accepts `limit`, `offset`, and `query`
  parameters.
- The API uses the same SQLite-backed data model as the local app.
- This is intended for light use today, not heavy multi-user deployment.

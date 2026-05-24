# CLI Reference

Cogitus provides CLI subcommands for scripting and automation alongside the TUI.

## Default Behavior

Running `cogitus` with no arguments launches the TUI:

```bash
cogitus
```

Show the installed version:

```bash
cogitus --version
```

## List Ideas

```bash
cogitus list                      # Simple format (default)
cogitus list --format json        # JSON array
cogitus list --format table       # Rich table
cogitus list --query "python"     # Filter by search
cogitus list --query "tag:python" # Filter by tag
cogitus list --query "group:backend and tag:api"
cogitus list --limit 10           # Limit results
```

### Output Formats

| Format | Description |
|--------|-------------|
| `simple` | One line per idea: `[1] Title [tag1] [tag2]` |
| `json` | Full JSON array with all fields |
| `table` | Rich table with ID, Title, Group, Updated |

## Export Ideas

```bash
cogitus export                    # All ideas as JSON
cogitus export 42                 # Single idea as JSON
cogitus export --format markdown  # All ideas as markdown
cogitus export 42 -f markdown     # Single idea as markdown
```

## Delete Ideas

```bash
cogitus delete 42                 # Prompts for confirmation
cogitus delete 42 --force         # Skip confirmation
```

## Serve the API

```bash
cogitus api serve
cogitus api serve --host 127.0.0.1 --port 8000
cogitus api serve --db-path /path/to/cogitus.db
```

This serves the normal REST API only. It does not expose the MCP endpoint.

## Configure API Auth

```bash
cogitus api set-auth --username your-username
cogitus api set-auth --username your-username --rotate-secret
```

The command prompts for the password, stores a password hash in config, and can
optionally rotate the JWT signing secret. You can use any username you want, or
omit `--username` and be prompted for it.

See the [API guide](api.md) for routes, example output, remote-mode setup from
the TUI, and current warnings.

## Serve MCP

```bash
cogitus mcp token
cogitus mcp token --rotate-secret
cogitus mcp serve
cogitus mcp serve --host 127.0.0.1 --port 9000
cogitus mcp serve --db-path /path/to/cogitus.db
```

`cogitus mcp token` prints a long-lived `Bearer ...` token for MCP clients and
creates the MCP signing secret if it does not already exist. `--rotate-secret`
replaces that secret before printing a new token, which invalidates older MCP
tokens.

`cogitus mcp serve` exposes the MCP endpoint at `/mcp` only. It uses separate
MCP auth and does not expose the normal REST API routes.

## Help

```bash
cogitus --help
cogitus list --help
cogitus export --help
cogitus delete --help
cogitus api serve --help
cogitus api set-auth --help
cogitus mcp token --help
cogitus mcp serve --help
```

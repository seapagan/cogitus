# CLI Reference

Cogitus provides CLI subcommands for scripting and automation alongside the TUI.

## Default Behavior

Running `cogitus` with no arguments launches the TUI:

```bash
cogitus
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

## Help

```bash
cogitus --help
cogitus list --help
cogitus export --help
cogitus delete --help
```

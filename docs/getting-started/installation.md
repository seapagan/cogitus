# Installation

## Requirements

- Python 3.10+
- A terminal that can run Textual applications

## Recommended Install (uv tool)

[uv](https://docs.astral.sh/uv/) is a modern and very fast tool to manage python
projects and dependencies.

```bash
uv tool install cogitus
```

or use `pipx`

```bash
pipx install cogitus
```

Finally, if you just prefer to use `pip`:

```bash
pip install cogitus
```

## API Server Install

If you want this machine to *serve* the optional Cogitus HTTP API, install the
API extra:

```bash
pip install cogitus[api]
```

You only need this extra on the machine running `cogitus api serve`. A normal
Cogitus TUI connecting to an already running remote server does not need the
FastAPI server dependencies.

## Run

```bash
cogitus
```

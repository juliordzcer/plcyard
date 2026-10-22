# Contributing

Contributions are welcome. Open an issue first for anything large.

## Set up

```bash
git clone https://github.com/juliordzcer/plcyard.git
cd plcyard
python3 -m venv .venv
.venv/bin/pip install -e . pytest pytest-qt mkdocs
.venv/bin/python -m pytest
```

## Layout

| Path | Holds |
| --- | --- |
| `plcyard/core/` | The PLC: memory, instructions, scan engine, ST compiler, FBD runner, PID |
| `plcyard/sims/` | Simulation models (no UI) |
| `plcyard/ui/` | The window, editors and simulation views (PySide6) |
| `plcyard/formats/` | Project files (`.plcy`) and import of older files |
| `plcyard/grader.py` | Exercise checks |
| `plcyard/data/` | Exercises, solutions and examples |
| `docs/wiki/` | This wiki |

## The reference pages

The pages under **Reference** are generated from the code (instructions, FBD blocks, ST functions,
simulation docstrings). After changing any of them run:

```bash
python -m plcyard.docgen
```

A test fails while the generated pages are out of date. Preview the wiki with `mkdocs serve`.

## The web version

`web/` holds the page and `plcyard/webapp.py` the Python it runs in the browser (Pyodide); nothing
in either may import Qt. Build it with `python -m plcyard.webbuild OUT_DIR` and serve `OUT_DIR`
with any static web server (`python -m http.server`). The site is the wiki with the web version in
`app/`:

```bash
mkdocs build -d SITE && python -m plcyard.webbuild SITE/app
```

## Rules

- Every fix comes with a test.
- No vendor names in anything the user sees.
- Keep the core free of UI imports.

# Read Before Guessing

## APIs and Class Attributes

Before accessing any class attribute or method in exploratory/debugging code,
**read the class definition first**. Never guess attribute names based on
third-party library conventions — project-specific classes often diverge.

1. Use `Grep` or `Read` to find the class definition before accessing attributes.
2. If the first access fails with `AttributeError`, **read the class source** —
   do not try another guess.

## JSON and Tool Output

Project tools and scripts produce JSON with **non-standardized schemas** that vary
between tools. Before writing inline code to parse JSON results:

1. **Read the JSON file first** — use `Read` or `head -20` to inspect actual key names.
2. Or use the tool's built-in formatting options (e.g. `--format markdown`) if available.
3. Never guess JSON key names — the first access must be a schema inspection,
   not a data query.

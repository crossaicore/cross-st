# st-cat — Print story container fields to stdout

Prints fields from a story container to stdout. Useful for piping into other tools or shell scripts. Defaults to printing the selected report’s authored prompt if no field flag is given. For an update output, this is its update request. Select the report with `-s N` (default: 1).

## Examples

```bash
st-cat subject.json                 # print the prompt (default)
st-cat -t subject.json              # print title of story 1
st-cat --markdown -s 3 subject.json # print markdown of story 3
st-cat -f 2 -s 1 subject.json       # print fact-check report 2 from story 1
st-cat --text -s 2 subject.json     # print plain text body of story 2
st-cat --prompt -s 2 subject.json   # print report 2's authored prompt or update request
```

## Options

| Option | Description |
|--------|-------------|
| `-s N`, `--story N` | Story number to read (integer), default: `1` |
| `-f N`, `--fact N` | Fact-check report number to read (integer); prints the specified fact-check instead of a story |
| `--title`, `-t` | Print the story title |
| `--text` | Print the plain-text story body |
| `--markdown` | Print the story markdown |
| `--hashtags` | Print the story hashtags |
| `--spoken` | Print the story spoken-text variant |
| `--prompt` | Print the selected report’s authored prompt or update request through its raw association; older reports can use a common authored prompt shared by all raw entries. If no unambiguous prompt is available, prints “No prompt found in container.” (**default** if no other field specified) |
| `-v`, `--verbose` | Verbose output |
| `-q`, `--quiet` | Minimal output |

**Related:** [st-ls](st-ls) · [st-edit](st-edit) · [Container Format](Container-Format)

---

## For developers

Reads a single story (or fact-check) from a .json container and prints the
requested field(s) to standard output.  Useful for piping story text into
other tools or shell scripts.

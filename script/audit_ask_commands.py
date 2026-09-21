#!/usr/bin/env python3
"""Audit every installed command against its wiki page without importing CLI code.

Literal argparse declarations are evidence of option names, not proof of runtime
semantics. st-man's manual parser is checked separately. Output is a review
queue, not an accuracy certificate. Cross-command examples can explain extras.
"""
import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def command_names():
    # Avoid requiring tomllib on supported Python 3.10.
    text = (ROOT / 'pyproject.toml').read_text()
    section = text.split('[project.scripts]', 1)[1].split('\n[', 1)[0]
    return re.findall(r'^(st(?:-[\w-]+)?)\s*=', section, re.M)


def arguments(name):
    tree = ast.parse((ROOT / 'cross_st' / f'{name}.py').read_text())
    rows = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr == 'add_argument'):
            continue
        names = [a.value for a in node.args if isinstance(a, ast.Constant) and isinstance(a.value, str)]
        if not names:
            raise ValueError(f'{name}:{node.lineno}: dynamic argument requires review')
        kw = {k.arg: k.value for k in node.keywords}
        help_node = kw.get('help')
        if isinstance(help_node, ast.Attribute) and help_node.attr == 'SUPPRESS':
            continue  # internal/unsupported options are not public help knowledge
        if isinstance(help_node, ast.Constant) and isinstance(help_node.value, str):
            description = help_node.value
        elif isinstance(help_node, ast.JoinedStr):
            description = ''.join(v.value if isinstance(v, ast.Constant) else '[configured value]'
                                  for v in help_node.values)
        else:
            description = 'Consult command help for details.'
        rows.append((names, description))
    if name == 'st-man':
        rows = [(['command'], 'Command name, or faq; omit to list commands.'),
                (['--web'], 'Open the corresponding wiki page in a browser.'),
                (['--doc'], 'Print the source docstring instead of the formatted man page.')]
    return rows


def command_reference():
    out = ['## Current command arguments', '',
           'Generated from the current CLI argument declarations. These establish option names; '
           'the wiki explains workflows. Dynamic values depend on configuration. '
           'Changelog entries describe historical releases, not necessarily current behavior.', '']
    for name in command_names():
        out += [f'### {name}', '', f'Source: `cross_st/{name}.py`.', '']
        for names, description in arguments(name):
            out.append('- ' + ', '.join(f'`{n}`' for n in names) + ': ' + description.replace('\n', ' '))
        out.append('')
    return '\n'.join(out)


def coverage_report():
    out = ['# st-ask command coverage audit', '',
           'Static comparison of every entry point with its own wiki page. Missing means absent '
           'from that page; extra mentions may be valid references to other commands. '
           'This does not certify examples, defaults, side effects, or runtime behavior.', '',
           '| Command | Declared long options | Missing from own wiki page | Other option mentions to review |',
           '|---|---:|---|---|']
    for name in command_names():
        flags = {n for names, _ in arguments(name) for n in names if n.startswith('--')}
        path = ROOT / 'docs/wiki' / f'{name}.md'
        documented = set(re.findall(r'--[a-z][a-z0-9_-]*', path.read_text())) if path.exists() else set()
        fmt = lambda items: ', '.join(f'`{n}`' for n in sorted(items)) or '—'
        out.append(f'| {name} | {len(flags)} | {fmt(flags - documented)} | {fmt(documented - flags)} |')
    return '\n'.join(out) + '\n'


if __name__ == '__main__':
    print(coverage_report(), end='')

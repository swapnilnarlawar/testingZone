"""
Shell Config Parser
Extracts variable definitions from .sh config files.
No dependencies beyond stdlib.
"""
from __future__ import annotations
import re
from dataclasses import dataclass, field

SHEBANG     = re.compile(r'^#!(\/usr\/bin\/env\s+)?ba?sh')
VAR_QUOTED  = re.compile(r'''^(?:export\s+)?([A-Za-z_]\w*)=(['"])(.*?)\2(?:\s*#.*)?$''')
VAR_PLAIN   = re.compile(r'''^(?:export\s+)?([A-Za-z_]\w*)=(.+?)(?:\s*#.*)?$''')
PLACEHOLDER = re.compile(r'TODO|PLACEHOLDER|<YOUR_|<ENTER_|^<[A-Z]')


@dataclass
class ShellVariable:
    name: str
    value: str
    comment: str = ""

    @property
    def needs_input(self) -> bool:
        return bool(PLACEHOLDER.search(self.value))


def parse(content: str) -> list[ShellVariable]:
    """Parse shell file content, return list of variable definitions."""
    variables: list[ShellVariable] = []
    pending_comments: list[str] = []

    for line in content.splitlines():
        stripped = line.strip()

        if not stripped or SHEBANG.match(stripped):
            if not stripped.startswith('#'):
                pending_comments = []
            continue

        if stripped.startswith('#'):
            text = stripped.lstrip('#').strip()
            if text:
                pending_comments.append(text)
            continue

        m = VAR_QUOTED.match(stripped) or VAR_PLAIN.match(stripped)
        if m:
            name  = m.group(1)
            value = m.group(3) if m.lastindex >= 3 else m.group(2)
            variables.append(ShellVariable(
                name=name,
                value=value.strip(),
                comment=' '.join(pending_comments).strip(),
            ))

        # Reset comments on any non-comment line (variable or noise)
        pending_comments = []

    return variables

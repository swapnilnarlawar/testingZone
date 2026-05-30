"""
Variable Differ
Computes added / changed / removed / unchanged between two variable lists.
"""
from __future__ import annotations
from dataclasses import dataclass
from .parser import ShellVariable


@dataclass
class DiffResult:
    added:     list[ShellVariable]
    removed:   list[ShellVariable]
    changed:   list[tuple[ShellVariable, str]]   # (new_var, old_value)
    unchanged: list[ShellVariable]

    @property
    def has_changes(self) -> bool:
        return bool(self.added or self.removed or self.changed)

    def summary(self) -> str:
        return (
            f"+{len(self.added)} new  "
            f"~{len(self.changed)} changed  "
            f"-{len(self.removed)} removed  "
            f"={len(self.unchanged)} unchanged"
        )


def diff(old_vars: list[ShellVariable], new_vars: list[ShellVariable]) -> DiffResult:
    old_map = {v.name: v for v in old_vars}
    new_map = {v.name: v for v in new_vars}

    added     = [v for v in new_vars if v.name not in old_map]
    removed   = [v for v in old_vars if v.name not in new_map]
    changed   = [(v, old_map[v.name].value)
                 for v in new_vars
                 if v.name in old_map and old_map[v.name].value != v.value]
    unchanged = [v for v in new_vars
                 if v.name in old_map and old_map[v.name].value == v.value]

    return DiffResult(added=added, removed=removed, changed=changed, unchanged=unchanged)

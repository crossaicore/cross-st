"""tests/test_agt9_shim_removed.py — AGT-9 removal coverage (cross-st 0.12.0).

The pre-AGT-9 back-compat surface was removed in 0.12.0:

  * the ``cross_st._alias_admin`` module shim,
  * the legacy symbol aliases (``add_alias``, ``list_aliases``,
    ``AliasError`` …) that lived at the bottom of ``_agent_admin``,
  * the hidden ``st-admin`` CLI flags ``--add-alias`` / ``--remove-alias`` /
    ``--list-aliases``.

These tests pin the removal (inverted from the one-release back-compat
guarantee) so the shims can never silently creep back.
"""
from __future__ import annotations

import importlib
import subprocess
import sys
from pathlib import Path

import pytest

_CROSS_ST = str(Path(__file__).parent.parent / "cross_st")
if _CROSS_ST not in sys.path:
    sys.path.insert(0, _CROSS_ST)


def test_alias_admin_module_removed():
    """The deprecated cross_st._alias_admin shim must be gone."""
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("cross_st._alias_admin")


def test_agent_admin_still_importable():
    """Removing the shim must not disturb the canonical module."""
    agent_admin = importlib.import_module("_agent_admin")
    assert hasattr(agent_admin, "add_agent")
    assert hasattr(agent_admin, "list_agents")


@pytest.mark.parametrize(
    "legacy_name",
    [
        "aliases_file_path", "read_alias_file", "write_alias_file",
        "add_alias", "remove_alias", "edit_alias_model", "list_aliases",
        "format_alias_table", "AliasError",
    ],
)
def test_legacy_symbol_aliases_removed(legacy_name):
    """The pre-AGT-9 symbol aliases are no longer exported by _agent_admin."""
    agent_admin = importlib.import_module("_agent_admin")
    assert not hasattr(agent_admin, legacy_name), (
        f"{legacy_name} should have been removed in 0.12.0"
    )


@pytest.mark.parametrize("flag", ["--add-alias", "--remove-alias", "--list-aliases"])
def test_hidden_alias_flags_rejected(flag):
    """st-admin must reject the removed pre-AGT-9 CLI flags."""
    proc = subprocess.run(
        [sys.executable, str(Path(_CROSS_ST) / "st-admin.py"), flag, "x"],
        capture_output=True, text=True, timeout=15,
    )
    assert proc.returncode != 0
    assert "unrecognized arguments" in proc.stderr, proc.stderr


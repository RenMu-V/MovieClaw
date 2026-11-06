"""Dependency-free regression checks for the self-built deployment policy."""
import ast
import os
from pathlib import Path
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def function(path, name, namespace):
    tree = ast.parse((ROOT / path).read_text())
    node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name)
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(path), 'exec'), namespace)
    return namespace[name]


class SelfBuildPolicy(unittest.TestCase):
    def test_official_updates_disabled_even_in_docker(self):
        f = function('src/movieclaw_api/services/app_update.py', '_runtime_version', {'os': os})
        with patch.dict(os.environ, MOVIECLAW_DISABLE_OFFICIAL_UPDATES='1', MOVIECLAW_RUNTIME_VERSION='1'):
            self.assertIsNone(f())
        with patch.dict(os.environ, MOVIECLAW_DISABLE_OFFICIAL_UPDATES='0', MOVIECLAW_RUNTIME_VERSION='1'):
            self.assertEqual(f(), 1)

    def test_no_automatic_plugin_dependency_download(self):
        calls = []
        f = function('src/movieclaw_api/services/plugin_deps.py', 'resume', {
            'Any': object, 'os': os, 'pending_installs': lambda s: calls.append(s) or [],
        })
        with patch.dict(os.environ, MOVIECLAW_DISABLE_PLUGIN_AUTO_INSTALL='1'):
            f(None, object())
        self.assertEqual(calls, [])


if __name__ == '__main__':
    unittest.main()

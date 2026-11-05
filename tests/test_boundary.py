"""The GUI boundary: only app/qtrender (and the app/main.py entry point) may use a GUI toolkit.

Everything else (core, prices, indicators, strategy, search) must run, and be testable, without PySide6.
"""
import ast
import subprocess
import sys
from pathlib import Path

import pytest

APP = Path(__file__).resolve().parents[1] / 'app'
HEADLESS_PACKAGES = ['core', 'prices', 'indicators', 'strategy', 'search', 'portfolio', 'learn',
                     'company']
GUI_MODULES = ('PySide6', 'pyqtgraph', 'qtrender', 'tkinter', 'matplotlib')


def _imports(path: Path) -> set[str]:
    found = set()
    for node in ast.walk(ast.parse(path.read_text(encoding='utf-8'))):
        if isinstance(node, ast.Import):
            found.update(alias.name.split('.')[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            found.add(node.module.split('.')[0])
    return found


@pytest.mark.parametrize('package', HEADLESS_PACKAGES)
def test_headless_packages_do_not_import_a_gui_toolkit(package):
    offenders = {}
    for path in (APP / package).rglob('*.py'):
        used = _imports(path) & set(GUI_MODULES)
        if used:
            offenders[str(path.relative_to(APP))] = sorted(used)
    assert not offenders, f'GUI imports outside qtrender/: {offenders}'


def test_only_qtrender_and_main_use_qt():
    offenders = []
    for path in APP.rglob('*.py'):
        relative = path.relative_to(APP)
        if relative.parts[0] == 'qtrender' or relative.name == 'main.py':
            continue
        if _imports(path) & set(GUI_MODULES):
            offenders.append(str(relative))
    assert not offenders, offenders


def test_core_imports_with_the_toolkit_blocked():
    """Import every core module in a fresh interpreter where PySide6 and pyqtgraph cannot be imported."""
    modules = ['.'.join(path.relative_to(APP).with_suffix('').parts) for path in (APP / 'core').rglob('*.py')
               if path.stem != '__init__']
    assert len(modules) > 15, modules  # the glob really found the feature packages
    code = (
        "import sys\n"
        "for name in ('PySide6', 'pyqtgraph'):\n"
        "    sys.modules[name] = None\n"  # makes `import PySide6` raise ImportError
        f"sys.path.insert(0, {str(APP)!r})\n"
        f"for module in {modules!r}:\n"
        "    __import__(module)\n"
    )
    result = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr

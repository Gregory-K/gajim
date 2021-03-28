
import sys
from importlib.abc import MetaPathFinder
from importlib.util import spec_from_file_location
from pathlib import Path


class GUIFinder(MetaPathFinder):

    def __init__(self, name, fallback=None):
        self._path = Path(__file__).parent.parent / name

        self._fallback_path = None
        if fallback is not None:
            self._fallback_path = Path(__file__).parent.parent / fallback

    def find_spec(self, fullname, _path, _target=None):
        if not fullname.startswith('gajim.gui'):
            return None

        _namespace, module_name = fullname.rsplit('.', 1)
        module_path = self._find_module(module_name)
        if module_path is None:
            return None

        spec = spec_from_file_location(fullname, module_path)

        return spec

    def _find_module(self, module_name):
        base_path = Path(self._path)

        fallback_base_path = None
        if self._fallback_path is not None:
            fallback_base_path = Path(self._fallback_path)

        module_path = base_path / module_name
        if module_path.is_dir():
            base_path = module_path
            if fallback_base_path is not None:
                fallback_base_path = fallback_base_path / module_name

            module_name = '__init__'

        module_path = base_path / f'{module_name}.py'
        if module_path.exists():
            return module_path

        module_path = base_path / f'{module_name}.pyc'
        if module_path.exists():
            return module_path

        if fallback_base_path is None:
            return None

        module_path = fallback_base_path / f'{module_name}.py'
        if module_path.exists():
            return module_path

        module_path = fallback_base_path / f'{module_name}.pyc'
        if module_path.exists():
            return module_path

        return None


def init(name, fallback=None):
    sys.meta_path.append(GUIFinder(name, fallback=fallback))

"""Load integration modules without importing Home Assistant."""

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys
from types import ModuleType


INTEGRATION_DIR = (
    Path(__file__).parents[1] / "custom_components" / "swissweather"
)
PACKAGE_NAME = "custom_components.swissweather"


def load_module(module_name: str):
    """Load a module from the integration package without executing __init__.py."""
    if "custom_components" not in sys.modules:
        custom_components = ModuleType("custom_components")
        custom_components.__path__ = [str(INTEGRATION_DIR.parent)]
        sys.modules["custom_components"] = custom_components

    if PACKAGE_NAME not in sys.modules:
        package = ModuleType(PACKAGE_NAME)
        package.__path__ = [str(INTEGRATION_DIR)]
        sys.modules[PACKAGE_NAME] = package

    qualified_name = f"{PACKAGE_NAME}.{module_name}"
    if qualified_name in sys.modules:
        return sys.modules[qualified_name]

    spec = spec_from_file_location(
        qualified_name, INTEGRATION_DIR / f"{module_name}.py"
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load {qualified_name}")

    module = module_from_spec(spec)
    sys.modules[qualified_name] = module
    spec.loader.exec_module(module)
    return module

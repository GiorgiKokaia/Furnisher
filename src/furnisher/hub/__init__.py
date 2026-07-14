"""Unified entry point (docs/08): one launcher that ties the layout editor and the furnish
app together. Pick or create a layout, then continue straight into furnishing."""

from furnisher.hub.hub import create_hub
from furnisher.hub.workspace import Workspace

__all__ = ["Workspace", "create_hub"]

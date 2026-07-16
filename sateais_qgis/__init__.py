"""SateAIs for QGIS — plugin entry point.

QGIS imports this package and calls ``classFactory(iface)`` to instantiate
the plugin.
"""

from __future__ import annotations


def classFactory(iface):
    """Required QGIS plugin factory hook.

    Args:
        iface: ``qgis.gui.QgisInterface`` instance provided by the host.

    Returns:
        An instance of :class:`SateAIsPlugin`.
    """
    from .plugin_main import SateAIsPlugin

    return SateAIsPlugin(iface)

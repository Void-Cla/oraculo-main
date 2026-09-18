from __future__ import annotations

import importlib


def test_reconcile_module_importable():
    mod = importlib.import_module("scripts.reconcile_orders")
    assert mod is not None

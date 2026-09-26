"""Dependency-light execution smoke test of all three Streamlit page bodies.

Uses a Streamlit rendering stub to exercise Python callbacks and Plotly figure
creation; this does not replace visual inspection in an installed Streamlit app.
"""
from __future__ import annotations

from pathlib import Path
import runpy
import sys
import types
import unittest
import importlib.util

ROOT = Path(__file__).resolve().parents[1]


class DisplayStub:
    def __init__(self, owner):
        self.owner = owner

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def __getattr__(self, name):
        return getattr(self.owner, name)


class DashboardSmokeTests(unittest.TestCase):
    @unittest.skipUnless(importlib.util.find_spec("plotly") is not None, "plotly optional dashboard dependency")
    def test_all_three_tabs_execute_on_validated_snapshot(self):
        s = types.ModuleType("streamlit")
        observed = {"tabs": None, "figures": 0, "tables": 0, "metrics": 0}
        dummy = DisplayStub(s)
        s.set_page_config = lambda **kwargs: None
        s.cache_data = lambda **kwargs: lambda fn: fn
        s.tabs = lambda labels: (observed.__setitem__("tabs", labels) or [dummy for _ in labels])
        s.columns = lambda count: [dummy for _ in range(count)]
        s.expander = lambda *args, **kwargs: dummy
        s.selectbox = lambda label, options, **kwargs: list(options)[0]
        s.checkbox = lambda *args, **kwargs: False
        s.plotly_chart = lambda fig, **kwargs: observed.__setitem__("figures", observed["figures"] + 1)
        s.dataframe = lambda frame, **kwargs: observed.__setitem__("tables", observed["tables"] + 1)
        s.metric = lambda *args, **kwargs: observed.__setitem__("metrics", observed["metrics"] + 1)
        s.stop = lambda: self.fail("Dashboard stopped unexpectedly")
        for name in ("title", "header", "subheader", "caption", "info", "warning", "error", "write", "markdown"):
            setattr(s, name, lambda *args, **kwargs: None)
        previous = sys.modules.get("streamlit")
        sys.modules["streamlit"] = s
        try:
            runpy.run_path(str(ROOT / "dashboard" / "app.py"), run_name="__main__")
        finally:
            if previous is None:
                sys.modules.pop("streamlit", None)
            else:
                sys.modules["streamlit"] = previous
        self.assertEqual(observed["tabs"], ["Efficiency benchmark", "Fleet activity", "Carrier comparisons"])
        self.assertGreaterEqual(observed["figures"], 4)
        self.assertGreaterEqual(observed["tables"], 3)
        self.assertEqual(observed["metrics"], 11)


if __name__ == "__main__":
    unittest.main()

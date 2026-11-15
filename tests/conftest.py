"""Test setup.

main.py imports tkinter and customtkinter at module level. The tests only exercise the non-GUI logic and never
create a window, so on machines without Tk or a display (CI runners, containers) those two modules are replaced
by tiny stand-ins before main.py is imported.
"""
import os
import sys
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def _stub_gui():
    for name in ("tkinter", "tkinter.filedialog", "tkinter.messagebox", "tkinter.ttk", "tkinter.font",
                 "customtkinter"):
        sys.modules[name] = types.ModuleType(name)
    tk = sys.modules["tkinter"]
    for sub in ("filedialog", "messagebox", "ttk", "font"):
        setattr(tk, sub, sys.modules[f"tkinter.{sub}"])

    class Widget:
        def __init__(self, *args, **kwargs):
            pass

        def configure(self, *args, **kwargs):
            pass

    ctk = sys.modules["customtkinter"]
    for cls in ("CTk", "CTkToplevel", "CTkLabel", "CTkButton", "CTkEntry", "CTkFrame", "CTkProgressBar"):
        setattr(ctk, cls, type(cls, (Widget,), {}))
    ctk.set_appearance_mode = ctk.set_default_color_theme = lambda *args, **kwargs: None


try:
    import customtkinter  # noqa: F401
    import tkinter  # noqa: F401
except ImportError:
    _stub_gui()


import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _never_touch_the_users_files(tmp_path, monkeypatch):
    """Every test runs against temp paths for the app's data files.

    A test once opened the real windscribe_results.db and called clear_db(), deleting a user's
    recorded results. Redirecting these for ALL tests makes that class of mistake impossible instead
    of relying on each test remembering to do it.
    """
    import main
    monkeypatch.setattr(main, "DB_FILE", str(tmp_path / "windscribe_results.db"))
    monkeypatch.setattr(main, "CONFIG_FILE", str(tmp_path / "config.json"))
    monkeypatch.setattr(main, "LOG_FILE", str(tmp_path / "autoscribe.log"))
    monkeypatch.setattr(main, "REPORTS_DIR", str(tmp_path / "reports"))

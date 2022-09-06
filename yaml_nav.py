"""
Main plugin module with sublime commands and listeners.
"""

import sublime
import sublime_plugin
import re
from functools import partial
from typing import (
    Any,
    List,
    Mapping,
    Optional,
)

from .lib import yaml_math


# Status key for sublime status bar
STATUS_BAR_ID = "yaml_nav"

# Filename with plugin settings
SETTINGS_FILE = "YamlNav.sublime-settings"

# Delay in milliseconds after which symbols will be updated on buffer modification
UPDATE_SYMBOLS_DEBOUNCE = 400

REMOVE_COLON_RE = re.compile(r"((?<=(^)):|((?<=(\.)):))")


def set_status(view, message: Optional[str] = None):
    """Display message in a status bar field for the given view.
    """
    if message:
        view.set_status(STATUS_BAR_ID, "YAML path: %s" % message)
    else:
        view.erase_status(STATUS_BAR_ID)


def is_yaml_view(view):
    """Check if the given view contains YAML code.
    """
    return view.score_selector(0, "source.yaml") > 0


def get_setting(key, default=None):
    return sublime.load_settings(SETTINGS_FILE).get(key, default)


class YamlNavListener(sublime_plugin.ViewEventListener):
    """Listen for file modification/cursor movement and maintain symbols for the view.
    """

    current_yaml_symbol = None
    symbols_update_scheduled = False
    yaml_symbols: List[yaml_math.Symbol] = []
    last_change_count: Optional[int] = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        print('yamlnav __init__', self.view.file_name(), self.view.id())

    @classmethod
    def is_applicable(cls, settings: Mapping[str, Any]):
        # A scope-selector-based approach would be nicer, but we don't get that here.
        return 'YAML' in settings.get('syntax', '')

    def on_load_async(self) -> None:
        self._update_yaml_symbols()

    def on_activated_async(self) -> None:
        print('yamlnav on_activated')
        if self.view.is_loading():
            return
        if self.yaml_symbols:
            # Update current symbol after view change/quick navigation
            self._update_current_yaml_symbol()
        else:
            # Rebuild list after plugin reload
            self._update_yaml_symbols()

    def on_modified_async(self) -> None:
        self._debounce_update_yaml_symbols()

    def on_selection_modified_async(self) -> None:
        self._update_current_yaml_symbol()

    def on_close(self) -> None:
        print('yamlnav on_close', self.view.file_name(), self.view.id())  # TODO remove after checking

    def __del__(self):
        print('yamlnav __del__', self.view.file_name(), self.view.id())  # TODO remove after checking

    def _debounce_update_yaml_symbols(self) -> None:
        print('yamlnav debounce', self.view.change_count())
        callback = partial(self._update_yaml_symbols, change_count=self.view.change_count())
        sublime.set_timeout_async(callback, UPDATE_SYMBOLS_DEBOUNCE)

    def _update_yaml_symbols(self, change_count: Optional[int] = None) -> None:
        """Generate YAML symbol list and saves it in the view data.
        """
        print('yamlnav _update_yaml_symbols')
        if change_count is not None and change_count != self.view.change_count():
            return

        # Extract symbols
        symbols = yaml_math.get_yaml_symbols(self.view)
        print('yamlnav symbols', symbols)

        # TODO what's this do
        # Remove leading colons when setting trim_leading_colon = true
        # if get_setting("trim_leading_colon"):
        #     for symbol in symbols:
        #         symbol["name"] = REMOVE_COLON_RE.sub("", symbol["name"])

        self.yaml_symbols = symbols

        # Also update current symbol because it may have changed
        self._update_current_yaml_symbol()

    def _update_current_yaml_symbol(self) -> None:
        """Find the currently selected YAML symbol (for display and copying).
        """
        self.current_yaml_symbol = yaml_math.get_selected_yaml_symbol(self.yaml_symbols, self.view)
        if self.current_yaml_symbol:
            set_status(self.view, self.current_yaml_symbol.name)
        else:
            set_status(self.view)

    # TODO write custom context key that checks whether the current file has symbols


class YamlNavGotoCommand(sublime_plugin.TextCommand):
    """Open a quick panel with YAML symbols.
    """
    _listener: Optional[YamlNavListener]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._listener = sublime_plugin.find_view_event_listener(self.view, YamlNavListener)

    def is_enabled(self) -> bool:
        return bool(self._listener)

    def run(self, edit: sublime.Edit) -> None:
        # TODO use a list input handler & live-update viewport
        if not self._listener:
            return
        if not (symbols := self._listener.yaml_symbols):
            self.view.window().status_message("No symbols found")
            return
        self.view.window().show_quick_panel(
            [x.name for x in symbols],
            self._on_symbol_selected,
        )

    def _on_symbol_selected(self, index: int) -> None:
        if index == -1 or not self._listener:
            return
        region = self._listener.yaml_symbols[index].region

        self.view.show_at_center(region)

        # TODO extract to TextCommand because of selection modification
        # Set cursor after YAML key
        self.view.sel().clear()
        self.view.sel().add(sublime.Region(region.end() + 1))


class YamlNavCopyCurrentCommand(sublime_plugin.TextCommand):
    """Copy selected YAML symbol into clipboard.
    """
    _listener: Optional[YamlNavListener]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._listener = sublime_plugin.find_view_event_listener(self.view, YamlNavListener)

    def is_enabled(self) -> bool:
        return bool(self._listener)

    def run(self, edit: sublime.Edit) -> None:
        if self._listener and (current_symbol := self._listener.current_yaml_symbol):
            current_symbol_name = current_symbol.name

            # Automatically detect localization YAML and trim first tag
            # (if enabled in settings)
            if get_setting("trim_language_tag_on_copy_from_locales") and self._is_locale_file():
                current_symbol_name = re.sub(r"^(.+?)\.", "", current_symbol_name)

            sublime.set_clipboard(current_symbol_name)
            set_status(self.view, f"{current_symbol_name} - copied to clipboard!")
        else:
            set_status(self.view, "nothing selected - can't copy!")

    def _is_locale_file(self) -> bool:
        return bool(re.search(
            get_setting("detect_locale_filename_re"),
            self.view.file_name() or "",
            re.I,
        ))

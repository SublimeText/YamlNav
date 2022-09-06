"""Functions for extracting YAML symbols from views.
"""

import sublime

from typing import (
    Iterator,
    List,
    NamedTuple,
    Optional,
)


class Symbol(NamedTuple):
    name: str
    region: sublime.Region


class Level(NamedTuple):
    key: str
    indent: int


def get_yaml_symbols(view: sublime.View) -> List[Symbol]:
    """
    Returns YAML key paths and associated regions for given sublime view.
    Paths calculated by key indentation level -- it's more efficient and secure, but doesn't support inline hashes.
    """

    # Note that this does not work for flow mappings
    # since it looks at the indentation level
    regions = view.find_by_selector(
        "meta.mapping.key.yaml string"
        " - meta.mapping.key meta.mapping"
        " - meta.mapping.key meta.sequence"
    )

    # Read the entire buffer content into the memory: it's much much faster than multiple substr's
    content = view.substr(sublime.Region(0, view.size()))

    symbols = []
    current_path: List[Level] = []

    for region in regions:
        key = content[region.begin():region.end()].strip()

        # Characters count from line beginning to key start position
        indent_level = region.begin() - content.rfind("\n", 0, region.begin()) - 1

        # Pop items from current_path while its indentation level less than current key indentation
        while len(current_path) > 0 and current_path[-1].indent >= indent_level:
            current_path.pop()

        current_path.append(Level(key, indent_level))

        symbol_name = ".".join(item.key for item in current_path)
        symbols.append(Symbol(symbol_name, region))

    return symbols


def get_selected_yaml_symbol(symbols: List[Symbol], view: sublime.View) -> Optional[Symbol]:
    """Determine the currently selected symbol of a view.
    """
    if not symbols:
        return None

    if len(view.sel()) != 1:
        # Ambigous symbol: multiple cursors
        return None

    # Reversing list because we are searching for the deepest key
    yaml_symbols = reversed(symbols)

    for region in iter_regions(view):
        for symbol in yaml_symbols:
            if region.intersects(symbol.region):
                return symbol

    return None


def iter_regions(view) -> Iterator[sublime.Region]:
    """Iterate over regions from the selections, gradually getting less specific.
    """
    for sel in view.sel():
        yield sublime.Region(sel.b, sel.b)
    for sel in view.sel():
        yield sel
    for sel in view.sel():
        yield from view.lines(sel)

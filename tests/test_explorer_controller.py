"""ExplorerController: open stocks, selection rules, refresh and right-click menus, through a fake tree."""
from core.explorer.controller import FOLDER, STRATEGY, SYMBOL, VIEW, ExplorerController, Node
from core.explorer.entries import StrategyEntry
from core.strategies import service as actions


class FakeTree:
    """Behaves like the real tree: selecting reports back to the controller (as Qt's signal does)."""

    def __init__(self):
        self.controller = None
        self.rows, self.entries = {}, {}
        self.selected: list[tuple[str, str | None]] = []
        self.current: tuple[str, str | None] | None = None
        self.silent = []  # calls that must not report a selection change

    def add_symbol(self, symbol, rows, strategies):
        self.rows[symbol], self.entries[symbol] = rows, strategies

    def set_strategies(self, symbol, strategies):
        self.entries[symbol] = strategies
        self.selected = [(s, k) for s, k in self.selected if k in self._keys(symbol) or s != symbol]

    def select_only(self, symbol, keys):
        self.selected = [(symbol, key) for key in keys]
        self.current = (symbol, keys[0])
        self._report()

    def restore_selection(self, symbol, keys, current_key):
        self.silent.append('restore')
        self.selected = [(symbol, key) for key in keys]
        self.current = (symbol, current_key)

    def apply_selection(self, symbol, keep):
        self.silent.append('apply')
        self.selected = [(s, k) for s, k in self.selected if s == symbol and k in keep]

    def read_selection(self):
        return (self._node(self.current) if self.current else None), [self._node(item) for item in self.selected]

    # --- what the user does ---

    def click(self, symbol, key, ctrl=False):
        self.selected = (self.selected if ctrl else []) + [(symbol, key)]
        self.current = (symbol, key)
        self._report()

    def click_symbol(self, symbol):
        self.current = (symbol, None)
        self._report()

    def _report(self):
        self.controller.on_selection_changed(*self.read_selection())

    def _keys(self, symbol):
        return {entry.key for entry in self.entries[symbol]}

    def _node(self, item):
        symbol, key = item
        if key is None:
            return Node(symbol, None, SYMBOL)
        if key in self._keys(symbol):
            library = next(e.is_library for e in self.entries[symbol] if e.key == key)
            return Node(symbol, key, STRATEGY, library)
        return Node(symbol, key, VIEW)


def entry(strategy_id, library=False):
    return StrategyEntry(f'strategy:{strategy_id}', strategy_id, '', library)


def make(strategies=None):
    """A controller over a fake tree. `strategies` is a dict symbol -> entries that the test can change."""
    strategies = {} if strategies is None else strategies
    tree, emitted, actions_run = FakeTree(), [], []
    controller = ExplorerController(tree, on_views_selected=lambda symbol, keys: emitted.append((symbol, keys)),
                                    on_strategy_action=lambda *args: actions_run.append(args),
                                    entries_source=lambda symbol: list(strategies.get(symbol, [])))
    tree.controller = controller
    return controller, tree, emitted, actions_run, strategies


def test_adding_a_symbol_builds_its_rows_and_selects_the_first_view():
    controller, tree, emitted, *_ = make({'IBM': [entry('a')]})
    controller.add_symbol('IBM')
    kinds = [(row.kind, row.key) for row in tree.rows['IBM']]
    assert kinds[0] == (VIEW, 'price') and (FOLDER, None) in kinds
    assert kinds.index((FOLDER, None)) == kinds.index((VIEW, 'history')) - 1  # folder sits just above History
    assert emitted == [('IBM', ['price'])] and controller.symbols == ['IBM']


def test_adding_a_known_symbol_does_not_rebuild_it_but_reselects_its_first_view():
    controller, tree, emitted, *_ = make()
    controller.add_symbol('IBM')
    controller.add_symbol('AAPL')
    tree.rows.clear()
    controller.add_symbol('IBM')
    assert tree.rows == {} and emitted[-1] == ('IBM', ['price']) and controller.symbols == ['IBM', 'AAPL']


def test_clicking_a_symbol_opens_its_first_view():
    controller, tree, emitted, *_ = make()
    controller.add_symbol('IBM')
    tree.click('IBM', 'macd')
    tree.click_symbol('IBM')
    assert emitted[-1] == ('IBM', ['price'])


def test_ctrl_click_stacks_views_in_top_to_bottom_order():
    controller, tree, emitted, *_ = make()
    controller.add_symbol('IBM')
    tree.click('IBM', 'atr', ctrl=True)
    tree.click('IBM', 'macd', ctrl=True)
    assert emitted[-1] == ('IBM', ['price', 'macd', 'atr'])  # the order of the tree, not of the clicks


def test_only_one_strategy_at_a_time_and_the_one_just_clicked_wins():
    controller, tree, emitted, *_ = make({'IBM': [entry('a'), entry('b')]})
    controller.add_symbol('IBM')
    tree.click('IBM', 'strategy:a', ctrl=True)
    assert emitted[-1] == ('IBM', ['price', 'strategy:a'])
    tree.click('IBM', 'strategy:b', ctrl=True)
    assert emitted[-1] == ('IBM', ['price', 'strategy:b'])
    assert ('IBM', 'strategy:a') not in tree.selected  # the tree was told to drop it


def test_selecting_in_another_stock_leaves_the_first_one():
    controller, tree, emitted, *_ = make()
    controller.add_symbol('IBM')
    controller.add_symbol('AAPL')
    tree.click('IBM', 'volume', ctrl=True)
    tree.click('AAPL', 'macd', ctrl=True)
    assert emitted[-1] == ('AAPL', ['macd']) and controller.current_symbol == 'AAPL'
    assert all(symbol == 'AAPL' for symbol, _ in tree.selected)


def test_clicking_away_the_last_view_keeps_the_view_showing():
    controller, tree, emitted, *_ = make()
    controller.add_symbol('IBM')
    count = len(emitted)
    tree.selected, tree.current = [], ('IBM', 'price')  # Ctrl+click deselected the only view
    tree._report()
    assert len(emitted) == count  # nothing emitted: the previous views stay


def test_refresh_keeps_the_selection_and_reports_it_again():
    strategies = {'IBM': [entry('a')]}
    controller, tree, emitted, *_ = make(strategies)
    controller.add_symbol('IBM')
    tree.click('IBM', 'strategy:a', ctrl=True)
    strategies['IBM'] = [entry('a'), entry('new')]  # a strategy was added elsewhere
    count = len(emitted)
    controller.refresh_strategies()
    assert 'restore' in tree.silent and len(emitted) == count + 1
    assert emitted[-1] == ('IBM', ['price', 'strategy:a'])
    assert [e.key for e in tree.entries['IBM']] == ['strategy:a', 'strategy:new']


def test_refresh_after_the_selected_strategy_was_deleted_falls_back_to_the_first_view():
    strategies = {'IBM': [entry('a')]}
    controller, tree, emitted, *_ = make(strategies)
    controller.add_symbol('IBM')
    tree.click('IBM', 'strategy:a')
    strategies['IBM'] = []
    controller.refresh_strategies()
    assert emitted[-1] == ('IBM', ['price'])


def test_refresh_before_anything_is_selected_only_updates_the_lists():
    controller, tree, emitted, *_ = make({})
    controller.refresh_strategies()
    assert emitted == []


def test_select_strategy_adds_the_stock_if_needed_and_ignores_unknown_ids():
    strategies = {'AAPL': [entry('x')]}
    controller, tree, emitted, *_ = make(strategies)
    controller.select_strategy('AAPL', 'x')
    assert controller.symbols == ['AAPL'] and emitted[-1] == ('AAPL', ['strategy:x'])
    count = len(emitted)
    controller.select_strategy('AAPL', 'nope')
    assert len(emitted) == count


def test_right_click_menus_and_actions():
    controller, tree, emitted, actions_run, _ = make()
    own = Node('IBM', 'strategy:a', STRATEGY, is_library=False)
    template = Node('IBM', 'strategy:t', STRATEGY, is_library=True)
    assert [e.action for e in controller.menu_for(Node('IBM', None, SYMBOL))] == [actions.NEW]
    assert actions.DUPLICATE in [e.action for e in controller.menu_for(own) if e]
    assert controller.menu_for(template)[0].action == actions.COPY_HERE

    controller.menu_action(actions.DUPLICATE, own)
    controller.menu_action(actions.NEW, Node('IBM', None, SYMBOL))
    assert actions_run == [(actions.DUPLICATE, 'IBM', 'a'), (actions.NEW, 'IBM', '')]

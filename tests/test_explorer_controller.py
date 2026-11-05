"""ExplorerController: open stocks, selection rules, refresh and right-click menus, through a fake tree."""
from core.dashboard.layout import OVERVIEW
from core.explorer.controller import FOLDER, PORTFOLIO, STRATEGY, SYMBOL, VIEW, ExplorerController, Node, Scope
from core.portfolios import actions as portfolio_actions
from portfolio import Portfolio
from core.explorer.entries import StrategyEntry
from core.strategies import service as actions


class FakeTree:
    """Behaves like the real tree: selecting reports back to the controller (as Qt's signal does)."""

    def __init__(self):
        self.controller = None
        self.rows, self.entries = {}, {}
        self.selected: list[tuple[Scope, str | None]] = []
        self.current: tuple[Scope, str | None] | None = None
        self.silent = []  # calls that must not report a selection change
        self.portfolios, self.added, self.removed, self.renaming = {}, [], [], None
        self.cleared = []

    def add_portfolio(self, portfolio_id, name):
        self.portfolios[portfolio_id] = name

    def rename_portfolio(self, portfolio_id, name):
        self.portfolios[portfolio_id] = name
        self.silent.append('rename')

    def begin_rename(self, portfolio_id):
        self.renaming = portfolio_id

    def remove_portfolio(self, portfolio_id):
        del self.portfolios[portfolio_id]

    def remove_symbol(self, scope):
        self.removed.append(scope)
        self.selected = [(s, k) for s, k in self.selected if s != scope]

    def add_symbol(self, scope, rows, strategies):
        self.rows[scope.symbol], self.entries[scope.symbol] = rows, strategies
        self.added.append(scope)

    def set_strategies(self, symbol, strategies):
        self.entries[symbol] = strategies
        self.selected = [(s, k) for s, k in self.selected if k in self._keys(symbol) or s.symbol != symbol]

    def select_only(self, scope, keys):
        self.selected = [(scope, key) for key in keys]
        self.current = (scope, keys[0])
        self._report()

    def restore_selection(self, scope, keys, current_key):
        self.silent.append('restore')
        self.selected = [(scope, key) for key in keys]
        self.current = (scope, current_key)

    def apply_selection(self, scope, keep):
        self.silent.append('apply')
        self.selected = [(s, k) for s, k in self.selected if s == scope and k in keep]

    def read_selection(self):
        return (self._node(self.current) if self.current else None), [self._node(item) for item in self.selected]

    # --- what the user does ---

    def click(self, symbol, key, ctrl=False, portfolio=None):
        scope = Scope(portfolio, symbol)
        self.selected = (self.selected if ctrl else []) + [(scope, key)]
        self.current = (scope, key)
        self._report()

    def click_symbol(self, symbol, ctrl=False):
        scope = Scope(None, symbol)  # the real tree registers a stock's own row under the OVERVIEW key
        self.selected = (self.selected if ctrl else []) + [(scope, OVERVIEW)]
        self.current = (scope, OVERVIEW)
        self._report()

    def click_portfolio(self, portfolio_id):
        self.controller.on_selection_changed(Node('', None, PORTFOLIO, portfolio=portfolio_id), [])

    def _report(self):
        self.controller.on_selection_changed(*self.read_selection())

    def _keys(self, symbol):
        return {entry.key for entry in self.entries[symbol]}

    def _node(self, item):
        scope, key = item
        symbol = scope.symbol
        if key in (None, OVERVIEW):
            return Node(symbol, key, SYMBOL, portfolio=scope.portfolio)
        if key in self._keys(symbol):
            library = next(e.is_library for e in self.entries[symbol] if e.key == key)
            return Node(symbol, key, STRATEGY, library, scope.portfolio)
        return Node(symbol, key, VIEW, portfolio=scope.portfolio)


def entry(strategy_id, library=False):
    return StrategyEntry(f'strategy:{strategy_id}', strategy_id, '', library)


def make(strategies=None):
    """A controller over a fake tree. `strategies` is a dict symbol -> entries that the test can change."""
    strategies = {} if strategies is None else strategies
    tree, emitted, actions_run = FakeTree(), [], []
    controller = ExplorerController(tree, on_views_selected=lambda symbol, keys: emitted.append((symbol, keys)),
                                    on_strategy_action=lambda *args: actions_run.append(args),
                                    on_selection_cleared=lambda: tree.cleared.append(True),
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


def test_clicking_a_symbol_opens_its_company_overview_on_its_own():
    controller, tree, emitted, *_ = make()
    controller.add_symbol('IBM')
    tree.click('IBM', 'macd')
    tree.click('IBM', 'atr', ctrl=True)
    tree.click_symbol('IBM', ctrl=True)  # even with Ctrl held, the overview is shown alone
    assert emitted[-1] == ('IBM', ['overview'])
    assert tree.selected == [(Scope(None, 'IBM'), 'overview')]


def test_ctrl_clicking_a_view_from_the_overview_replaces_it():
    controller, tree, emitted, *_ = make()
    controller.add_symbol('IBM')
    tree.click_symbol('IBM')
    tree.click('IBM', 'macd', ctrl=True)
    assert emitted[-1] == ('IBM', ['macd']) and tree.selected == [(Scope(None, 'IBM'), 'macd')]


def test_refreshing_strategies_keeps_the_overview_selected():
    strategies = {'IBM': [entry('a')]}
    controller, tree, emitted, *_ = make(strategies)
    controller.add_symbol('IBM')
    tree.click_symbol('IBM')
    strategies['IBM'] = [entry('a'), entry('b')]
    controller.refresh_strategies()
    assert emitted[-1] == ('IBM', ['overview']) and controller.selected == ['overview']


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
    assert (Scope(None, 'IBM'), 'strategy:a') not in tree.selected  # the tree was told to drop it


def test_selecting_in_another_stock_leaves_the_first_one():
    controller, tree, emitted, *_ = make()
    controller.add_symbol('IBM')
    controller.add_symbol('AAPL')
    tree.click('IBM', 'volume', ctrl=True)
    tree.click('AAPL', 'macd', ctrl=True)
    assert emitted[-1] == ('AAPL', ['macd']) and controller.current_symbol == 'AAPL'
    assert all(scope.symbol == 'AAPL' for scope, _ in tree.selected)


def test_clicking_away_the_last_view_keeps_the_view_showing():
    controller, tree, emitted, *_ = make()
    controller.add_symbol('IBM')
    count = len(emitted)
    tree.selected, tree.current = [], (Scope(None, 'IBM'), 'price')  # Ctrl+click deselected the only view
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
    stock_menu = controller.menu_for(Node('IBM', None, SYMBOL))
    assert stock_menu[0].action == actions.NEW and stock_menu[-1].text == 'Add to portfolio'
    assert actions.DUPLICATE in [e.action for e in controller.menu_for(own) if e]
    assert controller.menu_for(template)[0].action == actions.COPY_HERE

    controller.menu_action(actions.DUPLICATE, own)
    controller.menu_action(actions.NEW, Node('IBM', None, SYMBOL))
    assert actions_run == [(actions.DUPLICATE, 'IBM', 'a'), (actions.NEW, 'IBM', '')]


# --- portfolios ------------------------------------------------------------------------------------------------

def portfolio(name='Tech', symbols=('AAPL', 'MSFT')):
    return Portfolio(name, list(symbols))


def test_opening_a_portfolio_adds_its_row_and_its_stocks_in_order():
    controller, tree, emitted, *_ = make()
    tech = portfolio()
    controller.open_portfolio(tech)
    assert tree.portfolios == {tech.id: 'Tech'}
    assert tree.added == [Scope(tech.id, 'AAPL'), Scope(tech.id, 'MSFT')]
    assert controller.symbols == []  # nothing standalone
    assert emitted == []  # opening a portfolio does not change what is shown
    controller.open_portfolio(tech)  # again: nothing is added twice
    assert len(tree.added) == 2


def test_the_same_ticker_standalone_and_in_a_portfolio_selects_independently():
    controller, tree, emitted, *_ = make()
    tech = portfolio()
    controller.add_symbol('AAPL')
    controller.open_portfolio(tech)
    assert len(tree.added) == 3  # standalone AAPL, and AAPL + MSFT inside the portfolio
    tree.click('AAPL', 'macd', portfolio=tech.id)
    assert emitted[-1] == ('AAPL', ['macd']) and controller.current_scope == Scope(tech.id, 'AAPL')
    assert all(scope == Scope(tech.id, 'AAPL') for scope, _ in tree.selected)  # the standalone one was dropped
    tree.click('AAPL', 'atr')  # back to the standalone copy
    assert controller.current_scope == Scope(None, 'AAPL') and emitted[-1] == ('AAPL', ['atr'])


def test_a_portfolio_row_is_not_a_view_and_changes_nothing():
    controller, tree, emitted, *_ = make()
    tech = portfolio()
    controller.add_symbol('IBM')
    controller.open_portfolio(tech)
    count = len(emitted)
    tree.click_portfolio(tech.id)
    assert len(emitted) == count and controller.current_symbol == 'IBM'


def test_refresh_portfolio_adds_new_stocks_drops_removed_ones_and_renames():
    controller, tree, emitted, *_ = make()
    tech = portfolio()
    controller.open_portfolio(tech)
    tech.symbols, tech.name = ['MSFT', 'IBM'], 'Big Tech'
    controller.refresh_portfolio(tech)
    assert tree.portfolios[tech.id] == 'Big Tech'
    assert tree.removed == [Scope(tech.id, 'AAPL')] and Scope(tech.id, 'IBM') in tree.added
    assert [s for s in controller.scopes if s.portfolio == tech.id] == [Scope(tech.id, 'MSFT'), Scope(tech.id, 'IBM')]
    controller.refresh_portfolio(portfolio('Never opened'))  # not open: ignored
    assert len(tree.portfolios) == 1


def test_closing_a_portfolio_removes_it_and_forgets_a_selection_inside_it():
    controller, tree, emitted, *_ = make()
    tech, other = portfolio(), portfolio('Other', ('IBM',))
    controller.open_portfolio(tech)
    controller.open_portfolio(other)
    tree.click('AAPL', 'macd', portfolio=tech.id)
    controller.close_portfolio(tech.id)
    assert tree.portfolios == {other.id: 'Other'} and controller.current_scope is None and controller.selected == []
    assert [s for s in controller.scopes if s.portfolio == tech.id] == []
    controller.close_portfolio('unknown')  # harmless


def test_strategy_selection_prefers_the_stock_being_viewed():
    strategies = {'AAPL': [entry('a')]}
    controller, tree, emitted, *_ = make(strategies)
    tech = portfolio()
    controller.open_portfolio(tech)
    tree.click('AAPL', 'price', portfolio=tech.id)
    controller.select_strategy('AAPL', 'a')
    assert controller.current_scope == Scope(tech.id, 'AAPL') and emitted[-1] == ('AAPL', ['strategy:a'])
    controller.select_strategy('IBM', 'x')  # a different stock: opens it on its own
    assert Scope(None, 'IBM') in controller.scopes


def test_strategy_changes_reach_every_copy_of_the_ticker():
    strategies = {'AAPL': [entry('a')]}
    controller, tree, *_ = make(strategies)
    controller.add_symbol('AAPL')
    controller.open_portfolio(portfolio())
    strategies['AAPL'] = [entry('a'), entry('b')]
    controller.refresh_strategies()
    assert [e.key for e in tree.entries['AAPL']] == ['strategy:a', 'strategy:b']


def test_portfolio_menu():
    controller, *_ = make()
    node = Node('', None, PORTFOLIO, portfolio='p1')
    menu = controller.menu_for(node)
    assert [e.action for e in menu if e] == [portfolio_actions.ADD_STOCK, portfolio_actions.RENAME,
                                              portfolio_actions.CLOSE, portfolio_actions.DELETE]
    assert menu[2] is None  # a separator before the destructive entries


def test_stock_menu_offers_every_other_open_portfolio_and_remove_only_inside_one():
    controller, *_ = make()
    tech, other = portfolio(), portfolio('Other', ('IBM',))
    controller.open_portfolio(tech)
    controller.open_portfolio(other)

    standalone = controller.menu_for(Node('AAPL', None, SYMBOL))
    add_to = standalone[-1]
    assert add_to.text == 'Add to portfolio' and not add_to.action
    assert [(c.text, c.argument) for c in add_to.children if c and c.argument] == [('Tech', tech.id),
                                                                                    ('Other', other.id)]
    assert add_to.children[-1].action == portfolio_actions.ADD_TO_NEW and add_to.children[-2] is None
    assert all(not e or e.action != portfolio_actions.REMOVE_FROM for e in standalone)

    inside = controller.menu_for(Node('AAPL', None, SYMBOL, portfolio=tech.id))
    targets = [c.argument for c in inside[-2].children if c and c.argument]
    assert targets == [other.id]  # not the portfolio it is already in
    assert inside[-1].action == portfolio_actions.REMOVE_FROM


def test_with_no_other_portfolio_the_submenu_only_offers_a_new_one():
    controller, *_ = make()
    children = controller.menu_for(Node('AAPL', None, SYMBOL))[-1].children
    assert [c.action for c in children] == [portfolio_actions.ADD_TO_NEW]


def test_portfolio_actions_are_routed_with_their_argument_and_rename_carries_the_typed_name():
    controller, tree, emitted, actions_run, _ = make()
    routed = []
    controller.on_portfolio_action = lambda action, node, argument: routed.append((action, node, argument))
    stock = Node('AAPL', None, SYMBOL)
    controller.menu_action(portfolio_actions.ADD_TO, stock, 'p2')
    controller.rename_requested('p1', 'Retirement')
    assert routed[0] == (portfolio_actions.ADD_TO, stock, 'p2')
    assert routed[1][0] == portfolio_actions.RENAME and routed[1][1].portfolio == 'p1' and routed[1][2] == 'Retirement'
    assert actions_run == []  # not treated as strategy actions


def test_begin_rename_and_open_ids():
    controller, tree, *_ = make()
    tech = portfolio()
    controller.open_portfolio(tech)
    controller.begin_rename(tech.id)
    assert tree.renaming == tech.id and controller.open_portfolio_ids() == {tech.id}


def test_removing_the_stock_being_shown_clears_the_selection_and_the_app_is_told():
    controller, tree, emitted, *_ = make()
    tech = portfolio()
    controller.open_portfolio(tech)
    tree.click('AAPL', 'macd', portfolio=tech.id)
    tech.symbols = ['MSFT']
    controller.refresh_portfolio(tech)  # AAPL was removed from the portfolio
    assert tree.cleared == [True] and controller.current_scope is None and controller.selected == []


def test_removing_a_stock_that_is_not_being_shown_leaves_the_chart_alone():
    controller, tree, emitted, *_ = make()
    tech = portfolio()
    controller.open_portfolio(tech)
    tree.click('MSFT', 'macd', portfolio=tech.id)
    tech.symbols = ['MSFT']
    controller.refresh_portfolio(tech)
    assert tree.cleared == [] and controller.current_scope == Scope(tech.id, 'MSFT')


def test_closing_the_portfolio_that_holds_the_shown_stock_clears_once():
    controller, tree, *_ = make()
    tech = portfolio()
    controller.open_portfolio(tech)
    tree.click('AAPL', 'price', portfolio=tech.id)
    controller.close_portfolio(tech.id)
    assert tree.cleared == [True]


def test_the_same_ticker_shown_elsewhere_is_not_affected_when_another_copy_is_removed():
    controller, tree, *_ = make()
    tech = portfolio()
    controller.add_symbol('AAPL')  # standalone copy is the one being shown
    controller.open_portfolio(tech)
    tech.symbols = ['MSFT']
    controller.refresh_portfolio(tech)  # the portfolio's AAPL goes away
    assert tree.cleared == [] and controller.current_scope == Scope(None, 'AAPL')

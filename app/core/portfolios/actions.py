"""Names of the portfolio actions on the Explorer's right-click menu. (No imports: shared by two features.)"""

ADD_STOCK = 'add_stock'  # open the Add Stock wizard for a portfolio
RENAME = 'rename_portfolio'
CLOSE = 'close_portfolio'  # take it out of the Explorer (the file stays)
DELETE = 'delete_portfolio'  # remove it and its file
ADD_TO = 'add_to_portfolio'  # argument: the portfolio's id
ADD_TO_NEW = 'add_to_new_portfolio'
REMOVE_FROM = 'remove_from_portfolio'

ALL = (ADD_STOCK, RENAME, CLOSE, DELETE, ADD_TO, ADD_TO_NEW, REMOVE_FROM)

"""Symbol search: data sources, the catalogue, and matching. (The search bar widget is in qtrender/.)"""
from .catalog import Catalog, Group, Security, load_catalog
from .matcher import MAX_RESULTS, match_groups, match_securities

__all__ = ['Catalog', 'Group', 'MAX_RESULTS', 'Security', 'load_catalog', 'match_groups', 'match_securities']

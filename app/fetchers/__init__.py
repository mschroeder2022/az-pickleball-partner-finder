"""Import all fetcher modules so they self-register on the registry."""
from . import (  # noqa: F401
    app_tour,
    az_cash,
    dupr,
    matchpoint,
    pickleballden,
    picklemoneyball,
    ppa_challenger,
    second_serve,
)
from .base import all_fetchers, get_fetcher  # noqa: F401

"""
Test if a given list of values is IID (independent and identically distributed).
"""
import logging
import statsmodels
from statsmodels.stats.diagnostic import acorr_ljungbox


def is_iid(vals):
    """
    Use Ljung Box test to check if given |vals| are IID.

    Returns:
    True -- vals are IID
    False -- Otherwise
    """
    significance_level = 0.05
    _major, minor, _patch = statsmodels.__version__.split(".")
    if minor == "12":
        _test_statistic, p_values = acorr_ljungbox(vals)
        return all(p > significance_level for p in p_values)

    # |vals| < 5 triggers
    # ValueError: zero-size array to reduction operation maximum which has no identity
    if len(vals) < 5:
        logging.debug("Calling is_iid with fewer 5 values always returns False: %d", len(vals))
        return False
    res = acorr_ljungbox(vals)
    return bool((res["lb_pvalue"] > significance_level).all())

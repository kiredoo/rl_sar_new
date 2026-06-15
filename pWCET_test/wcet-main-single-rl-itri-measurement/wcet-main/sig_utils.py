"""
Utility functions for handling signals
"""
_GOT_SIGINT = False

def sigint_handler(_sig, _frame):
    global _GOT_SIGINT
    _GOT_SIGINT = True


def got_sigint():
    return _GOT_SIGINT

"""
Utility functions of working with OS
"""

def sanitize_filename(s):
    """
    Return a filename not containing s
    """
    return s.replace(":", "__COLON__")

def desanitize_filename(s):
    return s.replace("__COLON__", ":")

"""Bundled benchmark runners.

Each module in this package imports :mod:`chuzom.benchmark` and calls
``register_runner(...)`` at import time. The parent package imports them
all so that ``from chuzom.benchmark import get_runner`` finds them
without callers having to know module paths.
"""

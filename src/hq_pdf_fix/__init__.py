"""Rewrite legacy GBK-passthrough Chinese PDFs into self-contained Identity-H files.

The public surface is the ``hq_pdf_fix`` console command (see :mod:`hq_pdf_fix.cli`);
:func:`convert` is the same conversion exposed as a function.
"""

__version__ = "0.1.0"

__all__ = ["__version__", "convert"]


def convert(*args, **kwargs):
    """Convert one PDF; imported lazily so ``--version`` stays dependency-free."""
    from .converter import convert as _convert

    return _convert(*args, **kwargs)

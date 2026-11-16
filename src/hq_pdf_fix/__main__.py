"""Allow ``python -m hq_pdf_fix``."""
import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())

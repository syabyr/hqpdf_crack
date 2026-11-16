"""Console entry point: ``hq_pdf_fix``."""
from .converter import main as _main


def main(argv=None):
    """Run the converter and return a process exit status.

    ``argv`` defaults to sys.argv[1:].  The written path is not returned here:
    anything other than 0 or None passed to sys.exit() is printed and turned into
    a failure status, and this function backs a console script.
    """
    _main(argv)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

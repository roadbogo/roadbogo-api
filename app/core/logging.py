import logging
import sys
import time


def configure_logging(log_level: str) -> None:
    logging.basicConfig(
        level=log_level.upper(),
        format="%(asctime)sZ %(levelname)s %(name)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
        handlers=[logging.StreamHandler(sys.stdout)],
        force=True,
    )
    logging.Formatter.converter = time.gmtime

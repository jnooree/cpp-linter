import logging
from tempfile import NamedTemporaryFile

from requests import Response

FOUND_RICH_LIB = False
try:  # pragma: no cover
    from rich.logging import RichHandler, get_console  # type: ignore

    FOUND_RICH_LIB = True

    logging.basicConfig(
        format="%(name)s: %(message)s",
        handlers=[RichHandler(show_time=False)],
    )

except ImportError:  # pragma: no cover
    logging.basicConfig()

#: The :py:class:`logging.Logger` object used for outputting data.
logger = logging.getLogger("CPP Linter")
if not FOUND_RICH_LIB:
    logger.debug("rich module not found")

# setup a separate logger for using github log commands
log_commander = logging.getLogger("LOG COMMANDER")  # create a child of our logger obj
log_commander.setLevel(logging.DEBUG)  # be sure that log commands are output
console_handler = logging.StreamHandler()  # Create special stdout stream handler
console_handler.setFormatter(logging.Formatter("%(message)s"))  # no formatted log cmds
log_commander.addHandler(console_handler)  # Use special handler for log_commander
log_commander.propagate = False


def start_log_group(name: str) -> None:
    """Begin a collapsable group of log statements.

    :param name: The name of the collapsable group
    """
    log_commander.fatal("::group::%s", name)


def end_log_group() -> None:
    """End a collapsable group of log statements."""
    log_commander.fatal("::endgroup::")


def log_response_msg(response: Response):
    """Output the response buffer's message on a failed request."""
    if response.status_code >= 400:
        logger.error(
            "response returned %d from %s %s with message: %s",
            response.status_code,
            response.request.method,
            response.request.url,
            response.text,
        )


def worker_logfile_init(tempdir: str, loglvl: int):
    logfile = NamedTemporaryFile("w", dir=tempdir, delete=False)

    logger.handlers.clear()
    logger.propagate = False

    handler: logging.Handler
    if FOUND_RICH_LIB:
        console = get_console()
        console.file = logfile
        handler = RichHandler(show_time=False, console=console)
        handler.setFormatter(logging.Formatter("%(name)s: %(message)s"))
    else:
        handler = logging.StreamHandler(logfile)
        handler.setFormatter(logging.Formatter(logging.BASIC_FORMAT))
    logger.addHandler(handler)
    # Windows does not copy log level to subprocess.
    # https://github.com/cpp-linter/cpp-linter/actions/runs/8355193931
    logger.setLevel(loglvl)

    log_commander.handlers.clear()
    log_commander.propagate = False
    console_handler = logging.StreamHandler(logfile)
    console_handler.setFormatter(logging.Formatter("%(message)s"))
    log_commander.addHandler(console_handler)

    return logfile.name

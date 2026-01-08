import logging
import sys
from logging.handlers import RotatingFileHandler

LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
DATE_FORMAT = '%Y-%m-%d %H:%M:%S'


def setup_logger(name: str,
                 log_file: str = None,
                 level: int = logging.INFO,
                 rotate: bool = False,
                 max_bytes: int = 10*1024*1024,
                 backup_count: int = 5) -> logging.Logger:
    """
    Create and return a logger with specified name.

    Args:
        name: Logger name (usually __name__).
        log_file: Optional file path to log to. If None, file logging is disabled.
        level: Logging level.
        rotate: If True, uses rotating file handler.
        max_bytes: Max size per log file before rotation.
        backup_count: Number of rotated files to keep.
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)

    # Prevent duplicate handlers if setup repeated
    if not logger.handlers:
        # Console handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(level)
        console_formatter = logging.Formatter(LOG_FORMAT, DATE_FORMAT)
        console_handler.setFormatter(console_formatter)
        logger.addHandler(console_handler)

        # File handler (optional)
        if log_file:
            if rotate:
                file_handler = RotatingFileHandler(log_file, maxBytes=max_bytes, backupCount=backup_count)
            else:
                file_handler = logging.FileHandler(log_file)
            file_handler.setLevel(level)
            file_formatter = logging.Formatter(LOG_FORMAT, DATE_FORMAT)
            file_handler.setFormatter(file_formatter)
            logger.addHandler(file_handler)

    return logger


def get_logger(name: str = __name__, **kwargs) -> logging.Logger:
    """
    Convenience function to get a module-level logger.

    Usage:
        logger = get_logger(__name__, log_file='app.log', rotate=True)
    """
    return setup_logger(name, **kwargs)

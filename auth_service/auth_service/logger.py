import os
import logging
import logging.config
from logging.handlers import TimedRotatingFileHandler
from datetime import date
from django.conf import settings

def logger_object(api_module: str) -> logging.Logger:
    '''
    Returns a logger for the given module.
    - Logs to console and file.
    - Rotates daily.
    - Keeps last 5 logs.
    '''
    # Directory setup
    dynamic_log_path = getattr(settings, "DYNAMIC_LOG_PATH", os.path.join(settings.BASE_DIR, "Logs"))
    log_directory = os.path.join(dynamic_log_path, "server_logs")
    os.makedirs(log_directory, exist_ok=True)

    # File name: 2025-10-10.log
    logger_file_name = os.path.join(log_directory, f"{date.today()}.log")

    logging_schema = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "standard": {
                "format": "%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
                "datefmt": "%Y-%m-%d %H:%M:%S",
            },
            "json": {
                "format": '{"timestamp": "%(asctime)s", "level": "%(levelname)s", "module": "%(name)s", "message": "%(message)s"}',
                "datefmt": "%Y-%m-%d %H:%M:%S",
            },
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "formatter": "standard",
                "level": "DEBUG",
            },
            "file": {
                "class": "logging.handlers.TimedRotatingFileHandler",
                "formatter": "standard",
                "level": "DEBUG",
                "filename": logger_file_name,
                "encoding": "utf-8",
                "when": "midnight",  # rotate daily
                "backupCount": 5,    # keep last 5 logs
            },
        },
        "loggers": {
            api_module: {
                "handlers": ["console", "file"],
                "level": "DEBUG",
                "propagate": False,
            },
        },
    }

    logging.config.dictConfig(logging_schema)
    return logging.getLogger(api_module)

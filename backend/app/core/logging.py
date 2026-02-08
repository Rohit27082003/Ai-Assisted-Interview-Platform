"""Structured logging configuration."""

import logging
import sys
from datetime import datetime, timezone


class StructuredFormatter(logging.Formatter):
    def format(self, record):
        log_data = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "module": record.module,
            "function": record.funcName,
            "message": record.getMessage(),
        }
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)
        if hasattr(record, "candidate_id"):
            log_data["candidate_id"] = record.candidate_id
        if hasattr(record, "interview_id"):
            log_data["interview_id"] = record.interview_id
        if hasattr(record, "graph_name"):
            log_data["graph_name"] = record.graph_name
        return str(log_data)


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        # Console Handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(StructuredFormatter())
        logger.addHandler(console_handler)
        
        # File Handler
        file_handler = logging.FileHandler("backend.log")
        file_handler.setFormatter(StructuredFormatter())
        logger.addHandler(file_handler)
        
        logger.setLevel(logging.DEBUG)
    return logger

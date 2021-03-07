import logging
import os

if os.getenv("DEBUG"):
    loglevel = logging.DEBUG
else:
    loglevel = logging.INFO

logging.basicConfig(format="%(asctime)s %(levelname)s: %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
logger = logging.getLogger(__name__)
logger.setLevel(loglevel)
logger.debug("Logger initialized.")

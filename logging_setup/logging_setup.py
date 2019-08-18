import logging


def get_logger(name):
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(threadName)s] [%(levelname)s]: %(message)s",
        handlers=[logging.FileHandler("loopifi.log"), logging.StreamHandler()],
        datefmt='%B %d %Y, %H:%M:%S %p'
    )

    return logging.getLogger(name)
import logging


def setup_logging(level: int = logging.INFO) -> None:
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )
    # httpx логує кожен запит до LLM — занадто шумно
    logging.getLogger("httpx").setLevel(logging.WARNING)

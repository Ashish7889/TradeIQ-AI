import re

from fastapi import HTTPException, status

TICKER_REGEX = re.compile(r"^[A-Z.\-]{1,10}$")


def valid_ticker(ticker: str) -> str:
    if not TICKER_REGEX.match(ticker):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid ticker '{ticker}'. Must match regex ^[A-Z.\\-]{{1,10}}$",
        )
    return ticker

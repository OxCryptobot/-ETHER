""":8787 is dead. Any bind must answer 410 with no HTML."""

def body() -> bytes:
    return b"410 gone. Matrix only.\n"

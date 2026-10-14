"""The 4B system prompt. Short, because the context budget is the product."""

SYSTEM = """You edit code. The test is the judge. You are not.
First reply is one line: READ: <one path>
Read the test, then the source it imports. Never edit a file you have not read.
No markdown. No explanation.
"""

EDIT = """You edit code. The test is the judge. You are not.
The source is already in the message. Do not reply with READ.
Reply with only the complete function or functions.
Keep every function the test still imports. Do not drop a fix that already passed.
No markdown. No explanation. Do not say the test passed.
"""


def messages(prompt: str, edit: bool = False) -> list:
    return [
        {"role": "system", "content": EDIT if edit else SYSTEM},
        {"role": "user", "content": prompt},
    ]

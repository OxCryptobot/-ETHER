"""Generate vs repair prompts. Strangler slice off Pipeline.run."""
from __future__ import annotations

from typing import Optional

from core.repair import repair_prompt


def first_prompt(
    objective: str,
    strategy_hint: str,
    plan_json: str,
    *,
    tool_block: str = "",
    exp_txt: str = "",
    few_shot_txt: str = "",
    repo_map_txt: str = "",
    context_block: str = "",
    multifile: bool = False,
) -> str:
    prompt = (
        f"Write Python code for:\n{objective}\n\n"
        f"Strategy: {strategy_hint}\n\n"
        f"Plan:\n{plan_json}\n\n"
    )
    if tool_block:
        prompt += f"Tool output:\n{tool_block}\n\n"
    if exp_txt:
        prompt += f"Experience from prior runs:\n{exp_txt}\n\n"
    if few_shot_txt:
        prompt += f"Few-shot success patterns:\n{few_shot_txt}\n\n"
    if repo_map_txt:
        prompt += f"Repo map (symbols):\n{repo_map_txt}\n\n"
    if context_block:
        prompt += f"Relevant workspace context:\n{context_block}\n\n"
    if multifile:
        prompt += (
            "If multiple logical units are needed, keep them in one runnable "
            "module for sandbox, with asserts. Prefer pure functions.\n\n"
        )
    prompt += "Return only executable Python code, no markdown fences."
    return prompt


def retry_prompt(
    objective: str,
    generated: str,
    last_err: str,
    strategy_hint: str,
    *,
    repo_map_txt: str = "",
    context_block: str = "",
    burst: bool = False,
) -> str:
    prompt = repair_prompt(objective, generated, last_err, strategy_hint)
    preamble = ""
    if repo_map_txt:
        preamble += f"Repo map (symbols):\n{repo_map_txt}\n\n"
    if context_block:
        preamble += f"Relevant workspace context:\n{context_block}\n\n"
    prompt = preamble + prompt
    if burst:
        prompt = (
            "[Elevated model / burst retry]\n"
            + prompt
            + "\nInclude asserts that prove correctness.\n"
        )
    return prompt

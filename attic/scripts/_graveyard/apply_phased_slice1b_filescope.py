"""Phase D: tool_files local (not pydantic), fixture resolve, CQ fail tail."""
from __future__ import annotations
import ast
from pathlib import Path

p = Path("core/pipeline.py")
t = p.read_text(encoding="utf-8")

if "tool_files = {}" not in t:
    t = t.replace(
        "            tool_runtime_done = False\n",
        "            tool_runtime_done = False\n            tool_files = {}\n",
        1,
    )
    print("init tool_files")
else:
    print("init: already")

replaced = False
old = '''                        try:
                            setattr(result, "_tool_files", dict(tr.final_code or {}))
                        except Exception:
                            pass'''
if old in t:
    t = t.replace(
        old,
        '''                        tool_files = dict(tr.final_code or {})
                        try:
                            object.__setattr__(result, "_tool_files", tool_files)
                        except Exception:
                            try:
                                result.__dict__["_tool_files"] = tool_files
                            except Exception:
                                pass''',
        1,
    )
    print("tool_files local fill")
    replaced = True
if not replaced and 'result.strategy = "tool_runtime"' in t and "tool_files = dict(tr.final_code" not in t:
    t = t.replace(
        '                        result.strategy = "tool_runtime"\n',
        '                        result.strategy = "tool_runtime"\n'
        "                        tool_files = dict(tr.final_code or {})\n",
        1,
    )
    print("tool_files after strategy")

if 'files = dict(getattr(result, "_tool_files", None) or {})' in t:
    t = t.replace(
        'files = dict(getattr(result, "_tool_files", None) or {})',
        'files = dict(tool_files or getattr(result, "_tool_files", None) or {})',
        1,
    )
    print("cq uses local tool_files")
elif "files = dict(tool_files or" in t:
    print("cq local: already")

needle = 'fixture_env = (os.getenv("ETHER_TOOL_RUNTIME_FIXTURE") or "").strip()\n                sand_req = Envelope('
if needle in t:
    t = t.replace(
        needle,
        'fixture_env = (os.getenv("ETHER_TOOL_RUNTIME_FIXTURE") or "").strip()\n'
        "                if fixture_env:\n"
        "                    try:\n"
        "                        from pathlib import Path as _P\n"
        "                        fixture_env = str(_P(fixture_env).resolve())\n"
        "                    except Exception:\n"
        "                        pass\n"
        '                if not files and generated and "# file:" in generated:\n'
        "                    try:\n"
        "                        from core.multifile import extract_file_blocks\n"
        "                        files = extract_file_blocks(generated)\n"
        "                    except Exception:\n"
        "                        pass\n"
        "                sand_req = Envelope(",
        1,
    )
    print("fixture resolve")
elif "fixture_env = str(_P(fixture_env).resolve())" in t:
    print("fixture resolve: already")

if "files={len(files)}" not in t and "multifile_verify exit=" in t:
    t = t.replace(
        '''                    result.stages.append(
                        StageResult(
                            stage="sandbox",
                            success=cq_ok,
                            detail=(
                                f"multifile_verify exit={sand_payload.exit_code} "
                                f"tests={sand_payload.tests_passed}/{sand_payload.total_tests} "
                                f"flags={sand_payload.security_flags[:3]}"
                            )[:300],
                            duration_ms=(time.perf_counter() - t3) * 1000,
                        )
                    )''',
        '''                    _tail = ((sand_payload.stdout or "") + "\\n" + (sand_payload.stderr or ""))[-400:]
                    result.stages.append(
                        StageResult(
                            stage="sandbox",
                            success=cq_ok,
                            detail=(
                                f"multifile_verify exit={sand_payload.exit_code} "
                                f"tests={sand_payload.tests_passed}/{sand_payload.total_tests} "
                                f"files={len(files)} "
                                f"flags={sand_payload.security_flags[:3]} "
                                f"tail={_tail!r}"
                            )[:500],
                            duration_ms=(time.perf_counter() - t3) * 1000,
                        )
                    )''',
        1,
    )
    print("richer detail")
elif "files={len(files)}" in t:
    print("detail: already")

ast.parse(t)
p.write_text(t, encoding="utf-8")
print("done", len(t))

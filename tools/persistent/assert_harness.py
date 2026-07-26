from tools._lib import emit, parse_payload
from core.assert_harness import ensure_harness, has_self_check


def main(payload):
    code = str(payload.get("code") or "")
    new_code, modified = ensure_harness(code)
    return {
        "ok": True,
        "modified": modified,
        "had_self_check": has_self_check(code),
        "code": new_code,
    }


if __name__ == "__main__":
    emit(main(parse_payload()))

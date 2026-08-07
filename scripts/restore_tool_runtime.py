"""Restore core/tool_runtime.py from last known-good commit (65666a5)."""
from pathlib import Path
import urllib.request

URL = (
    "https://raw.githubusercontent.com/OxCryptobot/-ETHER/"
    "65666a5267a61ae2a7b292658f5437c973b1af4a/core/tool_runtime.py"
)

def main() -> None:
    data = urllib.request.urlopen(URL, timeout=60).read()
    if len(data) < 1000 or b"placeholder" in data[:50]:
        raise SystemExit("download failed or still placeholder")
    Path("core/tool_runtime.py").write_bytes(data)
    print("restored tool_runtime.py", len(data), "bytes")

if __name__ == "__main__":
    main()

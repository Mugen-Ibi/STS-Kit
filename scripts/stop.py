"""Stop only processes whose executable and creation time match our launch record."""
import json
from pathlib import Path
import psutil

state_file = Path(__file__).resolve().parents[1] / "run/processes.json"
if not state_file.exists():
    print("No managed STS processes.")
    raise SystemExit(0)
state = json.loads(state_file.read_text(encoding="utf-8"))
for entry in state.get("processes", []):
    try:
        process = psutil.Process(entry["pid"])
        if (Path(process.exe()).resolve() != Path(entry["executable"]).resolve()
                or abs(process.create_time() - entry["created"]) > 0.01):
            print(f"PID {entry['pid']} no longer matches; left running.")
            continue
        # Children are owned by the verified app (including persistent TTS workers).
        children = process.children(recursive=True)
        for child in reversed(children):
            try:
                child.terminate()
            except psutil.NoSuchProcess:
                pass
        process.terminate()
        try:
            process.wait(timeout=10)
        except psutil.TimeoutExpired:
            print(f"PID {entry['pid']} is still shutting down.")
    except psutil.NoSuchProcess:
        pass
print("STS Kit stopped.")

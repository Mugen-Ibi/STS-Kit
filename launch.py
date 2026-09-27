import atexit
import json
import os
import socket
import secrets
import subprocess
import time
import webbrowser
from pathlib import Path

from sts.settings import GEMMA, PROJECTOR, ROOT, settings, resolve_llama_server


def main():
    os.chdir(ROOT)
    config = settings()
    config['llama_server'] = str(resolve_llama_server(config['llama_server']))
    slots = int(config.get('llama_slots', 2))
    if slots not in (1, 2):
        raise SystemExit('llama_slots must be 1 or 2.')
    for path in [Path(config["llama_server"]), GEMMA, PROJECTOR]:
        if not path.is_file():
            raise SystemExit(f"Missing: {path}. Run setup.ps1 first.")
    for port in [config["llama_port"], config["web_port"]]:
        with socket.socket() as sock:
            if sock.connect_ex(("127.0.0.1", port)) == 0:
                raise SystemExit(f"Port {port} is already in use. Stop the previous STS Kit instance.")
    (ROOT / "logs").mkdir(exist_ok=True)
    (ROOT / "run").mkdir(exist_ok=True)
    log = open(ROOT / "logs/llama.log", "w", encoding="utf-8")
    os.environ["STS_LLAMA_API_KEY"] = secrets.token_urlsafe(32)
    command = [config["llama_server"], "-m", str(GEMMA), "--mmproj", str(PROJECTOR),
               "--host", "127.0.0.1", "--port", str(config["llama_port"]),
               "--alias", "gemma-4-e2b", "-c", str(config["context_size"] * slots),
               "-ngl", str(config["gpu_layers"]), "-np", str(slots), "-fa", "on",
               "-b", "512", "-ub", "256", "-t", "6", "--jinja", "--reasoning", "off",
               "--cache-ram", str(config.get('llama_cache_ram_mb', 0)),
               "--api-key", os.environ["STS_LLAMA_API_KEY"]]
    process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT,
                               creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)

    def cleanup():
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
        log.close()

    atexit.register(cleanup)
    try:
        import httpx
        import uvicorn
        import psutil
        with httpx.Client(trust_env=False, timeout=2) as client:
            for _ in range(180):
                if process.poll() is not None:
                    raise RuntimeError("Gemma failed to start. See logs/llama.log")
                try:
                    if client.get(f"http://127.0.0.1:{config['llama_port']}/health").status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                time.sleep(1)
            else:
                raise RuntimeError("Gemma startup timed out. See logs/llama.log")
        (ROOT / "run/processes.json").write_text(json.dumps({
            "app_pid": os.getpid(), "llama_pid": process.pid,
            "llama_executable": str(Path(config["llama_server"]).absolute()),
            "processes": [{"pid": pid, "executable": psutil.Process(pid).exe(),
                           "created": psutil.Process(pid).create_time()} for pid in [process.pid, os.getpid()]],
            "started": time.time()}), encoding="utf-8")
        print(f"STS Kit: http://127.0.0.1:{config['web_port']}", flush=True)
        if "--no-browser" not in __import__("sys").argv:
            import threading
            def open_when_ready():
                with httpx.Client(trust_env=False, timeout=2) as client:
                    for _ in range(120):
                        try:
                            if client.get(f"http://127.0.0.1:{config['web_port']}/api/health").json()["ready"]:
                                webbrowser.open(f"http://127.0.0.1:{config['web_port']}")
                                return
                        except Exception:
                            pass
                        time.sleep(1)
            threading.Thread(target=open_when_ready, daemon=True).start()
        uvicorn.run("sts.app:app", host="127.0.0.1", port=config["web_port"],
                    ws_max_size=5_500_000, ws_per_message_deflate=False, log_level="info")
    finally:
        cleanup()


if __name__ == "__main__":
    main()

"""Audit the current Git-visible files, without printing possible secret values."""
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
names = subprocess.check_output(['git', 'ls-files', '--cached', '--others', '--exclude-standard', '-z'], cwd=ROOT).decode('utf-8').split('\0')
blocked_dirs = {'models', 'runtime', 'vendor', 'run', 'logs', '.cache', '.venv', '.venv-audio', '.venv-cosy', '.venv-test', '.venv-download'}
blocked_suffixes = {'.wav', '.mp3', '.gguf', '.safetensors', '.onnx', '.pt', '.pth', '.pem', '.key'}
secrets = re.compile(r'(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,}|hf_[A-Za-z0-9]{30,}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----)')
personal_path = re.compile(r'[A-Z]:[/\\](?:Users[/\\][^/\\\s]+|ドキュメント|LLM)', re.I)
failures = []
for name in sorted(set(filter(None, names))):
    path = ROOT / name
    if not path.is_file():
        continue
    if (Path(name).parts[0] in blocked_dirs or path.suffix.lower() in blocked_suffixes or
            path.name == 'config.local.json' or (path.name.startswith('.env') and path.name != '.env.example')):
        failures.append(f'{name}: private/generated file is Git-visible')
        continue
    if path.stat().st_size > 1_000_000:
        failures.append(f'{name}: unexpectedly large file')
        continue
    try:
        content = path.read_text(encoding='utf-8')
    except UnicodeError:
        failures.append(f'{name}: unexpected binary file')
        continue
    for number, line in enumerate(content.splitlines(), 1):
        if secrets.search(line):
            failures.append(f'{name}:{number}: possible secret (value redacted)')
        if personal_path.search(line):
            failures.append(f'{name}:{number}: machine-specific path')
    if path.suffix == '.md':
        for target in re.findall(r'\]\(([^)]+)\)', content):
            target = target.split('#')[0]
            if not target or '://' in target or target.startswith('mailto:'):
                continue
            if not (path.parent / target).exists():
                failures.append(f'{name}: broken local link {target}')
if failures:
    print('\n'.join(failures))
    raise SystemExit(1)
print(f'Public-file audit passed ({len(set(filter(None, names)))} Git-visible files). This is not a full secret or dependency audit.')

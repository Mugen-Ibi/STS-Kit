"""Local diagnostic recordings must not be sent through environment proxies."""
import ast
from pathlib import Path


def test_loopback_websocket_clients_explicitly_disable_proxies():
    scripts = Path(__file__).resolve().parents[1] / 'scripts'
    checked = []
    for path in sorted(scripts.glob('*.py')):
        for node in ast.walk(ast.parse(path.read_text(encoding='utf-8'))):
            if not isinstance(node, ast.Call) or not node.args:
                continue
            address = node.args[0]
            if not isinstance(address, ast.Constant) or not isinstance(address.value, str):
                continue
            if not address.value.startswith('ws://127.0.0.1:'):
                continue
            options = {option.arg: option.value for option in node.keywords}
            assert 'proxy' in options, path.name
            assert isinstance(options['proxy'], ast.Constant) and options['proxy'].value is None, path.name
            checked.append(path.name)
    assert set(checked) == {'benchmark.py', 'check_limits.py', 'smoke_test.py',
                            'test_voice_api.py', 'verify_roleplay.py', 'verify_voice_readback.py'}

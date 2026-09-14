"""Exercise the real headless executable and stdio lifecycle without a display."""
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import tempfile
import threading
import time

exe, fixtures = map(Path, sys.argv[1:])
assert any(p.is_file() for p in (exe.parent / 'AI-HEADLESS.md', exe.parent.parent / 'Resources/AI-HEADLESS.md')), 'Missing AI headless instructions beside executable'
args = [str(exe), '--headless', '--apk', str(fixtures / 'cases.dex'), '--deobfuscate', '--unflatten']
env = dict(os.environ, QT_QPA_PLATFORM='intentionally-unavailable')
config = json.loads(subprocess.check_output(args + ['--print-mcp-config'], env=env, timeout=10))
server = config['mcpServers']['garlic']
assert '--headless' in server['args'] and '--unflatten' in server['args']
assert subprocess.run([str(exe), '--headless', '--apk', '/missing/input.apk'], env=env,
                      capture_output=True, timeout=10).returncode != 0
with tempfile.TemporaryFile(mode='w+') as log:
    proc = subprocess.Popen([server['command'], *server['args']], stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE, stderr=log, text=True, env=env)
    replies = queue.Queue()
    def read():
        for line in proc.stdout:
            replies.put(line)
    threading.Thread(target=read, daemon=True).start()
    serial = 0
    def call(method, params=None):
        global serial
        serial += 1
        proc.stdin.write(json.dumps(dict(jsonrpc='2.0', id=serial, method=method, params=params or {})) + '\n')
        proc.stdin.flush()
        response = json.loads(replies.get(timeout=30))
        assert response['id'] == serial, response
        assert 'error' not in response, response
        return response['result']
    def tool(name, arguments=None):
        result = call('tools/call', dict(name=name, arguments=arguments or {}))
        assert not result.get('isError'), result
        return json.loads(result['content'][0]['text'])
    try:
        assert 'protocolVersion' in call('initialize', {'protocolVersion': '2024-11-05', 'capabilities': {}, 'clientInfo': {'name': 'test', 'version': '1'}})
        assert any(t['name'] == 'get_status' for t in call('tools/list')['tools'])
        deadline = time.monotonic() + 30
        while True:
            status = tool('get_status')
            if status['class_count'] and not status['busy']:
                break
            assert time.monotonic() < deadline, status
            time.sleep(0.05)
        classes = tool('get_all_classes')
        assert classes['total'] >= 2, classes
        source = tool('get_class_source', {'class_name': classes['classes'][0]['name']})
        assert 'class ' in json.dumps(source), source
        settings = tool('get_settings')
        assert settings['deobfuscate'] and settings['unflatten'], settings
        for _ in range(60):
            assert tool('get_all_classes')['total'] == classes['total']
        if os.name == 'posix':
            processes = subprocess.check_output(['ps', '-axo', 'ppid=,command='], text=True)
            assert not any(line.split(None, 1)[0] == str(proc.pid) and '--mcp' in line
                           for line in processes.splitlines() if line.split()), processes
        proc.stdin.close()
        assert proc.wait(timeout=15) == 0
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait()
        log.seek(0)
        print(log.read(), file=sys.stderr)
print('Headless MCP startup, config, source and EOF passed')

# Repeated early EOF must not leave headless sessions behind.
for _ in range(4):
    p = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                         stderr=subprocess.DEVNULL, env=env)
    p.stdin.close()
    try:
        assert p.wait(timeout=15) == 0
    finally:
        if p.poll() is None:
            p.kill(); p.wait()

# HTTP defaults to loopback, permits an explicit address, and reaps on SIGTERM.
for host in (None, '127.0.0.1', '0.0.0.0'):
    import urllib.request
    with tempfile.TemporaryFile(mode='w+') as log:
        command = args + ['--http-port', '0'] + (['--http-host', host] if host else [])
        p = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=log, env=env)
        try:
            deadline = time.monotonic() + 15
            url = None
            while not url:
                log.seek(0)
                for line in log.read().splitlines():
                    if line.startswith('MCP URL: '): url = line.removeprefix('MCP URL: ')
                assert time.monotonic() < deadline
                time.sleep(.05)
            assert url.startswith('http://127.0.0.1:')
            request = urllib.request.Request(url, data=json.dumps(dict(jsonrpc='2.0', id=1, method='initialize')).encode(),
                                             headers={'Content-Type': 'application/json'})
            with urllib.request.urlopen(request, timeout=5) as response:
                assert 'result' in json.load(response)
            p.terminate()
            p.wait(timeout=15)
            if os.name == 'posix': assert p.returncode == 0
        finally:
            if p.poll() is None: p.kill(); p.wait()
assert subprocess.run(args + ['--http-port', '0', '--http-host', 'invalid'], env=env,
                      capture_output=True, timeout=10).returncode != 0
print('Repeated calls, EOF, HTTP bind addresses and termination passed')

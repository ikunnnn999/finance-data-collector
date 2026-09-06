"""Portable launcher: provision a workspace-local venv, then run the bundled engine."""
import argparse
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import venv


def main():
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument('--runtime-dir', type=Path, default=Path.cwd() / 'work/stock-quant-runtime')
    parser.add_argument('--use-current-python', action='store_true')
    options, forwarded = parser.parse_known_args()
    if not forwarded or '--help' in forwarded or '-h' in forwarded:
        print('Usage: python analyze.py NVDA [MSFT ...] or 600519 [000001 ...] [options]\n'
              'Downloads US or Shanghai/Shenzhen prices; generates HTML, Markdown, PNG and CSV.\n'
              'Options: --market auto|us|cn --benchmark TICKER --start YYYY-MM-DD --end YYYY-MM-DD\n'
              '         --train-end YYYY-MM-DD --cost-bps 10 --include-ml\n'
              '         --output-dir PATH (must be empty)\n'
              'Offline: --prices-dir PATH --ff3 FILE --ff5 FILE\n'
              'China: --cn-calendar FILE --cn-factors FILE (CN metadata JSON required) --cn-rf-annual 0\n'
              'Runtime: --runtime-dir PATH or --use-current-python\n'
              'Default: creates an isolated workspace-local venv on first run. Python 3.11+ required.')
        return 0
    if sys.version_info < (3, 11):
        raise SystemExit('Python 3.11 or newer is required')
    here = Path(__file__).resolve().parent
    requirements = here / 'requirements.txt'
    if options.use_current_python:
        executable = Path(sys.executable)
        subprocess.run([str(executable), '-c', 'import pandas,numpy,scipy,statsmodels,matplotlib,akshare'], check=True)
    else:
        runtime = options.runtime_dir.resolve()
        executable = runtime / ('Scripts/python.exe' if sys.platform == 'win32' else 'bin/python')
        if not executable.exists():
            if runtime.exists() and any(runtime.iterdir()) and not (runtime / 'pyvenv.cfg').exists():
                raise SystemExit('Runtime directory contains unrelated files; choose an empty --runtime-dir')
            print(f'Creating isolated Python environment: {runtime}', flush=True)
            venv.EnvBuilder(with_pip=True).create(runtime)
        fingerprint = hashlib.sha256(requirements.read_bytes()).hexdigest()
        marker = runtime / '.stock-quant-requirements.sha256'
        if not marker.exists() or marker.read_text().strip() != fingerprint:
            print('Installing stock-quant-report dependencies into its isolated environment...', flush=True)
            subprocess.run([str(executable), '-m', 'pip', 'install', '--disable-pip-version-check', '-r', str(requirements)], check=True, timeout=600)
            marker.write_text(fingerprint, encoding='utf-8')
    environment = dict(os.environ)
    environment['PYTHONUTF8'] = '1'
    return subprocess.run([str(executable), str(here / 'engine/stock_report.py'), *forwarded], env=environment).returncode


if __name__ == '__main__':
    raise SystemExit(main())

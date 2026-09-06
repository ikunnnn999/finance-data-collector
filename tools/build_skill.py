"""Bundle the canonical project engine so a GitHub subfolder install is sufficient."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FILES = ['stock_report.py', 'run_research.py', 'indicators/__init__.py', 'indicators/fama_french.py',
         'quant/__init__.py', 'quant/data.py', 'quant/metrics.py', 'quant/portfolio.py',
         'quant/backtest.py', 'quant/direction.py']


def main():
    target = ROOT / 'skills/stock-quant-report/scripts/engine'
    checksums = {}
    for relative in FILES:
        source = ROOT / relative
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        # Normalize text so bundle validation is independent of checkout line endings.
        content = source.read_text(encoding='utf-8-sig').replace('\r\n', '\n')
        destination.write_text(content, encoding='utf-8', newline='\n')
        checksums[relative] = hashlib.sha256(content.encode('utf-8')).hexdigest()
    (target / 'bundle-manifest.json').write_text(json.dumps(checksums, indent=2) + '\n', encoding='utf-8')
    print(f'Bundled {len(FILES)} engine files into {target}')


if __name__ == '__main__':
    main()

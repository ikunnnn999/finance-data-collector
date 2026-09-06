"""Compatibility entry: run the unified portfolio and strategy research pipeline."""
import sys
from pathlib import Path

if __name__ == '__main__':
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from run_research import main
    main()

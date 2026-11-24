"""Engineering recovery utility: rebuild a session workbook from cycles.jsonl.

Usage (on a development PC with Python): python rebuild_excel.py records/Run_YYYYMMDD...
Not part of the production EXE interface.
"""
import sys
from pathlib import Path
from session_runner import rebuild_excel
if __name__ == '__main__':
    if len(sys.argv)!=2:
        raise SystemExit('Usage: python rebuild_excel.py <session folder>')
    print(rebuild_excel(Path(sys.argv[1])))

"""V3600GS CLI parser. Never infer online state from timestamps or optical fields."""
from __future__ import annotations
import re

GPON_PROMPT = 'gpon-olt(config-pon-0/1)#'
TIME_ROW = re.compile(
    r'^\s*(?P<port>\d+/\d+)\s*'
    r'(?P<reg>\d{4}:\d{2}:\d{2}\s+\d{2}:\d{2}:\d{2}|N/A)\s*'
    r'(?P<dereg>\d{4}:\d{2}:\d{2}\s+\d{2}:\d{2}:\d{2}|N/A)\s*'
    r'(?P<reason>.*?)\s*'
    r'(?P<alive>\d+:\d{2}:\d{2}|N/A)\s*$', re.I)

FIELDS = {
    'Alarm': ('alarm', str),
    'Rx optical level(ONU)': ('rx', float),
    'Tx optical level': ('tx', float),
    'ONU response time': ('response', float),
    'Power feed voltage': ('voltage', float),
    'Laser bias current': ('current', float),
    'Temperature': ('temperature', float),
}


def normalize_terminal_output(raw: str) -> str:
    """Reconstruct Tera Term-style cursor-positioned serial output.

    V3600GS uses CR + ESC[nC to place each time-stamp column at an
    absolute screen column. Splitting on CR before rendering loses rows.
    Render a minimal terminal line: CR resets cursor, ESC[nC moves right,
    LF commits the line. Unknown formatting CSI sequences are ignored.
    """
    lines = []
    cells = []
    cursor = 0
    i = 0
    def flush():
        nonlocal cells, cursor
        lines.append(''.join(cells).rstrip())
        cells = []
        cursor = 0
    while i < len(raw):
        ch = raw[i]
        if ch == '\x1b' and i+1 < len(raw) and raw[i+1] == '[':
            m = re.match(r'\x1b\[([0-9;?]*)([@-~])', raw[i:])
            if m:
                args, op = m.groups()
                count = int(args.split(';')[0]) if args and args.split(';')[0].isdigit() else 1
                if op == 'C':
                    cursor += min(count, 10000)
                elif op == 'D':
                    cursor = max(0, cursor-min(count,10000))
                elif op == 'G':
                    cursor = max(0, count-1)
                i += len(m.group(0))
                continue
        if ch == '\r':
            cursor = 0
        elif ch == '\n':
            flush()
        elif ch == '\b':
            cursor = max(0,cursor-1)
        elif ch == '\t':
            cursor = (cursor//8+1)*8
        elif ch.isprintable() and ch != '\x7f':
            if cursor < 100000:
                if len(cells) <= cursor:
                    cells.extend(' '*(cursor+1-len(cells)))
                cells[cursor] = ch
                cursor += 1
        i += 1
    if cells:
        flush()
    return '\n'.join(lines)


def parse_time_stamp(output: str) -> dict[int, dict]:
    """Handle whitespace-separated AND vendor logs with merged columns.

    Example: 1/12026:11:23 16:47:05N/AN/A20:52:29
    """
    items = {}
    for line in normalize_terminal_output(output.replace('\x00', '')).splitlines():
        line = line.strip()
        match = TIME_ROW.match(line)
        if not match:
            continue
        v = {k: (val.strip() or 'N/A') for k, val in match.groupdict().items()}
        onu = int(v['port'].split('/')[-1])
        if onu in items:
            raise ValueError(f'Duplicate ONU ID in time-stamp: {onu}')
        items[onu] = {'onu_id': onu, 'port_id': v['port'], 'last_regist': v['reg'],
                      'last_deregist': v['dereg'], 'dereg_reason': v['reason'], 'alive': v['alive']}
    if not items:
        raise ValueError('No valid ONU rows in show onu time-stamp output')
    return items


def parse_optical(output: str) -> dict[int, dict]:
    entries: dict[int, dict] = {}
    current = None
    for line in output.replace('\x00', '').splitlines():
        match = re.match(r'^\s*ONU ID\s*:\s*(\d+)\s*$', line, re.I)
        if match:
            onu = int(match.group(1))
            if onu in entries:
                raise ValueError(f'Duplicate ONU ID in optical output: {onu}')
            current = {'onu_id': onu}
            entries[onu] = current
            continue
        if current is None or ':' not in line:
            continue
        key, val = [part.strip() for part in line.split(':', 1)]
        if key not in FIELDS:
            continue
        outkey, typ = FIELDS[key]
        if typ is str:
            current[outkey] = val
            continue
        matchnum = re.fullmatch(r'([-+]?\d+(?:\.\d+)?)\s*(?:\([^)]*\))?', val)
        current[outkey] = float(matchnum.group(1)) if matchnum else None
    if not entries:
        raise ValueError('No ONU ID blocks in show onu optical-info all output')
    return entries


def merge_data(timestamp: dict[int, dict], optical: dict[int, dict]) -> dict[int, dict]:
    union = sorted(set(timestamp) | set(optical))
    merged = {}
    for onu in union:
        item = {'onu_id': onu, 'status': 'NOT VERIFIED'}
        item.update(timestamp.get(onu, {}))
        item.update(optical.get(onu, {}))
        item['data_flag'] = ('OK' if onu in timestamp and onu in optical else
                             'MISSING_TIMESTAMP' if onu not in timestamp else 'MISSING_OPTICAL')
        merged[onu] = item
    return merged

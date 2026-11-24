"""V3600GS CLI parser. Never infer online state from timestamps or optical fields."""
from __future__ import annotations
import re

GPON_PROMPT = 'gpon-olt(config-pon-0/1)#'
TIME_ROW = re.compile(
    r'^\s*(?P<port>\d+/\d+)\s*'
    r'(?P<reg>\d{4}:\d{2}:\d{2}\s+\d{2}:\d{2}:\d{2}|N/A)\s*'
    r'(?P<dereg>\d{4}:\d{2}:\d{2}\s+\d{2}:\d{2}:\d{2}|N/A)\s*'
    r'(?P<reason>.*?)\s*'
    r'(?P<alive>(?:\d+\s+)?\d{2}:\d{2}:\d{2}|N/A)\s*$', re.I)

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

STATE_ROW = re.compile(
    r'^\s*(?P<pon>\d+)\s*:\s*(?P<id>\d+)\s+'
    r'(?P<admin>\S+)\s+(?P<omcc>\S+)\s+(?P<phase>\S+)\s+'
    r'(?P<channel>\S+)\s+(?P<serial>\S+)\s*$', re.I)


def parse_onu_state(output: str) -> dict[int, dict]:
    """Parse latest complete `show onu state` table, including repeated queries.

    Never interpret an unsolicited 'ONU Online' event as a row. CLI text may
    contain ANSI positioning; use the same terminal normalization as timestamps.
    """
    text = normalize_terminal_output(output.replace('\x00', ''))
    tables: list[list[str]] = []
    current: list[str] | None = None
    for line in text.splitlines():
        if re.search(r'\bOnuIndex\b.*\bPhase\s+State\b.*\bSerial\s+Number\b', line, re.I):
            if current is not None:
                tables.append(current)
            current = []
        elif current is not None:
            if re.search(r'gpon-olt\(', line, re.I) or re.match(r'^\s*total\s*:', line, re.I):
                tables.append(current)
                current = None
            else:
                current.append(line)
    if current is not None:
        tables.append(current)
    if not tables:
        raise ValueError('No ONU state table header in show onu state output')
    parsed = {}
    for line in tables[-1]:
        m = STATE_ROW.match(line)
        if not m:
            continue
        d = m.groupdict()
        onu = int(d['id'])
        if onu in parsed:
            raise ValueError(f'Duplicate ONU ID in state: {onu}')
        phase = d['phase'].lower()
        result = 'PASS' if phase == 'working' else 'FAIL'
        parsed[onu] = {
            'onu_id': onu, 'pon_index': d['pon'], 'gpon_sn': d['serial'],
            'admin_state': d['admin'], 'omcc_state': d['omcc'],
            'phase_state': d['phase'], 'channel': d['channel'],
            'status': result,
        }
    if not parsed:
        raise ValueError('No valid ONU rows in show onu state output')
    return parsed


def merge_state_data(state: dict[int, dict], timestamp: dict[int, dict],
                     optical: dict[int, dict]) -> dict[int, dict]:
    ids = sorted(set(state) | set(timestamp) | set(optical))
    result = {}
    for onu in ids:
        item = {'onu_id': onu, 'status': 'UNKNOWN'}
        item.update(timestamp.get(onu, {}))
        item.update(optical.get(onu, {}))
        item.update(state.get(onu, {}))
        missing = [name for name, source in [('STATE', state), ('TIMESTAMP', timestamp),
                                              ('OPTICAL', optical)] if onu not in source]
        item['data_flag'] = 'OK' if not missing else 'MISSING_' + '_'.join(missing)
        result[onu] = item
    return result

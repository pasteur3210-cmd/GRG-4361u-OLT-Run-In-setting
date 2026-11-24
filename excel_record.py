"""Minimal standards-compliant XLSX exporter using Python stdlib only.

One Excel row per check cycle. Dynamic ONU ID columns (not limited to 10 or 16).
No Excel framework/runtime dependency, making the bundled Windows EXE straightforward.
"""
from __future__ import annotations
import html
import os
import tempfile
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
from xml.sax.saxutils import escape

FIELDS = [('status','ONU Result'), ('gpon_sn','GPON SN'), ('phase_state','Phase State'),
          ('channel','Channel'), ('port_id','PON/ONU'),
          ('last_regist','Last Regist'), ('last_deregist','Last Deregist'),
          ('dereg_reason','Dereg Reason'), ('alive','Alive Time'),
          ('rx','ONU Rx'), ('tx','ONU Tx'), ('voltage','Voltage(V)'),
          ('current','Bias(mA)'), ('temperature','Temp(C)'),
          ('ping_result','IP PING Result'), ('ping_loss','PING Loss')]
BASE_HEADERS = ['Cycle','Check Time','Overall Result','ONU Count','Cycle Error']


def col_name(idx):
    result = ''
    while idx:
        idx, rem = divmod(idx-1,26)
        result = chr(65+rem)+result
    return result


def cell_xml(ref, value, style=0):
    attr = f' r="{ref}" s="{style}"'
    if isinstance(value, (float,int)) and not isinstance(value,bool):
        return f'<c{attr}><v>{value}</v></c>'
    if value is None:
        return f'<c{attr} t="inlineStr"><is><t></t></is></c>'
    val = escape(str(value).replace('\x00',''))
    return f'<c{attr} t="inlineStr"><is><t xml:space="preserve">{val}</t></is></c>'


def sheet_xml(rows, *, header=True, freeze=True, col_width=18):
    out = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
           '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">',
           f'<sheetViews><sheetView workbookViewId="0">'+
           ('<pane xSplit="4" ySplit="1" topLeftCell="E2" activePane="bottomRight" state="frozen"/>' if freeze else '')+
           '</sheetView></sheetViews>',
           f'<sheetFormatPr defaultRowHeight="16"/>',
           f'<cols><col min="1" max="{max((len(r) for r in rows),default=1)}" width="{col_width}" customWidth="1"/></cols>',
           '<sheetData>']
    for ri, row in enumerate(rows, 1):
        style = 1 if header and ri==1 else (2 if ri%2==0 else 0)
        out.append(f'<row r="{ri}">')
        for ci, value in enumerate(row,1):
            out.append(cell_xml(col_name(ci)+str(ri), value, style))
        out.append('</row>')
    out.append('</sheetData>')
    if rows:
        out.append(f'<autoFilter ref="A1:{col_name(max(len(r) for r in rows))}{len(rows)}"/>')
    out.append('</worksheet>')
    return ''.join(out)


def xlsx_bytes(sheets):
    import io
    buf=io.BytesIO()
    ns='http://schemas.openxmlformats.org/spreadsheetml/2006/main'
    sheets_meta=''.join(f'<sheet name="{escape(name)}" sheetId="{i}" r:id="rId{i}"/>' for i,(name,_) in enumerate(sheets,1))
    rels=''.join(f'<Relationship Id="rId{i}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{i}.xml"/>' for i in range(1,len(sheets)+1))
    types=''.join(f'<Override PartName="/xl/worksheets/sheet{i}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>' for i in range(1,len(sheets)+1))
    with ZipFile(buf,'w',ZIP_DEFLATED) as z:
        z.writestr('[Content_Types].xml',f'<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>{types}</Types>')
        z.writestr('_rels/.rels','<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>')
        z.writestr('xl/workbook.xml',f'<?xml version="1.0" encoding="UTF-8"?><workbook xmlns="{ns}" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>{sheets_meta}</sheets></workbook>')
        z.writestr('xl/_rels/workbook.xml.rels',f'<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">{rels}<Relationship Id="rId{len(sheets)+1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>')
        z.writestr('xl/styles.xml','''<?xml version="1.0" encoding="UTF-8"?><styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><fonts count="2"><font><sz val="11"/><name val="Aptos"/></font><font><b/><color rgb="FFFFFFFF"/><sz val="11"/><name val="Aptos"/></font></fonts><fills count="3"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill><fill><patternFill patternType="solid"><fgColor rgb="FF17365D"/><bgColor indexed="64"/></patternFill></fill></fills><borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders><cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs><cellXfs count="3"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/><xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0" applyFill="1" applyFont="1"/><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/></cellXfs></styleSheet>''')
        for idx,(_,rows) in enumerate(sheets,1):
            z.writestr(f'xl/worksheets/sheet{idx}.xml',sheet_xml(rows,freeze=(idx==1),col_width=19 if idx==1 else 21))
    return buf.getvalue()


def build_rows(cycles, expected_onu_ids=None, mapping=None):
    """Create one summary row per cycle; stable columns keyed by actual ONU ID.

    All ONU IDs across the input cycles share a fixed column mapping. A missing
    ONU is recorded as MISSING THIS CYCLE, not silently shifted or marked offline.
    Sparse IDs (e.g. 1, 3, 16) do not allocate fake ONU 2..15 columns.
    """
    mapping=mapping or {}
    known_ids = set(expected_onu_ids or []) | set(mapping)
    for cycle in cycles:
        known_ids.update(cycle['onus'])
    if any(not isinstance(onu, int) or isinstance(onu, bool) or onu <= 0 for onu in known_ids):
        raise ValueError('ONU IDs must be positive integers')
    ids = sorted(known_ids)
    if len(BASE_HEADERS) + len(ids)*len(FIELDS) > 16384:
        raise ValueError('Excel column limit exceeded')
    columns = BASE_HEADERS[:]
    for onu in ids:
        columns.extend(f'ONU{onu}_{label}' for _, label in FIELDS)
    summary = [columns]
    detail = [['Cycle', 'Check Time', 'ONU ID'] + [label for _, label in FIELDS]]
    for i, cycle in enumerate(cycles, 1):
        units = cycle['onus']
        ts = cycle['time']
        expected = set(ids)
        missing_ids = expected - set(units)
        if cycle.get('result'):
            result = cycle['result']
        elif cycle.get('error'):
            result = 'ERROR'
        elif any(item.get('status') == 'FAIL' for item in units.values()):
            result = 'FAIL'
        elif missing_ids or any(item.get('status') != 'PASS' or item.get('data_flag') != 'OK'
                                for item in units.values()):
            result = 'INCOMPLETE'
        else:
            result = 'PASS'
        row = [cycle.get('cycle', i), ts, result, len(units), cycle.get('error', '')]
        for onu in ids:
            if onu in units:
                item = units[onu]
                pr=cycle.get('ping',{}).get(str(onu),{})
                vals=[pr.get('result','NOT CONFIGURED') if k=='ping_result' else
                      (str(pr['loss'])+'/4' if pr.get('loss') is not None else 'N/A') if k=='ping_loss' else
                      item.get(k) for k,_ in FIELDS]
                row.extend(vals)
                detail.append([cycle.get('cycle', i), ts, onu] + vals)
            else:
                row.extend(('UNKNOWN' if k == 'status' else
                            cycle.get('ping',{}).get(str(onu),{}).get('result','NOT CONFIGURED') if k == 'ping_result' else
                            str(cycle.get('ping',{}).get(str(onu),{}).get('loss'))+'/4' if k=='ping_loss' and cycle.get('ping',{}).get(str(onu),{}).get('loss') is not None else None)
                           for k, _ in FIELDS)
        summary.append(row)
    event_rows = [['Cycle','Check Time','ONU ID','GPON SN','Previous Phase','Current Phase','Event']]
    previous = {}
    for i, cycle in enumerate(cycles, 1):
        for onu, item in sorted(cycle['onus'].items()):
            current = item.get('phase_state')
            if not current:
                continue
            before = previous.get(onu)
            if before is None:
                if current.lower() != 'working':
                    event_rows.append([cycle.get('cycle',i),cycle['time'],onu,item.get('gpon_sn'),
                                       'NOT OBSERVED',current,'INITIAL ABNORMAL'])
            elif before != current:
                event_rows.append([cycle.get('cycle',i),cycle['time'],onu,item.get('gpon_sn'),
                                   before,current,'RECOVERY' if current.lower()=='working' else 'STATE CHANGE'])
            previous[onu]=current
    mapping_rows=[['ONU ID','GPON SN','DUT IP','WAN MAC (ARP)','LAN MAC (-1)','Pre-Run Mapping']]
    for onu,entry in sorted(mapping.items()):
        mapping_rows.append([onu,entry['gpon_sn'],entry['ip'],entry['mac'],entry.get('lan_mac',''),'MATCH'])
    last_ping={}
    for i,cycle in enumerate(cycles,1):
        for onu_key, p in sorted(cycle.get('ping',{}).items(),key=lambda kv:int(kv[0])):
            onu=int(onu_key)
            current=p.get('result','ERROR')
            prev=last_ping.get(onu)
            if (prev is None and current in ('FAIL','ERROR')) or (prev is not None and prev!=current):
                event_rows.append([cycle.get('cycle',i),cycle['time'],onu,
                                   mapping.get(onu,{}).get('gpon_sn',''),prev or 'NOT OBSERVED',current,
                                   'PING RECOVERY' if current=='PASS' else 'PING STATUS CHANGE'])
            last_ping[onu]=current
    notes = [['Field', 'Explanation'],
             ['ONU columns', 'Automatically based on all actual ONU IDs; no 10/16 ONU hard limit'],
             ['Missing This Cycle', 'ONU ID not returned this cycle; NOT equivalent to Offline'],
             ['Status', 'PASS if Phase State working; FAIL for other observed states; UNKNOWN for missing state'],
             ['Ping Result', 'PASS 0/4 lost; WARNING 1/4; FAIL >=2/4; ERROR cannot determine loss'],
             ['N/A', 'Device returned N/A; do not interpret as PASS'],
             ['Units', 'Rx/Tx are raw CLI values; confirm dBm with product specification'],
             ['Mapping rule', 'ARP WAN MAC minus 1 (full 48-bit), then compare last 6 hex digits with GPON SN'],
             ['Source', 'show onu state + show onu time-stamp + show onu optical-info all']]
    return [('01_Loop_Summary', summary), ('02_ONU_Detail', detail), ('03_IP_Mapping', mapping_rows), ('04_Event_Log', event_rows), ('05_Field_Notes', notes)]

def export_cycles(path: Path, cycles: list[dict], mapping=None):
    path=Path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    data=xlsx_bytes(build_rows(cycles, mapping=mapping))
    fd,tmp=tempfile.mkstemp(suffix='.xlsx',dir=str(path.parent))
    try:
        with os.fdopen(fd,'wb') as fp:fp.write(data)
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp): os.unlink(tmp)
    return path

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

FIELDS = [('status','Status'), ('data_flag','Data Flag'), ('port_id','PON/ONU'),
          ('last_regist','Last Regist'), ('last_deregist','Last Deregist'),
          ('dereg_reason','Dereg Reason'), ('alive','Alive Time'),
          ('rx','ONU Rx'), ('tx','ONU Tx'), ('voltage','Voltage(V)'),
          ('current','Bias(mA)'), ('temperature','Temp(C)'),
          ('response','Response'), ('alarm','Alarm')]
BASE_HEADERS = ['Cycle','Check Time','Check Result','ONU Count']


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


def build_rows(cycles, expected_onu_ids=None):
    """Create one summary row per cycle; stable columns keyed by actual ONU ID.

    All ONU IDs across the input cycles share a fixed column mapping. A missing
    ONU is recorded as MISSING THIS CYCLE, not silently shifted or marked offline.
    Sparse IDs (e.g. 1, 3, 16) do not allocate fake ONU 2..15 columns.
    """
    known_ids = set(expected_onu_ids or [])
    for cycle in cycles:
        known_ids.update(cycle['onus'])
    if any(not isinstance(onu, int) or isinstance(onu, bool) or onu <= 0 for onu in known_ids):
        raise ValueError('ONU IDs must be positive integers')
    ids = sorted(known_ids)
    columns = BASE_HEADERS[:]
    for onu in ids:
        columns.extend(f'ONU{onu}_{label}' for _, label in FIELDS)
    summary = [columns]
    detail = [['Cycle', 'Check Time', 'ONU ID'] + [label for _, label in FIELDS]]
    for i, cycle in enumerate(cycles, 1):
        units = cycle['onus']
        ts = cycle['time']
        complete = bool(units) and all(item.get('data_flag') == 'OK' for item in units.values())
        if any(onu not in units for onu in ids):
            complete = False
        result = 'DATA RECORDED (STATUS UNVERIFIED)' if complete else 'DATA INCOMPLETE'
        row = [i, ts, result, len(units)]
        for onu in ids:
            if onu in units:
                item = units[onu]
                row.extend(item.get(k) for k, _ in FIELDS)
                detail.append([i, ts, onu] + [item.get(k) for k, _ in FIELDS])
            else:
                row.extend(('NOT VERIFIED' if k == 'status' else
                            'MISSING THIS CYCLE' if k == 'data_flag' else None)
                           for k, _ in FIELDS)
        summary.append(row)
    notes = [['Field', 'Explanation'],
             ['ONU columns', 'Automatically based on all actual ONU IDs; no 10/16 ONU hard limit'],
             ['Missing This Cycle', 'ONU ID not returned this cycle; NOT equivalent to Offline'],
             ['Status', 'NOT VERIFIED: timestamp and optical fields do not prove Online/Offline'],
             ['Data Flag', 'OK if two commands match, otherwise MISSING_TIMESTAMP / MISSING_OPTICAL'],
             ['N/A', 'Device returned N/A; do not interpret as PASS'],
             ['Units', 'Rx/Tx are raw CLI values; confirm dBm with product specification'],
             ['Source', 'show onu time-stamp + show onu optical-info all']]
    return [('01_Loop_Summary', summary), ('02_ONU_Detail', detail), ('03_Field_Notes', notes)]

def export_cycles(path: Path, cycles: list[dict]):
    path=Path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    data=xlsx_bytes(build_rows(cycles))
    fd,tmp=tempfile.mkstemp(suffix='.xlsx',dir=str(path.parent))
    try:
        with os.fdopen(fd,'wb') as fp:fp.write(data)
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp): os.unlink(tmp)
    return path

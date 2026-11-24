"""Windows IPv4 Ping and strict IP<->ARP MAC<->GPON SN association.

ARP neighbor entries are treated as WAN MAC; WAN MAC minus one yields
LAN MAC, whose last 6 hexadecimal characters must uniquely match a discovered ONU's GPON SN suffix. No index/order pairing.
"""
from __future__ import annotations
import concurrent.futures
import ipaddress
import re
import subprocess
import time

MAC_RE = re.compile(r'(?i)(?<![0-9a-f])(?:[0-9a-f]{2}[:-]){5}[0-9a-f]{2}(?![0-9a-f])')
TTL_RE = re.compile(r'(?i)\bTTL\s*=\s*\d+')


def normalize_ips(value):
    if isinstance(value, str):
        items = re.split(r'[\s,;]+', value.strip())
    else:
        items = list(value)
    ips=[]
    for item in items:
        if not str(item).strip():
            continue
        try:
            addr=ipaddress.ip_address(str(item).strip())
        except ValueError as exc:
            raise ValueError('Invalid IP: '+str(item)) from exc
        if addr.version != 4:
            raise ValueError('IPv4 required')
        if addr.is_multicast or addr.is_unspecified or addr.is_loopback or addr.is_link_local or addr.is_reserved:
            raise ValueError('DUT IPv4 unicast LAN address required: '+str(addr))
        ip=str(addr)
        if ip in ips:
            raise ValueError('Duplicate IP: '+ip)
        ips.append(ip)
    if not ips:
        raise ValueError('No DUT IPs supplied')
    if len(ips)>256:
        raise ValueError('Too many DUT IPs (max 256)')
    return ips


def suffix(value):
    return re.sub(r'[^0-9a-fA-F]', '', str(value or '')).upper()[-6:]


def wan_to_lan_mac(wan_mac):
    """Derive full 48-bit LAN MAC = WAN MAC - 1; reject invalid/underflow.

    Do not subtract from the last nibble or last byte alone: borrow matters.
    """
    normalized = re.sub(r'[:-]', '', str(wan_mac or '')).upper()
    if not re.fullmatch(r'[0-9A-F]{12}', normalized):
        raise ValueError('Invalid 48-bit WAN MAC')
    value = int(normalized, 16)
    if value == 0 or value == (1 << 48) - 1:
        raise ValueError('Invalid/reserved WAN MAC')
    return f'{value - 1:012X}'


def run_ping(ip, *, count=4, wait_ms=1000, runner=subprocess.run):
    """Ping Windows host; count received TTL replies (works across localized Windows).

    Command errors/timeouts are ERROR, not packet-loss FAIL; never return PASS
    when the packet count cannot be independently established.
    """
    if count < 1 or count > 100:
        raise ValueError('Ping count invalid')
    try:
        output=runner(['ping','-4','-n',str(count),'-w',str(wait_ms),ip],
                      capture_output=True, text=True, errors='replace',
                      timeout=max(8, count*wait_ms/1000 + 7), shell=False)
        raw=(output.stdout or '')+'\n'+(output.stderr or '')
        received=len(TTL_RE.findall(raw))
        # Other command errors may include zero responses; distinguish from 100% loss.
        if output.returncode not in (0,1) or (output.returncode != 0 and not raw.strip()):
            return {'result':'ERROR','loss':None,'received':None,'sent':count,'error':f'Ping exit code {output.returncode}','raw':raw}
        if received > count:
            return {'result':'ERROR','loss':None,'received':None,'sent':count,'error':'Unexpected Ping reply count','raw':raw}
        if received==0 and output.returncode==1 and re.search(r'(?i)could not find host|general failure|ping request could not find|找不到主機|一般失敗|無法找到',raw):
            return {'result':'ERROR','loss':None,'received':None,'sent':count,'error':'Ping command/network failure','raw':raw}
        lost=count-received
        result='FAIL' if lost>=2 else ('WARNING' if lost==1 else 'PASS')
        return {'result':result,'loss':lost,'received':received,'sent':count,'error':'','raw':raw}
    except (OSError,subprocess.TimeoutExpired) as exc:
        return {'result':'ERROR','loss':None,'received':None,'sent':count,'error':str(exc),'raw':''}


def ping_all(ips, *, count=4, wait_ms=1000, ping_fn=None, workers=16):
    ping_fn=ping_fn or run_ping
    if not ips:
        return {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(max(workers,1),len(ips))) as executor:
        pending={executor.submit(ping_fn,ip,count=count,wait_ms=wait_ms):ip for ip in ips}
        results={}
        for future in concurrent.futures.as_completed(pending):
            ip=pending[future]
            try:results[ip]=future.result()
            except Exception as exc:results[ip]={'result':'ERROR','loss':None,'sent':count,'received':None,'error':str(exc),'raw':''}
    return results


def find_mac(arp_text,ip):
    """Only exact IP neighbor row; never use another row or a gateway MAC."""
    for line in arp_text.splitlines():
        parts=line.split()
        if len(parts)>=2 and parts[0]==ip and MAC_RE.fullmatch(parts[1]):
            mac=parts[1].replace('-','').replace(':','').upper()
            if mac not in ('0'*12,'F'*12):
                return mac
    return None


def read_arp(ip, *, runner=subprocess.run):
    try:
        p=runner(['arp','-a',ip],capture_output=True,text=True,errors='replace',timeout=8,shell=False)
        return find_mac((p.stdout or '')+'\n'+(p.stderr or ''),ip)
    except (OSError,subprocess.TimeoutExpired):
        return None


def verify_mapping(ips, onu_states, *, ping_fn=None, arp_fn=None):
    """Return complete rows and mapping keyed by ONU ID. Never guess associations."""
    ips=normalize_ips(ips)
    if not onu_states:
        return [], {}, ['OLT has no ONU state rows']
    # Preflight Ping warms Windows' neighbor cache; unreachable IP remains unverified.
    ping_results=ping_all(ips,count=1,ping_fn=ping_fn)
    arp_fn=arp_fn or read_arp
    onu_suffixes={}
    for onu,unit in onu_states.items():
        sn=unit.get('gpon_sn','')
        match=suffix(sn)
        if len(match)!=6:
            continue
        onu_suffixes.setdefault(match,[]).append(onu)
    rows=[]
    matched={}
    errors=[]
    used_ids=set()
    used_macs=set()
    for ip in ips:
        ping=ping_results[ip]
        mac=arp_fn(ip)
        lan_mac = ''
        if mac:
            try:
                lan_mac = wan_to_lan_mac(mac)
            except ValueError:
                pass
        tail=suffix(lan_mac)
        candidates=onu_suffixes.get(tail,[]) if lan_mac else []
        status='NOT FOUND'
        onu=None
        if not mac:
            status='MAC NOT FOUND'
        elif not lan_mac:
            status='INVALID WAN MAC'
        elif mac in used_macs:
            status='DUPLICATE MAC'
        elif len(candidates)>1:
            status='AMBIGUOUS'
        elif len(candidates)==0:
            status='MISMATCH'
        elif candidates[0] in used_ids:
            status='DUPLICATE ONU'
        else:
            onu=candidates[0]
            status='MATCH' if ping['result']=='PASS' else 'PING UNREACHABLE'
        if mac:used_macs.add(mac)
        if onu is not None and status=='MATCH':
            used_ids.add(onu)
            matched[onu]={'ip':ip,'mac':mac,'lan_mac':lan_mac,'gpon_sn':onu_states[onu]['gpon_sn']}
        row={'ip':ip,'mac':mac or '', 'lan_mac':lan_mac, 'onu_id':onu, 'gpon_sn':onu_states[onu]['gpon_sn'] if onu is not None else '',
             'ping':ping['result'], 'status':status}
        rows.append(row)
        if status!='MATCH':errors.append(ip+': '+status)
    for onu in sorted(onu_states):
        if onu not in matched:
            errors.append(f'ONU {onu}: no verified DUT IP')
    if len(matched)!=len(ips) or len(matched)!=len(onu_states):
        errors.append('Mapping count mismatch; every configured DUT IP and discovered ONU must be uniquely mapped')
    return rows, matched, errors

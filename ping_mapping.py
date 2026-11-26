"""Windows IPv4 Ping and strict IP<->ARP MAC<->GPON SN association.

ARP neighbor entries may be the LAN MAC itself OR the WAN MAC (LAN+1).
Accept a unique ONU match by direct six-digit suffix or by full 48-bit MAC minus one.
Never subtract one for a direct match. Never guess an ambiguous pairing.
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



def canonical_mac(mac):
    """Validate an observed 48-bit ARP MAC; reject zero and broadcast."""
    value = re.sub(r'[:-]', '', str(mac or '')).upper()
    if not re.fullmatch(r'[0-9A-F]{12}', value) or value in ('0'*12, 'F'*12):
        raise ValueError('Invalid ARP MAC')
    return value


def match_mac_to_onu(mac, suffix_to_onus):
    """Unique match of observed MAC or observed MAC - 1; ambiguity blocks matching.

    Returns (ONU ID or None, accepted LAN MAC, match type, status).
    A GPON suffix matching two different ONUs is always AMBIGUOUS.
    """
    try:
        direct = canonical_mac(mac)
    except ValueError:
        return None, '', '', 'INVALID ARP MAC'
    candidates = []
    for match_type, lan_mac in [('DIRECT', direct)]:
        for onu in suffix_to_onus.get(suffix(lan_mac), []):
            candidates.append((onu,lan_mac,match_type))
    # Underflow makes -1 invalid, but direct matching remains permitted.
    try:
        decrement = wan_to_lan_mac(direct)
    except ValueError:
        decrement = ''
    if decrement:
        for onu in suffix_to_onus.get(suffix(decrement), []):
            candidates.append((onu,decrement,'OFFSET_MINUS_1'))
    unique_onus={c[0] for c in candidates}
    if len(unique_onus)>1 or len(candidates)>1:
        return None, '', '', 'AMBIGUOUS'
    if not candidates:
        return None, '', '', 'MISMATCH'
    onu,lan_mac,match_type=candidates[0]
    return onu,lan_mac,match_type,'MATCH'

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
        observed=arp_fn(ip)
        mac=''
        lan_mac=''
        match_type=''
        onu=None
        if not observed:
            status='MAC NOT FOUND'
        else:
            try:
                mac=canonical_mac(observed)
            except ValueError:
                status='INVALID ARP MAC'
            else:
                if mac in used_macs:
                    status='DUPLICATE MAC'
                else:
                    onu,lan_mac,match_type,status=match_mac_to_onu(mac,onu_suffixes)
                    if status=='MATCH' and onu in used_ids:
                        status='DUPLICATE ONU'
                        onu=None
                        lan_mac=''
                        match_type=''
                    elif status=='MATCH' and ping['result']!='PASS':
                        status='PING UNREACHABLE'
                used_macs.add(mac)
        if onu is not None and status=='MATCH':
            used_ids.add(onu)
            matched[onu]={'ip':ip,'mac':mac,'lan_mac':lan_mac,
                          'match_type':match_type,'gpon_sn':onu_states[onu]['gpon_sn']}
        row={'ip':ip,'mac':mac, 'lan_mac':lan_mac, 'match_type':match_type,
             'onu_id':onu,'gpon_sn':onu_states[onu]['gpon_sn'] if onu is not None else '',
             'ping':ping['result'], 'status':status}
        rows.append(row)
        if status!='MATCH':errors.append(ip+': '+status)
    for onu in sorted(onu_states):
        if onu not in matched:
            errors.append(f'ONU {onu}: no verified DUT IP')
    if len(matched)!=len(ips) or len(matched)!=len(onu_states):
        errors.append('Mapping count mismatch; every configured DUT IP and discovered ONU must be uniquely mapped')
    return rows, matched, errors


# Factory configuration: all DUTs use STATIC IPs, never DHCP.
STATIC_IP_POOL = tuple(f'192.168.2.{i}' for i in range(121, 137))


def discover_static_mapping(onu_states, expected_count, *, pool=STATIC_IP_POOL,
                            ping_fn=None, arp_fn=None):
    """Discover sparse static DUT IPs, then validate the complete OLT roster.

    An unreachable IP is NOT silently considered absent: the operator supplied
    expected_count and the OLT ONU count must both agree with verified matches.
    Unmatched responding IPs in the reserved DUT pool are an ambiguity/error.
    """
    if not isinstance(expected_count, int) or isinstance(expected_count, bool) or not (1 <= expected_count <= 16):
        raise ValueError('Expected DUT count must be 1..16')
    ips=normalize_ips(pool)
    if len(ips)!=16 or len(set(ips))!=16:
        raise ValueError('Invalid static IP pool')
    observed=ping_all(ips,count=1,ping_fn=ping_fn)
    responsive=[ip for ip in ips if observed[ip]['result']=='PASS']
    errors=[]
    if len(onu_states)!=expected_count:
        errors.append(f'EXPECTED {expected_count}, OLT reports {len(onu_states)} ONU; check missing/offline DUT')
    if len(responsive)!=expected_count:
        errors.append(f'EXPECTED {expected_count}, IP scan found {len(responsive)} responsive; no DUT may be silently skipped')
    if not responsive:
        return [],{},errors+['No responsive DUT IP in fixed pool']
    rows,mapping,verify_errors=verify_mapping(responsive,onu_states,ping_fn=ping_fn,arp_fn=arp_fn)
    errors.extend(verify_errors)
    if len(mapping)!=expected_count:
        errors.append(f'EXPECTED {expected_count}, verified mapping {len(mapping)}; MAPPING INCOMPLETE')
    return rows,mapping,errors

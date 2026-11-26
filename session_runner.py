"""Durable single/loop ONU checks over one Serial session per healthy run.

Cycle journal is primary recovery record: a crash during XLSX replacement leaves
JSONL cycles intact, allowing rebuilding the workbook via `rebuild_excel`.
"""
from __future__ import annotations
import datetime as dt
import json
import time
from pathlib import Path
from onu_parser import parse_onu_state, parse_time_stamp, parse_optical, merge_state_data
from excel_record import export_cycles
from continuous_ping import ContinuousPing

COMMANDS = [('show onu state', 'onu_state'),
            ('show onu time-stamp', 'onu_time_stamp'),
            ('show onu optical-info all', 'onu_optical_info')]


def read_journal(folder):
    path = Path(folder)/'cycles.jsonl'
    cycles=[]
    if path.exists():
        with path.open(encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    entry=json.loads(line)
                    entry['onus']={int(k):v for k,v in entry['onus'].items()}
                    cycles.append(entry)
    return cycles


def append_journal(folder, cycle):
    path=Path(folder)/'cycles.jsonl'
    with path.open('a',encoding='utf-8') as f:
        f.write(json.dumps(cycle,ensure_ascii=False,default=str)+'\n')
        f.flush()
        import os
        os.fsync(f.fileno())


def rebuild_excel(folder):
    folder=Path(folder)
    return export_cycles(folder/'ONU_Master_Record.xlsx',read_journal(folder), mapping=read_mapping(folder))


def read_mapping(folder):
    path=Path(folder)/'mapping.json'
    if not path.exists():return {}
    data=json.loads(path.read_text(encoding='utf-8'))
    return {int(k):v for k,v in data.items()}


def save_mapping(folder, mapping):
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
    (folder/'mapping.json').write_text(json.dumps(mapping,ensure_ascii=False,indent=2),encoding='utf-8')


def check_cycle(client, folder, number, logger):
    """Execute all 3 commands with per-cycle raw logs; do not hide CLI errors."""
    folder=Path(folder)
    raw=folder/'raw_cli'
    raw.mkdir(parents=True,exist_ok=True)
    logs={}
    errors=[]
    for command,stem in COMMANDS:
        try:
            result=client.command(command, timeout=45)
            logs[stem]=result
            (raw/f'Loop_{number:04d}_{stem}.log').write_text(result,encoding='utf-8')
        except Exception as exc:
            errors.append(f'{stem}: {type(exc).__name__}: {exc}')
            logger.exception('COMMAND_ERROR|CYCLE=%s|COMMAND=%s', number, command)
            # Serial session may be desynchronized: do not issue subsequent commands.
            break
    parsed={}
    for key,parser in [('onu_state',parse_onu_state),('onu_time_stamp',parse_time_stamp),
                       ('onu_optical_info',parse_optical)]:
        if key not in logs:
            parsed[key]={}
            continue
        try:
            parsed[key]=parser(logs[key])
        except ValueError as exc:
            # Empty optical/timestamp response may accompany an offline ONU;
            # record missing-data warning, while retaining explicit state.
            parsed[key]={}
            errors.append(f'{key} parse: {exc}')
            logger.warning('PARSE_WARNING|CYCLE=%s|%s',number,exc)
    # Fail-closed validation across all three independent CLI responses.
    # Some offline ONUs legitimately lack optical values; only demand complete
    # optical metrics for ONUs whose *state* is working.
    state=parsed.get('onu_state',{})
    stamp=parsed.get('onu_time_stamp',{})
    optical=parsed.get('onu_optical_info',{})
    if state:
        missing_stamp=set(state)-set(stamp)
        extra_stamp=set(stamp)-set(state)
        if missing_stamp or extra_stamp:
            errors.append(f'TIMESTAMP ONU ID mismatch: missing={sorted(missing_stamp)}, extra={sorted(extra_stamp)}')
        extra_optical=set(optical)-set(state)
        if extra_optical:
            errors.append(f'OPTICAL unexpected ONU ID: {sorted(extra_optical)}')
        for onu_id, unit in sorted(state.items()):
            if unit.get('phase_state','').lower()!='working':
                continue
            values=optical.get(onu_id)
            if values is None:
                errors.append(f'OPTICAL missing working ONU ID {onu_id}')
                continue
            missing=[field for field in ('rx','tx','voltage','current','temperature')
                     if values.get(field) is None]
            if missing:
                errors.append(f'OPTICAL incomplete working ONU ID {onu_id}: {",".join(missing)}')
    units=merge_state_data(state,stamp,optical)
    if not parsed.get('onu_state'):
        errors.append('No valid ONU state available; cannot determine Online/Offline')
    return units, '; '.join(errors)


def cycle_result(units,error, roster, ping_results=None, mapping=None):
    if not units or not any(u.get('phase_state') for u in units.values()): return 'ERROR'
    if any(u.get('status')=='FAIL' for u in units.values()): return 'FAIL'
    if ping_results is not None and any(x.get('result')=='TIMEOUT' for x in ping_results.values()): return 'FAIL'
    if ping_results is not None and (len(ping_results)!=len(mapping or {}) or any(x.get('result') in ('ERROR','INITIALIZING') for x in ping_results.values())): return 'INCOMPLETE'
    if mapping and (set(units)!=set(mapping) or any(i not in units or units[i].get('gpon_sn','').lower()!=data['gpon_sn'].lower() for i,data in mapping.items())):return 'INCOMPLETE'
    if error or any(i not in units for i in roster) or any(
        u.get('status')!='PASS' or u.get('data_flag')!='OK' for u in units.values()
    ): return 'INCOMPLETE'
    return 'PASS'


def run_session(client_factory, folder, logger, stop_event, *, loop=False,
                interval_min=5.0, duration_hr=72.0, notify=None, clock=None,
                mapping=None, ping_fn=None, ping_interval=1.0):
    """One run -> one folder, one XLSX; errors journaled and retry next cycle.

    ``interval_min`` is measured between planned cycle starts; if checks are
    slow, the next starts immediately without overlapping.
    """
    if interval_min <= 0 or duration_hr < 0:
        raise ValueError('Interval must be > 0 and duration must be >= 0')
    folder=Path(folder)
    folder.mkdir(parents=True,exist_ok=True)
    notify=notify or (lambda *_: None)
    clock=clock or time
    start=clock.monotonic()
    next_start=start
    cutoff=(start+duration_hr*3600) if loop and duration_hr>0 else None
    client=None
    mapping=mapping or {}
    if mapping:
        save_mapping(folder,mapping)
    monitor=None
    if mapping:
        monitor=ContinuousPing(mapping,folder,stop_event,interval=ping_interval,ping_fn=ping_fn,
                               callback=lambda onu,row:notify('PING_UPDATE',(onu,row)))
        monitor.start()
    cycles=[]
    roster=set()
    last_phases={}
    last_pings={}
    status='COMPLETED'
    try:
        while True:
            if stop_event.is_set():status='STOPPED BY USER';break
            now=clock.monotonic()
            if cutoff is not None and now >= cutoff and cycles:break
            while now < next_start and not stop_event.is_set():
                stop_event.wait(min(0.25,next_start-now))
                now=clock.monotonic()
            if stop_event.is_set():status='STOPPED BY USER';break
            if cutoff is not None and clock.monotonic()>=cutoff and cycles:break
            number=len(cycles)+1
            local_now=dt.datetime.now().astimezone()
            check_time=local_now.strftime('%Y-%m-%d %H:%M:%S')
            time_zone=local_now.strftime('%z')
            time_zone=time_zone[:3]+':'+time_zone[3:]
            notify('CHECKING',f'Cycle {number} checking ONU...')
            units={};err='';ping_results={}
            # Continuous Ping runs independently throughout the session.
            # Never execute a second batch of four pings from the ONU cycle.
            try:
                if client is None:
                    client=client_factory()
                    client.open()
                    client._login_sequence()
                    logger.info('LOGIN_READY|CYCLE=%s',number)
                units,err=check_cycle(client,folder,number,logger)
                if err and 'onu_state:' in err:
                    client.close();client=None
            except Exception as exc:
                err=f'{type(exc).__name__}: {exc}'
                logger.exception('CYCLE_ERROR|%s|%s',number,err)
                if client is not None:
                    client.close();client=None
            if monitor:
                ping_results=monitor.cycle_snapshot()
            if stop_event.is_set():
                # Preserve the fully collected cycle even if Stop was pressed
                # during CLI/Ping processing. The next iteration will exit.
                status='STOPPED BY USER'
                logger.info('STOP_REQUESTED_DURING_CYCLE|%s|SAVE_COMPLETED_CYCLE',number)
            roster.update(units)
            result=cycle_result(units,err,roster,ping_results if mapping else None,mapping)
            cycle={'cycle':number,'time':check_time,'time_zone':time_zone,'onus':units,'error':err,'result':result,
                   'ping':ping_results}
            # Journal is written before the spreadsheet to prevent data loss.
            append_journal(folder,cycle)
            cycles.append(cycle)
            excel_saved=False
            try:
                rebuild_excel(folder)
                excel_saved=True
                logger.info('EXCEL_SAVED|CYCLE=%s|RESULT=%s|ONU=%s',number,result,len(units))
            except Exception as exc:
                logger.exception('EXCEL_SAVE_FAILED|CYCLE=%s',number)
                notify('SAVE ERROR',f'Cycle {number} journal saved, Excel error: {exc}')
            events=[]
            for onu,item in sorted(units.items()):
                phase=item.get('phase_state')
                if phase is None:continue
                prior=last_phases.get(onu)
                if prior is not None and prior != phase:
                    event={'time':check_time,'cycle':number,'onu_id':onu,
                           'gpon_sn':item.get('gpon_sn',''), 'previous':prior,'current':phase}
                    events.append(event)
                last_phases[onu]=phase
            for onu_key, result_entry in sorted(ping_results.items(),key=lambda x:int(x[0])):
                onu=int(onu_key)
                current=result_entry.get('result','ERROR')
                previous=last_pings.get(onu)
                if (previous is None and current in ('FAIL','ERROR')) or (previous is not None and current!=previous):
                    events.append({'time':check_time,'cycle':number,'onu_id':onu,
                                   'gpon_sn':mapping.get(onu,{}).get('gpon_sn',''),
                                   'previous':previous or 'NOT OBSERVED','current':current,
                                   'kind':'PING'})
                last_pings[onu]=current
            if events:
                with (folder/'events.jsonl').open('a',encoding='utf-8') as ef:
                    for event in events:ef.write(json.dumps(event,ensure_ascii=False)+'\n')
            notify('CYCLE',f'Cycle {number} | {result} | {len(units)} ONU | '+('Excel updated' if excel_saved else 'Excel SAVE FAILED; JSONL retained'))
            if not loop:break
            next_start += interval_min*60
            if next_start < clock.monotonic():
                next_start=clock.monotonic()  # Overrun: no overlapping cycles
            if cutoff is not None and next_start>=cutoff:break
        # Complete Ping CSV / summary before reporting Session DONE to GUI.
        if monitor is not None:
            try:
                monitor.stop()
                logger.info('CONTINUOUS_PING_STOPPED')
                monitor=None
            except Exception as exc:
                logger.exception('CONTINUOUS_PING_STOP_FAILED')
                if status=='COMPLETED':status='PING SAVE ERROR'
        # A missing XLSX due to transient file lock may be recoverable after close.
        if cycles:
            try: rebuild_excel(folder)
            except Exception as exc:
                logger.exception('FINAL_EXCEL_SAVE_FAILED')
                if status=='COMPLETED':status='SAVE ERROR'
        elif status=='COMPLETED':status='NO DATA'
        summary={'status':status,'cycles':len(cycles),'folder':str(folder),
                 'last_result':cycles[-1]['result'] if cycles else None}
        (folder/'status.txt').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
        notify('DONE',summary)
        return summary
    finally:
        if client is not None:client.close()
        if monitor is not None:
            try:monitor.stop()
            except Exception:logger.exception('PING_MONITOR_STOP_ERROR')

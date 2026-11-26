"""Continuous per-DUT ping monitor. It never opens or modifies Excel.

Each sample is durably appended to CSV. One worker per IP runs independently;
one monitor thread is only the coordinator for lifecycle and snapshot access.
"""
from __future__ import annotations
import csv
import datetime as dt
import os
from pathlib import Path
import re
import subprocess
import sys
import threading
import time

FIELDS = ['Timestamp','UTC Offset','ONU ID','DUT IP','Result','RTT ms','Consecutive Loss','Max Consecutive Loss','Total Sent','Total Failed']


def ping_once(ip, timeout_ms=1000):
    """A single OS ICMP echo; unknown command errors stay ERROR, not packet loss."""
    if sys.platform == 'win32':
        args=['ping','-n','1','-w',str(timeout_ms),ip]
    else:
        args=['ping','-n','-c','1','-W',str(max(1, (timeout_ms+999)//1000)),ip]
    try:
        p=subprocess.run(args,capture_output=True,text=True,errors='replace',timeout=timeout_ms/1000+3,
                         creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        output=p.stdout+'\n'+p.stderr
        # Windows English/Chinese; use protocol reply indicators, not locale statistics lines.
        ttl_match=re.search(r'\bTTL\s*[=:]\s*\d+',output,re.I)
        if p.returncode==0 and (ttl_match or (sys.platform!='win32' and re.search(r'\b1\s+received\b',output,re.I))):
            m=re.search(r'(?:time|時間)\s*[=<]\s*(\d+(?:\.\d+)?)\s*ms',output,re.I)
            return True, float(m.group(1)) if m else None, ''
        if p.returncode in (0,1):
            return False,None,''
        return None,None, f'ping exited {p.returncode}: {output[-200:]}'
    except subprocess.TimeoutExpired:
        return False,None,''
    except Exception as exc:
        return None,None,str(exc)


class ContinuousPing:
    def __init__(self,mapping,folder,stop_event, *, interval=1.0,ping_fn=None,callback=None, clock=None):
        self.mapping={int(k):dict(v) for k,v in mapping.items()}
        self.folder=Path(folder)
        self.stop_event=stop_event
        self.interval=float(interval)
        if not 0.005 <= self.interval <= 3600:raise ValueError('Invalid ping interval')
        self.ping_fn=ping_fn or ping_once
        self.callback=callback or (lambda *_:None)
        self.clock=clock or time
        self.lock=threading.RLock()
        self.rows={i:dict(onu_id=i,ip=v['ip'],status='INITIALIZING',sent=0,success=0,failed=0,
                          consecutive=0,max_consecutive=0,rtt_ms=None,last_success='',last_failed='',error='')
                   for i,v in self.mapping.items()}
        self._local_stop=threading.Event()
        self._threads=[]
        self._started=False
        self._ping_file=None
        self._event_file=None
        self._csv=None
        self._event_csv=None

    def start(self):
        if self._started:raise RuntimeError('Monitor already started')
        self.folder.mkdir(parents=True,exist_ok=True)
        self._ping_file=(self.folder/'continuous_ping.csv').open('a',newline='',encoding='utf-8-sig')
        self._event_file=(self.folder/'continuous_ping_events.csv').open('a',newline='',encoding='utf-8-sig')
        self._csv=csv.writer(self._ping_file)
        self._event_csv=csv.writer(self._event_file)
        if self._ping_file.tell()==0:self._csv.writerow(FIELDS)
        if self._event_file.tell()==0:self._event_csv.writerow(['Start','Recovery','ONU ID','DUT IP','Consecutive Loss','Elapsed Seconds','Status'])
        self._ping_file.flush();self._event_file.flush()
        self._started=True
        for onu,entry in sorted(self.mapping.items()):
            t=threading.Thread(target=self._work,args=(onu,entry['ip']),daemon=True,name=f'ping-{onu}')
            self._threads.append(t);t.start()

    def _work(self,onu,ip):
        start_of_outage=None
        outage_monotonic=None
        next_start=self.clock.monotonic()
        while not self.stop_event.is_set() and not self._local_stop.is_set():
            current=self.clock.monotonic()
            if current<next_start:
                self._local_stop.wait(min(next_start-current,.25))
                continue
            timestamp=dt.datetime.now().astimezone()
            when=timestamp.isoformat(timespec='seconds')
            try:
                ok,rtt,error=self.ping_fn(ip)
            except Exception as exc:
                ok,rtt,error=None,None,str(exc)
            with self.lock:
                row=self.rows[onu]
                old=row['consecutive']
                if ok is True:
                    row['status']='ONLINE';row['success']+=1;row['sent']+=1
                    row['consecutive']=0;row['rtt_ms']=rtt;row['last_success']=when
                    if old:
                        self._event_csv.writerow([start_of_outage,when,onu,ip,old,
                                                  round(self.clock.monotonic()-outage_monotonic,3),'RECOVERED'])
                        self._event_file.flush()
                        start_of_outage=None;outage_monotonic=None
                elif ok is False:
                    row['status']='TIMEOUT';row['failed']+=1;row['sent']+=1;row['rtt_ms']=None
                    row['consecutive']+=1;row['max_consecutive']=max(row['max_consecutive'],row['consecutive'])
                    row['last_failed']=when
                    if not old:
                        start_of_outage=when;outage_monotonic=self.clock.monotonic()
                else:
                    # Tool error must be visible, but should not masquerade as an ICMP timeout.
                    row['status']='ERROR';row['error']=error;row['rtt_ms']=None
                self._csv.writerow([when,timestamp.strftime('%z'),onu,ip,row['status'],
                                   '' if rtt is None else rtt,row['consecutive'],row['max_consecutive'],
                                   row['sent'],row['failed']])
                self._ping_file.flush()
                try:self.callback(onu,dict(row))
                except Exception:pass
            next_start=max(next_start+self.interval,self.clock.monotonic())
        if start_of_outage is not None:
            with self.lock:
                self._event_csv.writerow([start_of_outage,'',onu,ip,self.rows[onu]['consecutive'],
                                          round(self.clock.monotonic()-outage_monotonic,3),'OPEN_AT_STOP'])
                self._event_file.flush()

    def snapshot(self):
        with self.lock:return {i:dict(row) for i,row in self.rows.items()}

    def cycle_snapshot(self):
        """Compatibility with existing two Ping columns: cumulative values, no additional Ping probes."""
        result={}
        for onu,row in self.snapshot().items():
            result[str(onu)]={'result':row['status'],'loss':row['failed'],
                              'sent':row['sent'],'received':row['success'],
                              'max_consecutive':row['max_consecutive'],'error':row['error']}
        return result

    def stop(self):
        self._local_stop.set()
        for thread in self._threads:thread.join(timeout=5)
        if any(t.is_alive() for t in self._threads):
            raise RuntimeError('Ping worker still running; refusing to close CSV')
        with self.lock:
            if self._ping_file and not self._ping_file.closed:
                self._ping_file.flush();os.fsync(self._ping_file.fileno());self._ping_file.close()
            if self._event_file and not self._event_file.closed:
                self._event_file.flush();os.fsync(self._event_file.fileno());self._event_file.close()
            with (self.folder/'continuous_ping_summary.csv').open('w',newline='',encoding='utf-8-sig') as f:
                writer=csv.writer(f)
                writer.writerow(['ONU ID','DUT IP','Latest Status','Sent','Success','Failed','Loss %','Max Consecutive Loss','Last Success','Last Failed'])
                for onu,r in sorted(self.rows.items()):
                    writer.writerow([onu,r['ip'],r['status'],r['sent'],r['success'],r['failed'],
                                     round(r['failed']/r['sent']*100,5) if r['sent'] else '',
                                     r['max_consecutive'],r['last_success'],r['last_failed']])

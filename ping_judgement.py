"""Run-in Continuous Ping acceptance rules (one independent state per DUT).

At 8/16/24/... elapsed hours, cumulative packet loss must not exceed
50/100/150/... . A 6th consecutive loss causes immediate latched FAIL.
All clock inputs are elapsed monotonic seconds, never wall-clock timestamps.
"""

WINDOW_SECONDS = 8 * 3600
LOSS_PER_WINDOW = 50
MAX_ALLOWED_CONSECUTIVE = 5


def initial_fields():
    return dict(test_result='MONITORING', fail_reason='', fail_time='',
                checkpoints_completed=0, allowed_loss=0,
                checkpoint_time='', checkpoint_failed=0)


def on_sample(row, when):
    """Update the irreversible consecutive-loss failure decision after a sample."""
    if row['max_consecutive'] >= MAX_ALLOWED_CONSECUTIVE + 1:
        if row['test_result'] != 'FAIL':
            row['test_result'] = 'FAIL'
            row['fail_reason'] = 'MAX_CONSECUTIVE_LOSS_EXCEEDED'
            row['fail_time'] = when
            return 'MAX_CONSECUTIVE_LOSS_EXCEEDED'
    return None


def on_elapsed(row, elapsed_seconds, when):
    """Check every crossed 8-hour boundary using totals from samples before it.

    Call before counting a new sample, so a ping completing just after the
    boundary belongs to the next interval, not the completed checkpoint.
    Returns a list of checkpoint event dicts (including checkpoints that PASS).
    """
    completed = int(max(0.0, elapsed_seconds) // WINDOW_SECONDS)
    events=[]
    while row['checkpoints_completed'] < completed:
        index=row['checkpoints_completed']+1
        allowed=index*LOSS_PER_WINDOW
        failed=row['failed']
        passed=failed<=allowed
        row['checkpoints_completed']=index
        row['allowed_loss']=allowed
        row['checkpoint_time']=when
        row['checkpoint_failed']=failed
        if not passed and row['test_result']!='FAIL':
            row['test_result']='FAIL'
            row['fail_reason']='CUMULATIVE_LOSS_LIMIT_EXCEEDED'
            row['fail_time']=when
        elif passed and row['test_result']=='MONITORING':
            row['test_result']='PASS'
        events.append(dict(checkpoint_hours=index*8, failed=failed,
                           allowed=allowed, checkpoint_result='PASS' if passed else 'FAIL',
                           session_result=row['test_result'], timestamp=when))
    return events


def on_completed(row, when, *, completed):
    """Finalize a session only when its planned test ran to completion.

    A scheduled test shorter than the first 8h checkpoint can be assessed
    against the immediate consecutive-loss rule, but does *not* certify the
    8-hour cumulative-loss criterion. Manual Stop keeps MONITORING.
    Latched FAIL remains FAIL permanently.
    """
    if row['test_result'] == 'FAIL':
        return 'FAIL_LATCHED'
    if not completed:
        return 'STOPPED_BEFORE_COMPLETION'
    if row.get('status') == 'ERROR' or row.get('sent', 0) == 0:
        return 'NO_VALID_PING_DATA'
    if row['test_result'] == 'MONITORING':
        row['test_result'] = 'PASS'
        return 'SHORT_RUN_UNDER_8H'
    return 'CHECKPOINT_PASS'

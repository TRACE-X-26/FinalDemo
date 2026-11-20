"""Read-only comparison of saved STM32 motor runs with the archived reference."""
from statistics import median

from .collector import validate_measurements
from .motor_health import MAX_GAP_MS, MIN_SAMPLES, WINDOW_END_MS, WINDOW_START_MS

REFERENCE = {
    'id': 't08-observed-v1',
    'motor_model': 'JGA25-371',
    'run_ids': ['T08-01', 'T08-02'],
    'pwm_percent': 50,
    'rpm_verified': False,
    'archive_sample_count': 60,
    'ranges': {'rpm': [77, 80], 'current': [0.044, 0.311], 'voltage': [12.200, 12.284]},
}
METRICS = {'rpm': 'Output speed', 'current': 'Motor current', 'voltage': 'Supply voltage'}


def motor_test_summary(number, run):
    config = run.get('configuration', {})
    return {
        'id': run['id'], 'number': number, 'state': run['state'],
        'created_at': run['created_at'], 'duration_ms': config.get('duration_ms'),
        'pwm_percent': run.get('commissioning', {}).get('fixed_pwm_percent'),
        'load_id': config.get('load_id'), 'direction': 'Forward',
    }


def _window_samples(run, step):
    captures = {name: {} for name in METRICS}
    started = step['started_ms']
    for saved in run['samples']:
        raw = saved['raw']
        if (raw.get('motor_state') != 'RUNNING' or raw.get('applied_pwm_percent') != REFERENCE['pwm_percent']
                or raw.get('test_id') != step['test_id']
                or (step.get('device_session_id') is not None
                    and raw.get('device_session_id') != step['device_session_id'])):
            continue
        try:
            channels = validate_measurements(raw)
        except ValueError:
            continue
        status_tick = raw.get('stm32_status_timestamp_ms')
        if type(status_tick) is not int:
            continue
        for name in METRICS:
            reading = channels[name]
            tick = reading['timestamp_ms']
            elapsed = (tick - started) & 0xffffffff
            age = (status_tick - tick) & 0xffffffff
            if (not reading['valid'] or age > 1500
                    or not WINDOW_START_MS <= elapsed <= WINDOW_END_MS):
                continue
            captures[name][elapsed] = (reading['value'], raw.get('encoder_calibrated') is True)
    return captures


def _adequate(captures):
    ticks = [WINDOW_START_MS, *sorted(captures), WINDOW_END_MS]
    return len(captures) >= MIN_SAMPLES and all(b - a <= MAX_GAP_MS for a, b in zip(ticks, ticks[1:]))


def compare_motor_test(number, run):
    summary = motor_test_summary(number, run)
    metrics = {name: {'value': None, 'range': bounds, 'sample_count': 0, 'outside': None}
               for name, bounds in REFERENCE['ranges'].items()}
    result = {'run_id': run['id'], 'number': number, 'reference': REFERENCE,
              'metrics': metrics, 'status': 'Not assessed', 'findings': [], 'rpm_calibrated': None,
              'window_ms': [WINDOW_START_MS, WINDOW_END_MS]}
    step = next((s for s in run.get('steps', []) if s.get('test_id') == 'pwm_50'
                 and type(s.get('started_ms')) is int), None)
    reasons = result['findings']
    if run['state'] != 'COMPLETED':
        reasons.append('Motor test did not complete.')
    model = (run.get('commissioning') or {}).get('motor', {}).get('model')
    if model and model != REFERENCE['motor_model']:
        reasons.append('The saved motor model differs from the archived reference.')
    if step is None:
        reasons.append('No confirmed 50% PWM run matches the archived reference.')
    duration = summary['duration_ms']
    if type(duration) is not int or duration < WINDOW_END_MS:
        reasons.append('Run is too short for the 3–13 second steady-state window.')
    if step is None:
        return result

    captures = _window_samples(run, step)
    for name, readings in captures.items():
        metric = metrics[name]
        metric['sample_count'] = len(readings)
        if readings:
            metric['value'] = median(value for value, _ in readings.values())
        if type(duration) is int and duration >= WINDOW_END_MS and not _adequate(readings):
            reasons.append(f'Insufficient fresh {METRICS[name].lower()} readings in the steady-state window.')
    if captures['rpm']:
        result['rpm_calibrated'] = all(calibrated for _, calibrated in captures['rpm'].values())
    if reasons:
        return result

    rpm_comparable = result['rpm_calibrated'] and REFERENCE['rpm_verified']
    for name, metric in metrics.items():
        if name == 'rpm' and not rpm_comparable:
            continue
        low, high = metric['range']
        metric['outside'] = not low <= metric['value'] <= high

    speed, current, voltage = (metrics[name] for name in ('rpm', 'current', 'voltage'))
    if voltage['value'] < voltage['range'][0]:
        reasons.append('Possible supply voltage sag')
    elif voltage['outside']:
        reasons.append('Supply voltage above the archived range')
    if result['rpm_calibrated'] and sum(value < 0 for value, _ in captures['rpm'].values()) > len(captures['rpm']) / 2:
        reasons.append('Unexpected encoder direction')
    elif not rpm_comparable and not speed['range'][0] <= speed['value'] <= speed['range'][1]:
        reasons.append('RPM outside the archived range. Verify encoder scaling before inferring a motor fault.')
    if current['outside']:
        level = 'above' if current['value'] > current['range'][1] else 'below'
        reasons.append(f'Motor current {level} the archived range')

    # The archive's RPM scale is unverified. Avoid mapping unlike scales to a
    # mechanical fault. A calibrated zero-speed reading plus excess current
    # can independently support a possible stall finding.
    if result['rpm_calibrated'] and sum(abs(value) <= 1 for value, _ in captures['rpm'].values()) >= 3:
        if current['value'] > current['range'][1]:
            reasons.append('Possible stall: repeated near-zero speed with elevated current')
    calibrated_motion_warning = result['rpm_calibrated'] and any(
        finding.startswith(('Unexpected encoder direction', 'Possible stall')) for finding in reasons)
    result['status'] = ('Deviation detected' if calibrated_motion_warning or any(metric['outside'] for metric in metrics.values())
                        else 'Within reference')
    return result

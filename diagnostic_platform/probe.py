"""Independent ADC probe telemetry; never substitutes INA219 supply voltage."""
import math

STATUSES = {'OK','ADC_NOT_INITIALIZED','ADC_TIMEOUT','ADC_READ_ERROR','OUT_OF_RANGE','STALE'}


def normalize_probe(result, device_tick=None):
    out = dict(voltage=None, raw_adc=None, adc_pin_voltage=None, unit='V', valid=False,
               status='NOT_REPORTED', calibrated=False, timestamp_ms=None, sequence=None)
    probe = result.get('circuit_probe')
    if probe is None:
        return out
    if not isinstance(probe, dict):
        return {**out, 'status':'INVALID_DATA'}
    status = probe.get('status')
    timestamp = probe.get('timestamp_ms')
    raw = probe.get('raw_adc')
    value = probe.get('voltage')
    pin = probe.get('adc_pin_voltage')
    sequence = probe.get('sequence')
    finite = lambda v: type(v) in (float, int) and math.isfinite(v)
    if (status not in STATUSES or type(probe.get('valid')) is not bool or probe.get('unit')!='V'
            or type(timestamp) is not int or not 0<=timestamp<=0xffffffff
            or type(sequence) is not int or not 0<=sequence<=0xffffffff
            or type(probe.get('calibrated')) is not bool
            or (raw is not None and (type(raw) is not int or not 0<=raw<=4095))
            or (pin is not None and (not finite(pin) or not 0<=pin<=3.6))):
        return {**out, 'status':'INVALID_DATA'}
    out.update(status=status, timestamp_ms=timestamp, sequence=sequence, raw_adc=raw,
               adc_pin_voltage=pin, calibrated=probe['calibrated'])
    if probe['valid']:
        if status!='OK' or raw is None or raw>=4080 or pin is None or not finite(value) or not 0<=value<=12.01:
            return {**out, 'status':'INVALID_DATA'}
        out.update(valid=True, voltage=value)
    if type(device_tick) is int:
        age=(device_tick-timestamp)&0xffffffff
        out['acquisition_age_ms']=age
        if age>500 and out['valid']:
            out.update(status='STALE',valid=False,voltage=None)
    return out

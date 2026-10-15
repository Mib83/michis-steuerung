"""Pure, local-clock scheduling for the upper-element domestic water controller."""
import re
from .engine import finite

DEFAULT_ENTITIES = {
 'top_temperature':'sensor.heizraum_warmwasser_oben',
 'bottom_temperature':'sensor.heizraum_warmwasser_unten',
 'top_switch':'switch.heizraum_heizstab_4_kw',
 'top_feedback':'binary_sensor.heizraum_heizstab_4kw',
 'bottom_switch':'switch.heizraum_heizstab_75_kw',
 'bottom_feedback':'binary_sensor.heizraum_heizstab_75kw',
 'pump_switch':'switch.heizraum_pumpe_warmwasserzirkulation',
 'pump_feedback':'binary_sensor.heizraum_pumpe_wasserzirkulation',
}
WATER_DEFAULTS = {'target_top':None,'restart_top':None,'wait_off':None,
 'legionella_enabled':False,'legionella_target':None,'legionella_from':'',
 'legionella_until':'','legionella_pump':False,'legionella_days':[],
 'windows':[{'days':[],'on':'','off':''}]}


def validate_entities(data):
    if not isinstance(data, dict) or set(data) != set(DEFAULT_ENTITIES):
        raise ValueError('Acht Brauchwasser-Entitäten erforderlich')
    result = {}
    for key, value in data.items():
        domain = 'sensor' if key.endswith('temperature') else 'switch' if key.endswith('switch') else 'binary_sensor'
        if not isinstance(value,str) or not re.fullmatch(domain+r'\.[a-z0-9_]+',value):
            raise ValueError('Entitäts-ID oder Entitätstyp ungültig')
        result[key] = value
    if len(set(result.values())) != 8:
        raise ValueError('Brauchwasser-Entitäten müssen eindeutig sein')
    return result


def minute(value):
    if not isinstance(value,str) or not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d',value):
        raise ValueError('Gültige Uhrzeit erforderlich')
    h,m = value.split(':')
    return int(h)*60+int(m)


def days(value):
    if not isinstance(value,list) or any(type(d) is not int or d not in range(7) for d in value) or len(value)!=len(set(value)):
        raise ValueError('Wochentage ungültig')
    return sorted(value)


def validate_water_settings(data):
    if not isinstance(data,dict) or set(data) != set(WATER_DEFAULTS):
        raise ValueError('Brauchwasser-Einstellungen unvollständig')
    result = dict(data)
    for key in ('target_top','restart_top','wait_off'):
        result[key] = finite(data[key])
    if not 0 <= result['restart_top'] < result['target_top'] <= 95:
        raise ValueError('Wiedereinschalttemperatur muss unter der Zieltemperatur liegen (0–95 °C)')
    if not 0 <= result['wait_off'] <= 86400:
        raise ValueError('Sperrzeit muss zwischen 0 und 86400 Sekunden liegen')
    for key in ('legionella_enabled','legionella_pump'):
        if not isinstance(data[key],bool):
            raise ValueError('Schalterwert ungültig')
    result['legionella_days'] = days(data['legionella_days'])
    if data['legionella_target'] is not None:
        result['legionella_target'] = finite(data['legionella_target'])
        if not 0 <= result['legionella_target'] <= 95:
            raise ValueError('Zieltemperatur muss zwischen 0 und 95 °C liegen')
    if data['legionella_enabled']:
        if result['legionella_target'] is not None and result['legionella_target'] < result['target_top']:
            raise ValueError('Legionellen-Zieltemperatur muss mindestens der normalen Zieltemperatur entsprechen')
        if result['legionella_target'] is None or not result['legionella_days']:
            raise ValueError('Zieltemperatur und Wochentage für das Legionellenprogramm erforderlich')
        if minute(data['legionella_from']) == minute(data['legionella_until']):
            raise ValueError('Beginn und Ende des Legionellenprogramms müssen verschieden sein')
    else:
        for key in ('legionella_from','legionella_until'):
            if data[key]:minute(data[key])
    if not isinstance(data['windows'],list) or not 1 <= len(data['windows']) <= 50:
        raise ValueError('Ein bis 50 Zirkulations-Zeitfenster erforderlich')
    result['windows'] = []
    for window in data['windows']:
        if not isinstance(window,dict) or set(window) != {'days','on','off'}:
            raise ValueError('Zirkulations-Zeitfenster ungültig')
        selected = days(window['days'])
        if selected:
            if minute(window['on']) == minute(window['off']):
                raise ValueError('Ein- und Ausschaltzeit müssen verschieden sein')
        else:
            for key in ('on','off'):
                if window[key]:minute(window[key])
        result['windows'].append({'days':selected,'on':window['on'],'off':window['off']})
    return result


def active_window(selected, start, end, now):
    if not selected or not start or not end:
        return False
    current = now.hour*60+now.minute
    start,end = minute(start),minute(end)
    if start < end:
        return now.weekday() in selected and start <= current < end
    # Overnight periods belong to the selected starting day.
    return (now.weekday() in selected and current >= start) or ((now.weekday()-1)%7 in selected and current < end)


def water_demand(settings, temperature, heater_on, blocked, now):
    legionella = settings['legionella_enabled'] and active_window(settings['legionella_days'],settings['legionella_from'],settings['legionella_until'],now)
    target = settings['legionella_target'] if legionella else settings['target_top']
    difference = settings['target_top']-settings['restart_top']
    restart = target-difference if legionella else settings['restart_top']
    heat = not blocked and (temperature < target if heater_on else temperature <= restart)
    pump = any(active_window(w['days'],w['on'],w['off'],now) for w in settings['windows'])
    pump = pump or (legionella and settings['legionella_pump'])
    return {'heat':bool(heat),'pump':bool(pump),'legionella':bool(legionella),'target':target,'restart':restart}

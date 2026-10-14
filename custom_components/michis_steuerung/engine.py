"""Pure control logic; never substitutes missing temperatures with zero."""
import math
from .const import DEFAULTS

def finite(value):
    if isinstance(value, bool):
        raise ValueError('Zahl erforderlich')
    value = float(value)
    if not math.isfinite(value):
        raise ValueError('Endliche Zahl erforderlich')
    return value

def validate_settings(data):
    base = {'lower', 'upper', 'step', 'pause', 'stale'}
    full = base | {'fast_enabled', 'fast_threshold', 'fast_step', 'fast_immediate'}
    if not isinstance(data, dict) or set(data) not in (base, full):
        raise ValueError('Regler-Einstellungen unvollständig')
    legacy = set(data) == base
    merged = {**DEFAULTS, **data}
    for key in ('fast_enabled', 'fast_immediate'):
        if not isinstance(merged[key], bool):
            raise ValueError('Schnellreaktions-Schalter müssen an oder aus sein')
    result = {key: merged[key] if key in ('fast_enabled', 'fast_immediate') else finite(merged[key]) for key in full}
    if not 0 <= result['lower'] < result['upper'] <= 100:
        raise ValueError('Untergrenze muss kleiner als Obergrenze sein (0–100 °C)')
    if not 0.1 <= result['step'] <= 1 or abs(result['step'] * 10 - round(result['step'] * 10)) > 1e-8:
        raise ValueError('Schrittweite: 0,1–1 V in 0,1-V-Schritten')
    if not 2 <= result['pause'] <= 300:
        raise ValueError('Pause: 2–300 Sekunden')
    if not 10 <= result['stale'] <= 300:
        raise ValueError('Messwertgültigkeit: 10–300 Sekunden')
    if not 0.5 <= result['fast_threshold'] <= 10:
        raise ValueError('Temperatursprung: 0,5–10 °C')
    if legacy:
        result['fast_step'] = max(result['step'], result['fast_step'])
    if not result['step'] <= result['fast_step'] <= 3 or abs(result['fast_step'] * 10 - round(result['fast_step'] * 10)) > 1e-8:
        raise ValueError('Schnellschritt: normale Schrittweite bis 3 V in 0,1-V-Schritten')
    return result

def next_output(temperature, output, settings):
    temperature, output = finite(temperature), finite(output)
    if not 0 <= output <= 10:
        raise ValueError('Stellwert außerhalb 0–10 V')
    if temperature > settings['upper']:
        return round(min(10, output + settings['step']), 1)
    if temperature < settings['lower']:
        return round(max(0, output - settings['step']), 1)
    return output

def validate_sources(sources):
    if not isinstance(sources, list) or len(sources) != 4:
        raise ValueError('Genau vier Miner erforderlich')
    result, bases = [], set()
    for item in sources:
        if not isinstance(item, dict):
            raise ValueError('Miner-Konfiguration ungültig')
        name, base, labels = item.get('name'), item.get('base'), item.get('labels')
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 80:
            raise ValueError('Minername erforderlich (maximal 80 Zeichen)')
        if not isinstance(base, str):
            raise ValueError('MQTT-Basispfad erforderlich')
        base = base.strip().rstrip('/')
        if not base or len(base) > 500 or any(c in base for c in '+#\x00\r\n') or base in bases:
            raise ValueError('Vier eindeutige MQTT-Basispfade ohne Platzhalter erforderlich')
        if not isinstance(labels, list) or len(labels) != 4 or any(not isinstance(x, str) or not 1 <= len(x.strip()) <= 80 for x in labels):
            raise ValueError('Vier Temperaturnamen je Miner erforderlich (maximal 80 Zeichen)')
        bases.add(base)
        result.append({'name': name.strip(), 'base': base, 'labels': [x.strip() for x in labels]})
    return result

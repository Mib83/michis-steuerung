"""Independent, persistent fan controllers using DHT22 Modbus and Loxone UDP."""
import asyncio
import ipaddress
import time
from datetime import timedelta
from types import SimpleNamespace
from homeassistant.helpers.storage import Store
from .const import DOMAIN
from .history import chart_history
from homeassistant.helpers.event import async_track_time_interval
from . import Controller
from .const import DEFAULTS
from .engine import finite, validate_settings
from .modbus import read_climate

FAN_DEFAULTS = {**DEFAULTS, 'lower': 27.0, 'upper': 28.0, 'pause': 120.0}


def validate_config(data):
    if not isinstance(data, dict):
        raise ValueError('Lüfter-Konfiguration fehlt')
    name = data.get('name', '').strip()
    if not 1 <= len(name) <= 80:
        raise ValueError('Name erforderlich (maximal 80 Zeichen)')
    result = {'name': name}
    for key in ('sensor_host', 'host'):
        try:
            ip = ipaddress.ip_address(data[key].strip())
            if ip.version != 4:
                raise ValueError()
            result[key] = str(ip)
        except (ValueError, KeyError, AttributeError):
            raise ValueError('Gültige IPv4-Adressen für ESP32 und Loxone erforderlich') from None
    for key, low, high in [('sensor_port', 1, 65535), ('port', 1, 65535), ('unit', 0, 255)]:
        n = finite(data.get(key))
        if not low <= n <= high or n != int(n):
            raise ValueError('Port oder Modbus-Geräteadresse ungültig')
        result[key] = int(n)
    command = data.get('command', '')
    if not isinstance(command, str) or not 1 <= len(command.strip()) <= 100 or any(c in command for c in '\x00\r\n'):
        raise ValueError('UDP-Befehlsname erforderlich (maximal 100 Zeichen)')
    result['command'] = command.strip()
    for key in ('minimum', 'maximum'):
        n = finite(data.get(key))
        if not 0 <= n <= 10 or abs(n * 10 - round(n * 10)) > 1e-8:
            raise ValueError('Spannungsgrenzen: 0–10 V in 0,1-V-Schritten')
        result[key] = n
    if result['minimum'] >= result['maximum']:
        raise ValueError('Mindestspannung muss kleiner als Höchstspannung sein')
    if data.get('off_mode') not in ('hold', 'minimum', 'zero'):
        raise ValueError('Verhalten bei Automatik aus ungültig')
    result['off_mode'] = data['off_mode']
    return result


class FanController(Controller):
    def __init__(self, parent, fan_id, config, saved=None):
        self.parent, self.fan_id = parent, fan_id
        self.config = validate_config(config)
        entry = SimpleNamespace(entry_id=parent.entry.entry_id + '.' + fan_id,
            data={**self.config, 'miners': [], 'prefix': ''})
        super().__init__(parent.hass, entry)
        self.settings = dict(FAN_DEFAULTS)
        self.output = self.config['minimum']
        self.config_entry = None
        self.fan_store = Store(self.hass, 1, f'{DOMAIN}.fan.{fan_id}')
        self.measurement = None
        self.sensor_error = None
        self.stopping = False
        if saved:
            self.settings = validate_settings(saved['settings'])
            self.output = self.clamp(finite(saved['output']))
            previous = saved.get('last_sent_output')
            if previous is not None and 0 <= finite(previous) <= 10:
                self.last_sent_output = finite(previous)

    def output_limits(self):
        return self.config['minimum'], self.config['maximum']

    def clamp(self, value):
        return round(max(self.config['minimum'], min(self.config['maximum'], value)), 1)

    def serialized(self):
        return {'id': self.fan_id, 'config': self.config, 'settings': self.settings,
            'output': self.output, 'last_sent_output': self.last_sent_output}

    async def save(self):
        await self.fan_store.async_save(self.serialized())
        if self.config_entry and self.config_entry.title != self.config['name']:
            self.hass.config_entries.async_update_entry(self.config_entry, title=self.config['name'])

    async def start(self):
        self.enabled = False
        self.unsubscribers.append(async_track_time_interval(self.hass, self.poll, timedelta(seconds=5)))
        self.unsubscribers.append(async_track_time_interval(self.hass, self.tick, timedelta(seconds=1)))
        # Initial polling does not send or enable the fan.
        self.hass.async_create_task(self.poll(None))

    async def poll(self, _now):
        async with self.lock:
            if self.stopping:
                return
            try:
                temperature, humidity = await read_climate(self.config['sensor_host'],
                    self.config['sensor_port'], self.config['unit'])
            except (OSError, ValueError, asyncio.TimeoutError, asyncio.IncompleteReadError) as err:
                self.measurement = None
                self.sensor_error = str(err) or 'ESP32 nicht erreichbar'
                self.reset_jump_detection()
            else:
                self.measurement = (temperature, humidity, time.monotonic())
                self.sensor_error = None

    def temperature_revision(self):
        return self.measurement[2] if self.measurement else None

    def snapshot(self, history_seconds=3600):
        now = time.monotonic()
        ready = self.measurement is not None and now - self.measurement[2] <= self.settings['stale']
        temperature = self.measurement[0] if ready else None
        remaining = max(0, self.settings['pause']-(now-self.last_sent)) if self.last_sent is not None else 0
        if self.last_error:
            status = 'UDP-Sendefehler · Automatik aus'
        elif not ready:
            status = 'Temperatur fehlt · Stellwert wird gehalten'
        elif not self.enabled:
            status = 'Manuell · Automatik aus'
        elif remaining > 0:
            status = 'Wartezeit nach Stellwertänderung'
        elif temperature > self.settings['upper']:
            status = 'Lüfter erhöhen' if self.output < self.config['maximum'] else 'Höchstspannung erreicht'
        elif temperature < self.settings['lower']:
            status = 'Lüfter reduzieren' if self.output > self.config['minimum'] else 'Mindestspannung erreicht'
        else:
            status = 'Temperatur im gewünschten Bereich'
        return {'id': self.fan_id, 'config': dict(self.config), 'settings': dict(self.settings),
            'maximum': temperature, 'humidity': self.measurement[1] if ready else None,
            'ready': ready, 'output': self.output, 'sent_output': self.last_sent_output,
            'enabled': self.enabled, 'remaining': round(remaining, 1), 'status': status,
            'sensor_error': self.sensor_error, 'last_message': self.last_message,
            'history': chart_history(self.history, history_seconds), 'fast_pending': self.pending_jump is not None,
            'last_fast_event': self.last_fast_event}

    async def send(self, value):
        # Manual 0 V is possible only through the explicit off setting.
        if finite(value) != 0 or self.config['off_mode'] != 'zero':
            value = self.clamp(finite(value))
        await super().send(value)

    async def command(self, action, value):
        if action in ('config', 'configure'):
            async with self.lock:
                config = validate_config(value['config'] if action == 'configure' else value)
                settings = validate_settings(value['settings']) if action == 'configure' else self.settings
                if self.enabled and config != self.config:
                    raise ValueError('Vor dem Ändern der Verbindung die Automatik ausschalten')
                self.parent.validate_fan_target(config, self.fan_id)
                sensor_changed = any(config[k] != self.config[k] for k in ('sensor_host', 'sensor_port', 'unit'))
                self.config = config
                self.settings = settings
                self.entry.data.update(config)
                self.output = self.clamp(self.output)
                if sensor_changed:
                    self.measurement = None
                    self.history.clear()
                self.reset_jump_detection()
                await self.save()
            return self.snapshot()
        if action == 'enable' and value is False:
            async with self.lock:
                self.enabled = False
                self.reset_jump_detection()
                target = {'minimum': self.config['minimum'], 'zero': 0}.get(self.config['off_mode'])
                if target is not None and self.last_sent_output != target:
                    await self.send(target)
            return self.snapshot()
        if action == 'enable' and value is True:
            self.output = self.clamp(self.output)
        if action == 'manual':
            value = finite(value)
            if not self.config['minimum'] <= value <= self.config['maximum']:
                raise ValueError('Manueller Stellwert muss innerhalb der Spannungsgrenzen liegen')
        return await super().command(action, value)

    async def stop(self):
        self.stopping = True
        await super().stop()

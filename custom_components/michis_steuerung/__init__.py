"""MQTT-fed controller and authenticated custom UI for HA 2026.10."""
import asyncio
from homeassistant.config_entries import ConfigEntryDisabler
from collections import deque
from datetime import timedelta
from pathlib import Path
import socket
import time
import uuid

import probatio as vol
from homeassistant.components import mqtt, panel_custom, frontend, websocket_api
from homeassistant.components.http import StaticPathConfig
from homeassistant.core import callback
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.storage import Store
from .const import DEFAULTS, DOMAIN, NAME, VERSION, UI_BUILD, LEGACY_DOMAIN, CONTROLLER_NAME
from .history import chart_history, PERIODS
from .engine import finite, next_output, validate_settings, validate_sources

class Controller:
    def __init__(self, hass, entry):
        self.hass, self.entry = hass, entry
        self.settings = dict(DEFAULTS)
        self.output = 4.0
        self.enabled = False
        self.samples = {}
        self.history = deque(maxlen=17281)
        self.last_sent = None
        self.last_message = None
        self.last_sent_output = None
        self.last_error = None
        self.last_history = 0
        self.previous_temperature = None
        self.previous_revision = None
        self.pending_jump = None
        self.last_fast = None
        self.last_fast_event = None
        self.lock = asyncio.Lock()
        self.store = Store(hass, 1, f'{DOMAIN}.{entry.entry_id}')
        self.unsubscribers = []
        self.mqtt_unsubscribers = []
        self.fans = {}
        self.waters = {}
        self.legacy_fans = []
        self.sources = [{'name': miner.upper().replace('_', '-'),
            'base': f"{entry.data['prefix']}/{miner}",
            'labels': [f'Slot {i}' for i in range(4)]}
            for miner in entry.data['miners']]

    async def start(self):
        saved = await self.store.async_load()
        if saved is None and self.entry.data.get('legacy_entry_id'):
            legacy_store = Store(self.hass, 1, f"{LEGACY_DOMAIN}.{self.entry.data['legacy_entry_id']}")
            saved = await legacy_store.async_load()
        if saved:
            try:
                self.settings = validate_settings(saved['settings'])
                output = finite(saved['output'])
                if 0 <= output <= 10:
                    self.output = output
                previous_sent = saved.get('last_sent_output')
                if previous_sent is not None and 0 <= finite(previous_sent) <= 10:
                    self.last_sent_output = finite(previous_sent)
            except (ValueError, KeyError, TypeError):
                pass
        if saved and 'sources' in saved:
            try:
                self.sources = validate_sources(saved['sources'])
            except (ValueError, TypeError):
                pass
        self.legacy_fans = (saved or {}).get('fans', [])
        # Every startup deliberately requires manual enable; no startup UDP output.
        self.enabled = False
        await self.subscribe_sources(self.sources)
        self.unsubscribers.append(async_track_time_interval(self.hass, self.tick, timedelta(seconds=1)))
        async def shutdown(_event):
            await self.stop()
        self.unsubscribers.append(self.hass.bus.async_listen_once('homeassistant_stop', shutdown))

    async def subscribe_sources(self, sources):
        new_unsubscribers = []
        try:
            for source in sources:
                for key in ('ths', 'sm0', 'sm1', 'sm2', 'sm3'):
                    topic = f"{source['base']}/{key}/state"
                    @callback
                    def receive(message, topic=topic, key=key):
                        if message.retain:
                            return
                        try:
                            value = finite(message.payload)
                        except (ValueError, TypeError):
                            self.samples.pop(topic, None)
                            return
                        if value < 0 or (key != 'ths' and value > 200):
                            self.samples.pop(topic, None)
                            return
                        self.samples[topic] = (value, time.monotonic())
                    new_unsubscribers.append(await mqtt.async_subscribe(self.hass, topic, receive, 1))
        except Exception:
            for unsubscribe in new_unsubscribers:
                unsubscribe()
            raise
        for unsubscribe in self.mqtt_unsubscribers:
            unsubscribe()
        self.mqtt_unsubscribers = new_unsubscribers
        self.samples.clear()
        self.reset_jump_detection()

    def snapshot(self, history_periods=None):
        now = time.monotonic()
        miners, valid = [], []
        for source in self.sources:
            temps = []
            for key in ('sm0', 'sm1', 'sm2', 'sm3', 'ths'):
                sample = self.samples.get(f"{source['base']}/{key}/state")
                value = sample[0] if sample and now-sample[1] <= self.settings['stale'] else None
                if key == 'ths':
                    ths = value
                else:
                    temps.append(value)
                    if value is not None:
                        valid.append(value)
            miners.append({'name': source['name'], 'labels': source['labels'], 'temperatures': temps, 'ths': ths})
        ready = len(valid) == 16
        maximum = max(valid) if valid else None
        remaining = max(0, self.settings['pause'] - (now-self.last_sent)) if self.last_sent is not None else 0
        if self.last_error:
            status = 'UDP-Sendefehler · Automatik aus'
        elif not ready:
            status = 'Messwerte fehlen · Stellwert wird gehalten'
        elif not self.enabled:
            status = 'Manuell · Automatik aus'
        elif remaining > 0:
            status = 'Wartezeit nach Stellwertänderung'
        elif maximum > self.settings['upper']:
            status = 'Mehr Kühlung erforderlich' if self.output < 10 else 'Obergrenze 10 V erreicht'
        elif maximum < self.settings['lower']:
            status = 'Kühlung reduzieren' if self.output > 0 else 'Untergrenze 0 V erreicht'
        else:
            status = 'Temperatur im gewünschten Bereich'
        return {'waters': [water.snapshot() for water in self.waters.values()], 'fans': [fan.snapshot((history_periods or {}).get(fan.fan_id, 3600)) for fan in self.fans.values()], 'fast_pending': self.pending_jump is not None, 'last_fast_event': self.last_fast_event, 'sources': self.sources, 'settings': self.settings, 'output': self.output, 'enabled': self.enabled,
            'miners': miners, 'maximum': maximum, 'ready': ready, 'valid_count': len(valid),
            'remaining': round(remaining,1), 'status': status,
            'last_message': self.last_message, 'sent_output': self.last_sent_output, 'last_error': self.last_error,
            'history': chart_history(self.history, (history_periods or {}).get('miner', 3600)), 'target': f"{self.entry.data['host']}:{self.entry.data['port']}", 'version': VERSION}

    async def save(self):
        await self.store.async_save({'settings': self.settings, 'output': self.output, 'last_sent_output': self.last_sent_output, 'sources': self.sources, 'fans': self.legacy_fans})

    def output_limits(self):
        return 0, 10

    def validate_fan_target(self, config, fan_id=None):
        target = (config['host'], config['port'], config['command'])
        if target == (self.entry.data['host'], self.entry.data['port'], self.entry.data['command']):
            raise ValueError('Lüfter benötigt einen eigenen UDP-Befehlsnamen')
        for other_id, fan in self.fans.items():
            if other_id != fan_id and target == (fan.config['host'], fan.config['port'], fan.config['command']):
                raise ValueError('Dieses UDP-Ziel mit Befehlsname wird bereits von einem Lüfter verwendet')

    async def fan_action(self, action, value):
        if action != 'fan_command':
            raise ValueError('Neue Geräte bitte unter Einstellungen → Geräte & Dienste hinzufügen')
        if not isinstance(value, dict) or value.get('id') not in self.fans:
            raise ValueError('Lüfter nicht gefunden')
        await self.fans[value['id']].command(value.get('action'), value.get('value'))
        return self.snapshot()

    async def send(self, value):
        value = finite(value)
        if not 0 <= value <= 10:
            raise ValueError('Stellwert muss zwischen 0 und 10 V liegen')
        message = f"{self.entry.data['command']}{value:.1f}"
        def transmit():
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                sock.sendto(message.encode('utf-8'), (self.entry.data['host'], self.entry.data['port']))
        try:
            await self.hass.async_add_executor_job(transmit)
        except OSError as err:
            self.last_error = str(err)
            self.enabled = False
            raise ValueError(f'UDP konnte nicht gesendet werden: {err}') from err
        self.output = round(value,1)
        self.last_message = message
        self.last_sent_output = self.output
        self.last_sent = time.monotonic()
        self.last_error = None
        await self.save()

    def temperature_revision(self):
        return tuple(self.samples.get(f"{source['base']}/sm{i}/state", (None, None))[1]
            for source in self.sources for i in range(4))

    def reset_jump_detection(self):
        self.previous_temperature = None
        self.previous_revision = None
        self.pending_jump = None

    def detect_jump(self, state):
        if not self.enabled or not state['ready']:
            self.reset_jump_detection()
            return
        revision = self.temperature_revision()
        if revision == self.previous_revision:
            return
        current = state['maximum']
        if (self.settings['fast_enabled'] and self.previous_temperature is not None
            and current - self.previous_temperature >= self.settings['fast_threshold']
            and current > self.settings['upper']):
            # Consume each measured change once; collapse further pending jumps.
            if self.pending_jump is None:
                self.pending_jump = {'baseline': self.previous_temperature,
                    'delta': round(current-self.previous_temperature, 2),
                    'created': time.monotonic()}
        self.previous_temperature = current
        self.previous_revision = revision

    async def tick(self, _now):
        async with self.lock:
            state = self.snapshot()
            self.detect_jump(state)
            now = time.monotonic()
            pending = self.pending_jump
            if pending and (not self.settings['fast_enabled']
                or state['maximum'] is None
                or state['maximum'] <= self.settings['upper']
                or state['maximum']-pending['baseline'] < self.settings['fast_threshold']
                or now-pending['created'] > self.settings['stale']):
                self.pending_jump = pending = None
            # A fast step may bypass the normal pause once. Further fast steps
            # must respect a full normal pause after the previous fast step.
            fast_allowed = pending and (self.settings['fast_immediate'] or state['remaining'] <= 0)
            fast_allowed = fast_allowed and (self.last_fast is None or now-self.last_fast >= self.settings['pause'])
            minimum, maximum = self.output_limits()
            if self.enabled and state['ready']:
                fast = bool(fast_allowed)
                if fast:
                    value = round(min(maximum, self.output+self.settings['fast_step']), 1)
                    self.pending_jump = None
                elif pending:
                    value = self.output
                elif state['remaining'] <= 0:
                    value = max(minimum, min(maximum, next_output(state['maximum'], self.output, self.settings)))
                else:
                    value = self.output
                if value != self.output:
                    previous_output = self.output
                    try:
                        await self.send(value)
                    except ValueError:
                        pass
                    else:
                        if fast:
                            self.last_fast = self.last_sent
                            self.last_fast_event = {'time': time.time(), 'jump': pending['delta'],
                                'change': round(value-previous_output, 1)}
            if time.monotonic()-self.last_history >= 5:
                state = self.snapshot()
                self.history.append({'t': time.time(), 'temperature': state['maximum'] if state['ready'] else None, 'output': self.output})
                self.last_history = time.monotonic()

    async def command(self, action, value):
        if action == 'water_command':
            if not isinstance(value, dict) or value.get('id') not in self.waters:
                raise ValueError('Brauchwasser-Regler nicht gefunden')
            await self.waters[value['id']].command(value.get('action'), value.get('value'))
            return self.snapshot()
        if action in ('fan_add', 'fan_command'):
            return await self.fan_action(action, value)
        async with self.lock:
            if action == 'settings':
                self.settings = validate_settings(value)
                self.reset_jump_detection()
                await self.save()
            elif action == 'sources':
                if self.enabled:
                    raise ValueError('Vor dem Ändern der Messquellen die Automatik ausschalten')
                sources = validate_sources(value)
                if sources != self.sources:
                    if [x['base'] for x in sources] != [x['base'] for x in self.sources]:
                        await self.subscribe_sources(sources)
                        self.history.clear()
                    self.sources = sources
                    await self.save()
            elif action == 'enable':
                if not isinstance(value, bool):
                    raise ValueError('Schalterwert ungültig')
                if value:
                    if not self.snapshot()['ready']:
                        raise ValueError('Frische, gültige Temperaturwerte erforderlich')
                    # Synchronize selected start voltage before starting regulation.
                    await self.send(self.output)
                self.enabled = value
                self.reset_jump_detection()
                if value:
                    self.previous_temperature = self.snapshot()['maximum']
                    self.previous_revision = self.temperature_revision()
            elif action == 'manual':
                if self.enabled:
                    raise ValueError('Zuerst die Automatik ausschalten')
                await self.send(value)
            else:
                raise ValueError('Unbekannte Aktion')
        return self.snapshot()

    async def stop(self):
        for water in list(self.waters.values()):
            await water.stop()
        for fan in self.fans.values():
            await fan.stop()
        self.enabled = False
        for unsubscribe in self.unsubscribers + self.mqtt_unsubscribers:
            unsubscribe()
        self.unsubscribers.clear()
        self.mqtt_unsubscribers.clear()
        # Wait for an already running send to finish before unloading.
        async with self.lock:
            self.enabled = False
            await self.save()

@websocket_api.websocket_command({'type': f'{DOMAIN}/state', vol.Optional('history_periods'): dict})
@websocket_api.require_admin
@websocket_api.async_response
async def ws_state(hass, connection, msg):
    controller = hass.data[DOMAIN].get('controller')
    if controller is None:
        connection.send_error(msg['id'], 'not_ready', 'Integration noch nicht eingerichtet')
        return
    periods = msg.get('history_periods', {})
    if any(isinstance(v, bool) or v not in PERIODS for v in periods.values()):
        connection.send_error(msg['id'], 'invalid_value', 'Ungültiger Diagrammzeitraum')
        return
    connection.send_result(msg['id'], controller.snapshot(periods))

@websocket_api.websocket_command({'type': f'{DOMAIN}/command', vol.Required('action'): str, vol.Required('value'): object})
@websocket_api.require_admin
@websocket_api.async_response
async def ws_command(hass, connection, msg):
    controller = hass.data[DOMAIN].get('controller')
    if controller is None:
        connection.send_error(msg['id'], 'not_ready', 'Integration noch nicht eingerichtet')
        return
    try:
        result = await controller.command(msg['action'], msg['value'])
    except (ValueError, TypeError) as err:
        connection.send_error(msg['id'], 'invalid_value', str(err))
        return
    connection.send_result(msg['id'], result)

async def async_setup(hass, config):
    hass.data.setdefault(DOMAIN, {})
    websocket_api.async_register_command(hass, ws_state)
    websocket_api.async_register_command(hass, ws_command)
    await hass.http.async_register_static_paths([
        StaticPathConfig(f'/{DOMAIN}/panel.js', str(Path(__file__).parent / 'panel.js'), False),
        StaticPathConfig(f'/{DOMAIN}/fan-panel.js', str(Path(__file__).parent / 'fan-panel.js'), False),
        StaticPathConfig(f'/{DOMAIN}/water-panel.js', str(Path(__file__).parent / 'water-panel.js'), False),
        StaticPathConfig(f'/{DOMAIN}/warmwasserspeicher-v2.png', str(Path(__file__).parent / 'warmwasserspeicher-v2.png'), False),
        StaticPathConfig(f'/{DOMAIN}/brand', str(Path(__file__).parent / 'brand'), True)])
    return True

async def async_setup_entry(hass, entry):
    if entry.data.get('kind') == 'water':
        return await setup_water_entry(hass, entry)
    if entry.data.get('kind') == 'fan':
        return await setup_fan_entry(hass, entry)
    legacy_id = entry.data.get('legacy_entry_id')
    if legacy_id:
        legacy = hass.config_entries.async_get_entry(legacy_id)
        if legacy and legacy.domain == LEGACY_DOMAIN and legacy.disabled_by is None:
            # Stop the old controller before this one can subscribe or send.
            if not await hass.config_entries.async_set_disabled_by(legacy.entry_id, ConfigEntryDisabler.USER):
                raise RuntimeError('Der bisherige Regler konnte nicht gestoppt werden')
    if entry.title != CONTROLLER_NAME:
        hass.config_entries.async_update_entry(entry, title=CONTROLLER_NAME)
    controller = Controller(hass, entry)
    try:
        await controller.start()
        await controller.save()
        await panel_custom.async_register_panel(hass,
            frontend_url_path=DOMAIN, webcomponent_name='michis-steuerung-panel-030b4',
            sidebar_title=NAME, sidebar_icon='mdi:coolant-temperature',
            module_url=f'/{DOMAIN}/panel.js?v={UI_BUILD}', require_admin=True)
    except Exception:
        await controller.stop()
        raise
    hass.data[DOMAIN]['controller'] = controller
    # Convert Beta1 stored fan definitions to independently managed HA entries.
    try:
        await migrate_legacy_fans(hass, controller)
    except Exception:
        hass.data[DOMAIN].pop('controller', None)
        await controller.stop()
        frontend.async_remove_panel(hass, DOMAIN)
        raise
    # A parent reload replaces the runtime; reload previously running child entries.
    children = {**hass.data[DOMAIN].get('fan_entries', {}), **hass.data[DOMAIN].get('water_entries', {})}
    for child_id, fan in list(children.items()):
        if fan.parent is not controller:
            hass.async_create_task(hass.config_entries.async_reload(child_id))
    return True

async def async_unload_entry(hass, entry):
    if entry.data.get('kind') == 'water':
        water = hass.data[DOMAIN].get('water_entries', {}).pop(entry.entry_id, None)
        if water:
            await water.stop()
            water.parent.waters.pop(water.water_id, None)
        return True
    if entry.data.get('kind') == 'fan':
        fan = hass.data[DOMAIN].get('fan_entries', {}).pop(entry.entry_id, None)
        if fan:
            await fan.stop()
            if fan.parent.fans.get(fan.fan_id) is fan:
                fan.parent.fans.pop(fan.fan_id, None)
        return True
    controller = hass.data[DOMAIN].pop('controller', None)
    if controller:
        await controller.stop()
    frontend.async_remove_panel(hass, DOMAIN)
    return True


async def setup_fan_entry(hass, entry):
    from homeassistant.exceptions import ConfigEntryNotReady
    from .fan import FanController
    parent = hass.data[DOMAIN].get('controller')
    if parent is None:
        raise ConfigEntryNotReady('Michi´s Steuerung wird noch gestartet')
    fan_id = entry.data['fan_id']
    if fan_id in parent.fans:
        return True
    if len(parent.fans) >= 20:
        raise ValueError('Maximal 20 aktive Lüfter möglich')
    saved = await Store(hass, 1, f'{DOMAIN}.fan.{fan_id}').async_load()
    initial = saved or entry.data.get('initial')
    config = initial['config'] if initial else entry.data['config']
    parent.validate_fan_target(config, fan_id)
    fan = FanController(parent, fan_id, config, initial)
    fan.config_entry = entry
    parent.fans[fan_id] = fan
    try:
        await fan.save()
        await fan.start()
    except Exception:
        parent.fans.pop(fan_id, None)
        await fan.stop()
        raise
    hass.data[DOMAIN].setdefault('fan_entries', {})[entry.entry_id] = fan
    return True


async def async_remove_entry(hass, entry):
    if entry.data.get('kind') == 'water':
        await Store(hass, 1, f"{DOMAIN}.water.{entry.data['water_id']}").async_remove()
    if entry.data.get('kind') == 'fan':
        await Store(hass, 1, f"{DOMAIN}.fan.{entry.data['fan_id']}").async_remove()


async def migrate_legacy_fans(hass, controller):
    if not controller.legacy_fans:
        return
    for saved in controller.legacy_fans:
        existing = hass.config_entries.async_entries(DOMAIN)
        if any(e.data.get('kind') == 'fan' and e.data.get('fan_id') == saved['id'] for e in existing):
            continue
        result = await hass.config_entries.flow.async_init(DOMAIN, context={'source': 'import'},
            data={'kind': 'fan', 'fan_id': saved['id'], 'config': saved['config'], 'initial': saved})
        if result['type'] != 'create_entry' and not (result['type'] == 'abort' and result.get('reason') == 'already_configured'):
            raise ValueError('Vorhandener Lüfter konnte nicht übernommen werden; Quelldaten bleiben erhalten')
    controller.legacy_fans = []
    await controller.save()


async def setup_water_entry(hass, entry):
    from homeassistant.exceptions import ConfigEntryNotReady
    from .water import WaterController
    parent = hass.data[DOMAIN].get('controller')
    if parent is None:
        raise ConfigEntryNotReady('Michi´s Steuerung wird noch gestartet')
    water = WaterController(parent, entry)
    validate_water_outputs(parent, water.entities)
    parent.waters[water.water_id] = water
    try:
        await water.start()
    except Exception:
        parent.waters.pop(water.water_id, None)
        await water.stop()
        raise
    hass.data[DOMAIN].setdefault('water_entries', {})[entry.entry_id] = water
    return True


def validate_water_outputs(parent, entities):
    outputs = {entities['top_switch'], entities['bottom_switch'], entities['pump_switch']}
    for water in parent.waters.values():
        if outputs & {water.entities['top_switch'], water.entities['bottom_switch'], water.entities['pump_switch']}:
            raise ValueError('Heizstab oder Pumpe wird bereits durch einen Brauchwasser-Regler verwendet')

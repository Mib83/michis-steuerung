"""HA-entity water controller. Only upper heater and circulation pump are outputs."""
import asyncio
import copy
import time
from datetime import timedelta
from homeassistant.core import callback
from homeassistant.helpers.event import async_track_state_change_event, async_track_time_interval
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util
from .const import DOMAIN
from .engine import finite
from .water_engine import WATER_DEFAULTS, validate_entities, validate_water_settings, water_demand


def state_temperature(state):
    if state is None or state.state in ('unknown','unavailable'):
        return None
    try:
        value = finite(state.state)
        unit = state.attributes.get('unit_of_measurement')
        if unit in ('°F','F'):
            value = (value-32)*5/9
        elif unit == 'K':
            value -= 273.15
        # PyLoxone analog temperature sensors may report a bare degree sign.
        elif unit not in (None,'°C','C','°'):
            return None
        return value if 0 <= value <= 110 else None
    except (ValueError,TypeError):
        return None


def state_binary(state):
    return True if state is not None and state.state == 'on' else False if state is not None and state.state == 'off' else None


class WaterController:
    def __init__(self, parent, entry):
        self.parent,self.hass,self.entry = parent,parent.hass,entry
        self.water_id = entry.data['water_id']
        self.entities = validate_entities(entry.data['entities'])
        self.name = entry.data.get('name','Brauchwasser Regler')
        self.settings = copy.deepcopy(WATER_DEFAULTS)
        self.enabled = False
        self.lock = asyncio.Lock()
        self.unsubscribers = []
        self.store = Store(self.hass,1,f'{DOMAIN}.water.{self.water_id}')
        self.last_top_off = None
        self.pending = {}
        self.last_error = None
        self.last_message = None
        self.persistence_dirty = False
        self.stopping = False

    def read(self, key):
        return self.hass.states.get(self.entities[key])

    def configured(self):
        try:
            validate_water_settings(self.settings)
            return True
        except (ValueError,TypeError):
            return False

    def ready(self):
        return (state_temperature(self.read('top_temperature')) is not None
            and all(state_binary(self.read(key)) is not None for key in ('top_switch','top_feedback','pump_switch','pump_feedback')))

    def remaining(self):
        if self.last_top_off is None or self.settings['wait_off'] is None:
            return 0
        return max(0,self.last_top_off+self.settings['wait_off']-time.time())

    async def start(self):
        saved = await self.store.async_load()
        if saved:
            self.settings = validate_water_settings(saved['settings']) if saved.get('configured') else copy.deepcopy(WATER_DEFAULTS)
            value = saved.get('last_top_off')
            if value is not None:
                self.last_top_off = min(finite(value),time.time())
        if self.last_top_off is None and state_binary(self.read('top_feedback')) is False:
            self.last_top_off = time.time()
        @callback
        def receive(event):
            if event.data['entity_id'] == self.entities['top_feedback']:
                old = state_binary(event.data.get('old_state'))
                new = state_binary(event.data.get('new_state'))
                if new is False and (old is True or self.last_top_off is None):
                    self.last_top_off = time.time()
                    self.persistence_dirty = True
        self.unsubscribers.append(async_track_state_change_event(self.hass,list(self.entities.values()),receive))
        self.unsubscribers.append(async_track_time_interval(self.hass,self.tick,timedelta(seconds=1)))
        # No startup commands; enabling always requires a deliberate user action.

    async def save(self):
        await self.store.async_save({'settings':self.settings,'configured':self.configured(),'last_top_off':self.last_top_off})
        self.persistence_dirty = False

    def snapshot(self):
        top = state_temperature(self.read('top_temperature'))
        bottom = state_temperature(self.read('bottom_temperature'))
        configured,ready = self.configured(),self.ready()
        remaining = self.remaining()
        if self.last_error:
            status = self.last_error
        elif not configured:
            status = 'Zieltemperatur, Wiedereinschalttemperatur und Sperrzeit einstellen'
        elif not ready:
            status = 'Temperatur oder Loxone-Rückmeldung nicht verfügbar'
        elif not self.enabled:
            status = 'Automatik aus'
        elif remaining > 0:
            status = 'Heizstab gesperrt · Erholungszeit'
        else:
            status = 'Normalbetrieb · nur oberer Heizstab'
        if self.enabled and configured and ready and not self.last_error:
            demand = water_demand(self.settings,top,state_binary(self.read('top_feedback')),remaining>0,dt_util.now())
            if demand['legionella']:
                status = 'Legionellenprogramm · nur oberer Heizstab' + (' · Sperrzeit aktiv' if remaining>0 else '')
        return {'id':self.water_id,'name':self.name,'settings':copy.deepcopy(self.settings),
            'entities':dict(self.entities),'top_temperature':top,'bottom_temperature':bottom,
            'top_on':state_binary(self.read('top_feedback')),'bottom_on':state_binary(self.read('bottom_feedback')),
            'pump_on':state_binary(self.read('pump_feedback')),'enabled':self.enabled,
            'enable_available':self.enabled or (configured and ready and not self.pending),
            'wait_remaining':round(remaining,1),'status':status,'last_error':self.last_error,'last_message':self.last_message}

    async def drive(self,key,desired,force=False):
        feedback = state_binary(self.read(key+'_feedback'))
        pending = self.pending.get(key)
        if pending and pending['desired'] == desired:
            if feedback == desired:
                self.pending.pop(key,None)
                return
            if time.monotonic()-pending['sent'] > 15:
                raise ValueError('Loxone-Relaisrückmeldung fehlt · Automatik aus')
            return
        if not pending and not force and feedback == desired:
            return
        action = 'turn_on' if desired else 'turn_off'
        await asyncio.wait_for(self.hass.services.async_call('switch',action,{'entity_id':self.entities[key+'_switch']},blocking=True),10)
        self.pending[key] = {'desired':desired,'sent':time.monotonic(),'sent_wall':time.time()}
        self.last_message = f'{self.entities[key+"_switch"]}: {"An" if desired else "Aus"}'

    async def fail_off(self,message):
        self.enabled = False
        self.last_error = message
        # A compensating OFF is sent once, even if an ON acknowledgement was lost.
        self.pending.clear()
        for key in ('top','pump'):
            try:
                await self.drive(key,False,force=True)
            except Exception:
                self.last_error += ' · Ausschalten '+('oberer Heizstab' if key == 'top' else 'Zirkulationspumpe')+' nicht bestätigt'
        # No automatic restart after a fault.

    async def tick(self,_now):
        async with self.lock:
            if self.stopping:
                return
            if self.persistence_dirty:
                await self.save()
            # Acknowledge outstanding OFF commands even with automation disabled.
            for key,pending in list(self.pending.items()):
                if state_binary(self.read(key+'_feedback')) == pending['desired']:
                    if key == 'top' and not pending['desired'] and (self.last_top_off is None or self.last_top_off < pending['sent_wall']):
                        self.last_top_off = time.time()
                        self.persistence_dirty = True
                    self.pending.pop(key,None)
                elif not self.enabled and time.monotonic()-pending['sent'] > 15:
                    self.pending.pop(key,None)
                    self.last_error = 'Ausschalten nicht durch Loxone bestätigt · Automatik aus'
            if not self.enabled:
                return
            if not self.ready():
                await self.fail_off('Temperatur oder Relaisrückmeldung ausgefallen · Automatik aus')
                return
            demand = water_demand(self.settings,state_temperature(self.read('top_temperature')),
                state_binary(self.read('top_feedback')),self.remaining()>0,dt_util.now())
            try:
                await self.drive('top',demand['heat'])
                await self.drive('pump',demand['pump'])
            except Exception as error:
                await self.fail_off(str(error) or 'Loxone-Schaltbefehl fehlgeschlagen · Automatik aus')

    async def command(self,action,value):
        async with self.lock:
            if action == 'settings':
                settings = validate_water_settings(value)
                self.settings = settings
                await self.save()
            elif action == 'enable':
                if not isinstance(value,bool):
                    raise ValueError('Schalterwert ungültig')
                if value:
                    if not self.configured() or not self.ready() or self.pending:
                        raise ValueError('Gültige Einstellungen, Temperatur und bestätigte Loxone-Rückmeldungen erforderlich')
                    self.last_error = None
                    self.enabled = True
                else:
                    self.enabled = False
                    try:
                        await self.drive('top',False)
                        await self.drive('pump',False)
                    except Exception as error:
                        self.last_error = str(error)
                        raise ValueError('Ausschalten fehlgeschlagen; Loxone-Rückmeldung prüfen') from error
            else:
                raise ValueError('Unbekannte Brauchwasser-Aktion')
        return self.snapshot()

    async def stop(self):
        self.stopping = True
        for unsubscribe in self.unsubscribers:
            unsubscribe()
        self.unsubscribers.clear()
        async with self.lock:
            if self.enabled:
                await self.fail_off('Regler gestoppt · Automatik aus')
            self.enabled = False
            await self.save()

"""One-time setup, no manually created helpers."""
import uuid
import ipaddress
import probatio as vol
from homeassistant import config_entries
from homeassistant.helpers import selector
from homeassistant.core import callback
from .const import DOMAIN, NAME, LEGACY_DOMAIN, CONTROLLER_NAME

class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return DeviceOptionsFlow()


    async def async_step_user(self, user_input=None):
        if user_input is None:
            legacy_entries = self.hass.config_entries.async_entries(LEGACY_DOMAIN)
            if legacy_entries and not self._async_current_entries():
                self.legacy = legacy_entries[0]
                return await self.async_step_legacy()
        return self.async_show_menu(step_id='user', menu_options=['miner', 'fan', 'water'])

    async def async_step_miner(self, user_input=None):
        if any(e.data.get('kind') not in ('fan','water') for e in self._async_current_entries()):
            return self.async_abort(reason='single_miner_allowed')
        errors = {}
        if user_input is not None:
            try:
                ip = ipaddress.ip_address(user_input['host'].strip())
                if ip.version != 4:
                    raise ValueError()
                port = int(user_input['port'])
                if not 1 <= port <= 65535:
                    raise ValueError()
                miners = [x.strip() for x in user_input['miners'].split(',')]
                if len(miners) != 4 or len(set(miners)) != 4 or any(not x or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-'  for c in x) for x in miners):
                    raise ValueError()
                prefix = user_input['prefix'].strip().rstrip('/')
                if not prefix or any(c in prefix for c in '+#\x00\r\n'):
                    raise ValueError()
                command = user_input['command'].strip()
                if not command or any(c in command for c in '\r\n') or len(command) > 100:
                    raise ValueError()
                return self.async_create_entry(title=CONTROLLER_NAME, data={
                    'host': str(ip), 'port': port, 'miners': miners,
                    'command': command, 'prefix': user_input['prefix'].strip().rstrip('/'),
                })
            except (ValueError, KeyError, TypeError):
                errors['base'] = 'invalid_config'
        return self.async_show_form(step_id='miner', errors=errors, data_schema=vol.Schema({
            vol.Required('host', default='172.16.30.3'): str,
            vol.Required('port', default=7000): selector.NumberSelector(selector.NumberSelectorConfig(min=1,max=65535,mode='box',step=1)),
            vol.Required('command', default='MinerGrundwasser:'): str,
            vol.Required('prefix', default='4A/Miner'): str,
            vol.Required('miners', default='M63S-1,M63S-2,M73S-1,M73S-2'): str,
        }))

    async def async_step_legacy(self, user_input=None):
        if user_input is not None:
            data = dict(self.legacy.data)
            data['legacy_entry_id'] = self.legacy.entry_id
            return self.async_create_entry(title=CONTROLLER_NAME, data=data)
        return self.async_show_form(step_id='legacy', data_schema=vol.Schema({}))


    async def async_step_fan(self, user_input=None):
        from .fan import validate_config
        parent = self.hass.data.get(DOMAIN, {}).get('controller')
        if parent is None:
            return self.async_abort(reason='controller_not_ready')
        errors = {}
        if user_input is not None:
            try:
                config = validate_config(user_input)
                parent.validate_fan_target(config)
            except (ValueError, TypeError, KeyError) as err:
                errors['base'] = 'invalid_fan'
                self._fan_error = str(err)
            else:
                fan_id = uuid.uuid4().hex
                await self.async_set_unique_id('fan_' + fan_id)
                return self.async_create_entry(title=config['name'], data={
                    'kind': 'fan', 'fan_id': fan_id, 'config': config})
        defaults = {'name': '0-10V Lüftersteuerung Loxone', 'sensor_host': '',
            'sensor_port': 502, 'unit': 1, 'host': parent.entry.data['host'],
            'port': parent.entry.data['port'], 'command': 'Luefter:',
            'minimum': 2, 'maximum': 10, 'off_mode': 'minimum', **(user_input or {})}
        schema = {}
        for key in ('name', 'sensor_host', 'sensor_port', 'unit', 'host', 'port', 'command', 'minimum', 'maximum', 'off_mode'):
            if key in ('sensor_port', 'port', 'unit', 'minimum', 'maximum'):
                low, high, step = (0, 10, .1) if key in ('minimum', 'maximum') else (0 if key == 'unit' else 1, 255 if key == 'unit' else 65535, 1)
                typ = selector.NumberSelector(selector.NumberSelectorConfig(min=low, max=high, step=step, mode='box'))
            elif key == 'off_mode':
                typ = selector.SelectSelector(selector.SelectSelectorConfig(options=[
                    {'value': 'minimum', 'label': 'Mindestspannung senden'},
                    {'value': 'hold', 'label': 'Letzten Stellwert halten'},
                    {'value': 'zero', 'label': '0 V senden'}], mode='dropdown'))
            else:
                typ = str
            schema[vol.Required(key, default=defaults[key])] = typ
        return self.async_show_form(step_id='fan', data_schema=vol.Schema(schema), errors=errors,
            description_placeholders={'error': getattr(self, '_fan_error', '')})

    async def async_step_import(self, data):
        from .fan import validate_config
        if data.get('kind') != 'fan':
            return self.async_abort(reason='invalid_import')
        await self.async_set_unique_id('fan_' + data['fan_id'])
        self._abort_if_unique_id_configured()
        config = validate_config(data['config'])
        return self.async_create_entry(title=config['name'], data=data)


    async def async_step_water(self, user_input=None):
        from . import validate_water_outputs
        from .water_engine import DEFAULT_ENTITIES, validate_entities
        parent = self.hass.data.get(DOMAIN, {}).get('controller')
        if parent is None:
            return self.async_abort(reason='controller_not_ready')
        errors = {}
        if user_input is not None:
            try:
                entities = validate_entities(user_input)
                validate_water_outputs(parent, entities)
            except (ValueError,TypeError) as error:
                errors['base'] = 'invalid_water'
                self._water_error = str(error)
            else:
                water_id = uuid.uuid4().hex
                await self.async_set_unique_id('water_' + water_id)
                return self.async_create_entry(title='Brauchwasser Regler',data={
                    'kind':'water','water_id':water_id,'name':'Brauchwasser Regler','entities':entities})
        schema = {}
        for key, default in DEFAULT_ENTITIES.items():
            domain = 'sensor' if key.endswith('temperature') else 'switch' if key.endswith('switch') else 'binary_sensor'
            schema[vol.Required(key,default=(user_input or {}).get(key,default))] = selector.EntitySelector(selector.EntitySelectorConfig(domain=domain))
        return self.async_show_form(step_id='water',data_schema=vol.Schema(schema),errors=errors,
            description_placeholders={'error':getattr(self,'_water_error','')})


class DeviceOptionsFlow(config_entries.OptionsFlow):
    """Edit the existing source/output mappings through the HA Configure button."""

    async def async_step_init(self, user_input=None):
        from . import Controller, validate_water_outputs
        from .engine import validate_sources
        from .fan import validate_config
        from .water_engine import validate_entities
        parent = self.hass.data.get(DOMAIN,{}).get('controller')
        if parent is None:
            return self.async_abort(reason='controller_not_ready')
        entry = self.config_entry
        kind = entry.data.get('kind','miner')
        errors = {}
        runtime = parent.fans.get(entry.data.get('fan_id')) if kind=='fan' else parent.waters.get(entry.data.get('water_id')) if kind=='water' else parent
        if runtime is None:
            return self.async_abort(reason='controller_not_ready')
        defaults = {}
        if kind=='fan':
            defaults = dict(runtime.config)
        elif kind=='water':
            defaults = dict(runtime.entities)
        else:
            defaults = {k:entry.data[k] for k in ('host','port','command')}
            defaults.update(feedback_entity=parent.valve_feedback['entity_id'],feedback_unit=parent.valve_feedback['unit'])
            for i,source in enumerate(parent.sources):
                defaults.update({f'miner_{i}_name':source['name'],f'miner_{i}_base':source['base']})
                defaults.update({f'miner_{i}_label_{j}':label for j,label in enumerate(source['labels'])})
        if user_input is not None:
            try:
                if runtime.enabled or (kind=='water' and (runtime.legionella_active() or runtime.timer_owned or runtime.top_timer_owned or runtime.program_owned)):
                    raise ValueError('Vor dem Ändern Automatik und Timer ausschalten')
                if kind=='water':
                    entities = validate_entities(user_input)
                    others = type('OtherControllers',(),{'waters':{k:v for k,v in parent.waters.items() if v is not runtime}})()
                    validate_water_outputs(others,entities)
                    if runtime.pending:
                        raise ValueError('Auf bestätigtes Ausschalten warten')
                    await runtime.stop()
                    self.hass.config_entries.async_update_entry(entry,data={**entry.data,'entities':entities})
                    await self.hass.config_entries.async_reload(entry.entry_id)
                elif kind=='fan':
                    config = validate_config(user_input)
                    parent.validate_fan_target(config,runtime.fan_id)
                    await runtime.command('config',config)
                    self.hass.config_entries.async_update_entry(entry,data={**entry.data,'config':config},title=config['name'])
                else:
                    ip = ipaddress.ip_address(user_input['host'].strip())
                    port = int(user_input['port']);command = user_input['command'].strip()
                    if ip.version!=4 or not 1<=port<=65535 or not command or len(command)>100 or any(c in command for c in '\r\n'):
                        raise ValueError('UDP-Ziel ungültig')
                    feedback = Controller.validate_valve_feedback({'entity_id':user_input.get('feedback_entity',''),'unit':user_input['feedback_unit']})
                    sources = validate_sources([{'name':user_input[f'miner_{i}_name'],'base':user_input[f'miner_{i}_base'],'labels':[user_input[f'miner_{i}_label_{j}'] for j in range(4)]} for i in range(4)])
                    await parent.command('sources',sources)
                    await parent.command('valve_feedback',feedback)
                    self.hass.config_entries.async_update_entry(entry,data={**entry.data,'host':str(ip),'port':port,'command':command})
                return self.async_create_entry(title='',data={})
            except (ValueError,TypeError,KeyError) as error:
                errors['base']='invalid_device'
                self._error=str(error)
        defaults.update(user_input or {})
        schema={}
        for key,value in defaults.items():
            typ=str
            if kind=='water':
                domain='sensor' if key.endswith('temperature') else 'switch' if key.endswith('switch') else 'binary_sensor'
                typ=selector.EntitySelector(selector.EntitySelectorConfig(domain=domain))
            elif key in ('port','sensor_port','unit','minimum','maximum'):
                low,high,step=(0,10,.1) if key in ('minimum','maximum') else (0 if key=='unit' else 1,255 if key=='unit' else 65535,1)
                typ=selector.NumberSelector(selector.NumberSelectorConfig(min=low,max=high,step=step,mode='box'))
            elif key in ('feedback_unit','off_mode'):
                options=['V','%'] if key=='feedback_unit' else ['minimum','hold','zero']
                typ=selector.SelectSelector(selector.SelectSelectorConfig(options=options,mode='dropdown'))
            marker=vol.Optional(key,default=value) if key=='feedback_entity' else vol.Required(key,default=value)
            schema[marker]=typ
        return self.async_show_form(step_id='init',data_schema=vol.Schema(schema),errors=errors,
            description_placeholders={'error':getattr(self,'_error','')})

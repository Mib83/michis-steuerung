"""One-time setup, no manually created helpers."""
import uuid
import ipaddress
import probatio as vol
from homeassistant import config_entries
from homeassistant.helpers import selector
from .const import DOMAIN, NAME, LEGACY_DOMAIN, CONTROLLER_NAME

class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        if user_input is None:
            legacy_entries = self.hass.config_entries.async_entries(LEGACY_DOMAIN)
            if legacy_entries and not self._async_current_entries():
                self.legacy = legacy_entries[0]
                return await self.async_step_legacy()
        return self.async_show_menu(step_id='user', menu_options=['miner', 'fan'])

    async def async_step_miner(self, user_input=None):
        if any(e.data.get('kind') != 'fan' for e in self._async_current_entries()):
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

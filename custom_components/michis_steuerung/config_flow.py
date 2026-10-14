"""One-time setup, no manually created helpers."""
import ipaddress
import probatio as vol
from homeassistant import config_entries
from homeassistant.helpers import selector
from .const import DOMAIN, NAME, LEGACY_DOMAIN, CONTROLLER_NAME

class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        if self._async_current_entries():
            return self.async_abort(reason='single_instance_allowed')
        if user_input is None:
            legacy_entries = self.hass.config_entries.async_entries(LEGACY_DOMAIN)
            if legacy_entries:
                self.legacy = legacy_entries[0]
                return await self.async_step_legacy()
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
        return self.async_show_form(step_id='user', errors=errors, data_schema=vol.Schema({
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

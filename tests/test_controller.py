"""Controller tests with mocked HA adapters and captured UDP datagrams."""
import asyncio
import importlib.util
import json
from pathlib import Path
import socket
import sys
import time
import types
import unittest
from unittest.mock import patch, AsyncMock
ROOT = Path(__file__).parent.parent / 'custom_components/michis_steuerung'
def module(name, **attrs):
    m=types.ModuleType(name)
    for k,v in attrs.items():setattr(m,k,v)
    sys.modules[name]=m
    return m
identity=lambda f:f
module('probatio',Required=lambda x:x)
module('homeassistant')
module('homeassistant.config_entries',ConfigEntryDisabler=types.SimpleNamespace(USER='user'))
module('homeassistant.components')
callbacks={}
async def subscribe(hass,topic,receive,qos):
    callbacks[topic]=receive
    def unsubscribe():
        if callbacks.get(topic) is receive:callbacks.pop(topic,None)
    return unsubscribe
module('homeassistant.components.mqtt',async_subscribe=subscribe)
module('homeassistant.components.panel_custom')
module('homeassistant.components.frontend')
module('homeassistant.components.websocket_api',websocket_command=lambda schema:identity,require_admin=identity,async_response=identity)
module('homeassistant.components.http',StaticPathConfig=lambda *args:args)
module('homeassistant.core',callback=identity)
module('homeassistant.helpers')
module('homeassistant.helpers.event',async_track_time_interval=lambda *args:lambda:None)
class Store:
    def __init__(self,*args):self.data=None
    async def async_load(self):return self.data
    async def async_save(self,data):self.data=json.loads(json.dumps(data))
module('homeassistant.helpers.storage',Store=Store)
package='controller_under_test'
spec=importlib.util.spec_from_file_location(package,ROOT/'__init__.py',submodule_search_locations=[str(ROOT)])
backend=importlib.util.module_from_spec(spec);sys.modules[package]=backend;spec.loader.exec_module(backend)
engine=sys.modules[package+'.engine']
class Hass:
    bus=types.SimpleNamespace(async_listen_once=lambda *args:lambda:None)
    async def async_add_executor_job(self,func):return await asyncio.to_thread(func)
class Tests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        callbacks.clear()
        self.sent=[]
        test=self
        class FakeSocket:
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def sendto(self,payload,target):test.sent.append((payload,target))
        self.socket_patch=patch.object(backend.socket,'socket',return_value=FakeSocket())
        self.socket_patch.start()
        self.entry=types.SimpleNamespace(entry_id='test',data={'host':'127.0.0.1','port':7000,'miners':['m63s_1','m63s_2','m73s_1','m73s_2'],'prefix':'miners','command':'MinerGrundwasser:'})
        self.c=backend.Controller(Hass(),self.entry);await self.c.start()
    async def asyncTearDown(self):await self.c.stop();self.socket_patch.stop()
    def fill(self,temp=45):
        for topic,receive in callbacks.items():receive(types.SimpleNamespace(payload=str(500 if '/ths/' in topic else temp),retain=False))
    async def receive(self):
        payload,target=self.sent.pop(0)
        self.assertEqual(target,('127.0.0.1',7000))
        return payload.decode()
    async def test_start_is_off_and_no_command(self):
        self.assertFalse(self.c.enabled);self.assertIsNone(self.c.last_message);self.assertEqual(len(callbacks),20)
    async def test_retained_does_not_enable(self):
        for receive in callbacks.values():receive(types.SimpleNamespace(payload='44',retain=True))
        self.assertFalse(self.c.snapshot()['ready'])
        with self.assertRaises(ValueError):await self.c.command('enable',True)
    async def test_udp_message_and_destination(self):
        await self.c.command('manual',4.3);self.assertEqual(await self.receive(),'MinerGrundwasser:4.3')
    async def test_hot_step_and_cooldown(self):
        self.fill();await self.c.command('enable',True);await self.receive()
        self.c.last_sent=time.monotonic()-16
        await self.c.tick(None);self.assertEqual(await self.receive(),'MinerGrundwasser:4.2')
        await self.c.tick(None);self.assertEqual(self.c.output,4.2)
    async def test_cold_step(self):
        self.fill(42);self.c.enabled=True;await self.c.tick(None)
        self.assertEqual(await self.receive(),'MinerGrundwasser:3.8')
    async def test_deadband_inclusive(self):
        for temp in [43,43.5,44]:
            self.fill(temp);self.c.enabled=True;await self.c.tick(None);self.assertEqual(self.c.output,4)
        self.assertIsNone(self.c.last_message)
    async def test_missing_one_holds(self):
        self.fill();self.c.enabled=True
        self.c.samples.pop('miners/m73s_2/sm3/state')
        await self.c.tick(None);self.assertEqual(self.c.output,4);self.assertFalse(self.c.snapshot()['ready'])
    async def test_stale_holds(self):
        self.fill();self.c.enabled=True
        self.c.samples={k:(v[0],time.monotonic()-31) for k,v in self.c.samples.items()}
        await self.c.tick(None);self.assertEqual(self.c.output,4)
    async def test_invalid_input_invalidation(self):
        self.fill();callbacks['miners/m63s_1/sm0/state'](types.SimpleNamespace(payload='NaN',retain=False))
        self.assertFalse(self.c.snapshot()['ready'])
    async def test_manual_locked_when_auto(self):
        self.fill();self.c.enabled=True
        with self.assertRaises(ValueError):await self.c.command('manual',3)
    async def test_reject_bad_settings_and_bounds(self):
        for value in [-.1,10.1,float('nan'),True]:
            with self.assertRaises(ValueError):await self.c.command('manual',value)
        data=dict(self.c.settings);data['lower']=45
        with self.assertRaises(ValueError):await self.c.command('settings',data)
        self.assertEqual(self.c.settings['lower'],43)
    async def test_saturation(self):
        self.assertEqual(engine.next_output(60,9.9,self.c.settings),10)
        self.assertEqual(engine.next_output(30,.1,self.c.settings),0)
    async def test_settings_persistence(self):
        data=dict(self.c.settings);data['pause']=20
        await self.c.command('settings',data);self.assertEqual(self.c.store.data['settings']['pause'],20)
    async def test_udp_failure_disables_auto(self):
        self.fill();self.c.enabled=True
        with patch.object(backend.socket,'socket',side_effect=OSError('test')):
            await self.c.tick(None)
        self.assertFalse(self.c.enabled);self.assertIsNotNone(self.c.last_error)
    async def test_restart_restores_settings_not_auto(self):
        self.c.settings=dict(self.c.settings,pause=20);self.c.output=4.8;self.c.enabled=True
        await self.c.stop();await self.c.start()
        self.assertFalse(self.c.enabled);self.assertEqual(self.c.output,4.8);self.assertEqual(self.c.settings['pause'],20)
    async def test_custom_topics_and_names(self):
        sources=[{'name': f'Miner {i+1}', 'base': '4A/Miner/'+name, 'labels': ['Chip A','Chip B','Chip C','Chip D']} for i,name in enumerate(['M63S-1','M63S-2','M73S-1','M73S-2'])]
        self.fill()
        await self.c.command('sources',sources)
        self.assertEqual(len(callbacks),20)
        self.assertIn('4A/Miner/M63S-1/sm0/state',callbacks)
        self.assertNotIn('miners/m63s_1/sm0/state',callbacks)
        self.assertFalse(self.c.snapshot()['ready'])
        self.fill(43.2)
        self.assertTrue(self.c.snapshot()['ready'])
        self.assertEqual(self.c.snapshot()['miners'][0]['labels'][0],'Chip A')
        self.assertEqual(self.c.snapshot()['miners'][0]['name'],'Miner 1')
    async def test_source_change_requires_manual(self):
        self.c.enabled=True
        with self.assertRaises(ValueError):await self.c.command('sources',self.c.sources)
    async def test_label_change_keeps_measurements(self):
        self.fill()
        sources=[dict(x,labels=list(x['labels'])) for x in self.c.sources]
        sources[0]['labels'][0]='Wärmster Chip links'
        await self.c.command('sources',sources)
        self.assertTrue(self.c.snapshot()['ready'])
        self.assertEqual(len(callbacks),20)
    async def test_sources_restore_after_restart(self):
        sources=[dict(x,base='4A/Miner/'+x['name']) for x in self.c.sources]
        await self.c.command('sources',sources)
        saved=self.c.store.data
        await self.c.stop()
        other=backend.Controller(Hass(),self.entry);other.store.data=saved
        await other.start()
        self.assertEqual(other.sources,sources)
        self.assertFalse(other.enabled)
        self.assertIn('4A/Miner/M63S-1/sm0/state',callbacks)
        await other.stop()
    async def test_bad_sources_leave_existing_sources_unchanged(self):
        original=self.c.sources
        for bad in [[],[{}]*4,[dict(x,base='4A/#') for x in original],[dict(x,base='4A/same') for x in original]]:
            with self.assertRaises(ValueError):await self.c.command('sources',bad)
        self.assertEqual(self.c.sources,original)
    async def test_trailing_slash_normalized(self):
        sources=[dict(x,base=x['base']+'/') for x in self.c.sources]
        await self.c.command('sources',sources)
        self.assertFalse(any(x['base'].endswith('/') for x in self.c.sources))
    async def enable_with_baseline(self, temperature=44.5):
        self.fill(temperature)
        await self.c.command('enable',True)
        await self.receive()
    async def test_fast_bypasses_normal_pause_once(self):
        await self.enable_with_baseline()
        self.fill(47.5)
        await self.c.tick(None)
        self.assertEqual(await self.receive(),'MinerGrundwasser:4.6')
        self.assertEqual(self.c.last_fast_event['jump'],3)
        self.assertGreater(self.c.snapshot()['remaining'],14)
        self.fill(47.5)
        await self.c.tick(None)
        self.assertEqual(self.c.output,4.6)
        self.assertEqual(len(self.sent),0)
    async def test_fast_respects_pause_when_configured(self):
        self.c.settings['fast_immediate']=False
        await self.enable_with_baseline()
        self.fill(47.5);await self.c.tick(None)
        self.assertTrue(self.c.snapshot()['fast_pending'])
        self.assertEqual(len(self.sent),0)
        self.c.last_sent=time.monotonic()-16
        await self.c.tick(None)
        self.assertEqual(await self.receive(),'MinerGrundwasser:4.6')
        self.assertFalse(self.c.snapshot()['fast_pending'])
    async def test_pending_jump_cancels_when_temperature_recovers(self):
        self.c.settings['fast_immediate']=False
        await self.enable_with_baseline()
        self.fill(47.5);await self.c.tick(None)
        self.fill(43.5);await self.c.tick(None)
        self.assertFalse(self.c.snapshot()['fast_pending'])
        self.c.last_sent=time.monotonic()-16
        await self.c.tick(None)
        self.assertEqual(len(self.sent),0)
    async def test_fast_disabled_uses_normal_step(self):
        self.c.settings['fast_enabled']=False
        await self.enable_with_baseline()
        self.fill(47.5);await self.c.tick(None)
        self.assertEqual(len(self.sent),0)
        self.c.last_sent=time.monotonic()-16
        await self.c.tick(None)
        self.assertEqual(await self.receive(),'MinerGrundwasser:4.2')
    async def test_falling_jump_does_not_boost(self):
        await self.enable_with_baseline(46)
        self.fill(42);await self.c.tick(None)
        self.assertEqual(len(self.sent),0)
        self.c.last_sent=time.monotonic()-16
        await self.c.tick(None)
        self.assertEqual(await self.receive(),'MinerGrundwasser:3.8')
    async def test_jump_inside_band_does_not_boost(self):
        await self.enable_with_baseline(40.5)
        self.fill(43.5);await self.c.tick(None)
        self.assertEqual(len(self.sent),0)
    async def test_second_jump_waits_after_fast_step(self):
        await self.enable_with_baseline()
        self.fill(47.5);await self.c.tick(None);await self.receive()
        self.fill(50.5);await self.c.tick(None)
        self.assertEqual(len(self.sent),0)
        self.assertTrue(self.c.snapshot()['fast_pending'])
        self.c.last_sent=time.monotonic()-16;self.c.last_fast=time.monotonic()-16
        await self.c.tick(None)
        self.assertEqual(await self.receive(),'MinerGrundwasser:5.2')
    async def test_missing_data_does_not_create_restoration_jump(self):
        await self.enable_with_baseline()
        self.c.samples.pop('miners/m63s_1/sm0/state');await self.c.tick(None)
        self.fill(47.5);await self.c.tick(None)
        self.assertEqual(len(self.sent),0)
        self.assertIsNone(self.c.pending_jump)
    async def test_fast_at_voltage_limit_clamps(self):
        self.c.output=9.8
        await self.enable_with_baseline()
        self.fill(47.5);await self.c.tick(None)
        self.assertEqual(await self.receive(),'MinerGrundwasser:10.0')
        self.assertEqual(self.c.last_fast_event['change'],.2)
    async def test_old_settings_preserved_on_upgrade(self):
        legacy={'lower':43,'upper':44,'step':.2,'pause':15,'stale':30}
        self.c.store.data={'settings':legacy,'output':4.8,'sources':self.c.sources}
        other=backend.Controller(Hass(),self.entry);other.store.data=self.c.store.data
        await self.c.stop();await other.start()
        self.assertEqual(other.settings['pause'],15)
        self.assertEqual(other.settings['fast_threshold'],3)
        self.assertEqual(other.settings['fast_step'],.6)
        self.assertEqual(other.output,4.8)
        self.assertFalse(other.enabled)
        await other.stop()
    async def test_fast_settings_validation_and_persistence(self):
        settings=dict(self.c.settings,fast_threshold=2,fast_step=.8,fast_immediate=False)
        await self.c.command('settings',settings)
        self.assertEqual(self.c.store.data['settings']['fast_step'],.8)
        for key,value in [('fast_step',.15),('fast_step',.1),('fast_threshold',0),('fast_enabled',1)]:
            with self.assertRaises(ValueError):await self.c.command('settings',dict(settings,**{key:value}))
    async def test_compact_sent_value_not_invented_before_first_send(self):
        self.assertIsNone(self.c.snapshot()['sent_output'])
        await self.c.command('manual',4.3)
        self.assertEqual(self.c.snapshot()['sent_output'],4.3)
        self.assertEqual(self.c.store.data['last_sent_output'],4.3)
    async def test_last_sent_value_survives_restart(self):
        await self.c.command('manual',4.3)
        saved=self.c.store.data
        await self.c.stop()
        other=backend.Controller(Hass(),self.entry);other.store.data=saved
        await other.start()
        self.assertEqual(other.snapshot()['sent_output'],4.3)
        self.assertFalse(other.enabled)
        await other.stop()
    async def test_legacy_store_is_imported(self):
        self.entry.data['legacy_entry_id']='legacy123'
        legacy_store=Store()
        sources=[dict(x,name='Alter Name '+str(i)) for i,x in enumerate(self.c.sources)]
        legacy_store.data={'settings':dict(self.c.settings,pause=15),'output':4.8,'sources':sources,'last_sent_output':4.8}
        await self.c.stop()
        other=backend.Controller(Hass(),self.entry)
        with patch.object(backend,'Store',side_effect=lambda hass,version,key: legacy_store if key==backend.LEGACY_DOMAIN+'.legacy123' else Store()):
            await other.start()
        await other.save()
        self.assertEqual(other.sources,sources)
        self.assertEqual(other.output,4.8)
        self.assertEqual(other.snapshot()['sent_output'],4.8)
        self.assertFalse(other.enabled)
        self.assertEqual(other.store.data['sources'],sources)
        self.assertEqual(len(self.sent),0)
        await other.stop()
    async def test_new_store_takes_precedence_over_legacy(self):
        self.entry.data['legacy_entry_id']='legacy123'
        await self.c.stop()
        other=backend.Controller(Hass(),self.entry)
        other.store.data={'settings':dict(self.c.settings,pause=20),'output':5.2}
        with patch.object(backend,'Store',side_effect=AssertionError('Alte Daten dürfen nicht erneut importiert werden')):
            await other.start()
        self.assertEqual(other.output,5.2)
        self.assertEqual(other.settings['pause'],20)
        await other.stop()
    async def test_migration_aborts_if_old_controller_cannot_stop(self):
        self.entry.data['legacy_entry_id']='legacy123'
        hass=Hass()
        hass.config_entries=types.SimpleNamespace(async_get_entry=lambda key:types.SimpleNamespace(entry_id=key,domain=backend.LEGACY_DOMAIN,disabled_by=None),async_set_disabled_by=AsyncMock(return_value=False))
        with self.assertRaises(RuntimeError):await backend.async_setup_entry(hass,self.entry)
        hass.config_entries.async_set_disabled_by.assert_awaited_once_with('legacy123','user')
    async def test_config_flow_offers_legacy_import(self):
        class FlowBase:
            def __init_subclass__(cls, **kwargs):pass
            def _async_current_entries(self):return []
            def async_show_form(self, **kwargs):return kwargs
            def async_create_entry(self, **kwargs):return kwargs
        sys.modules['homeassistant.config_entries'].ConfigFlow=FlowBase
        sys.modules['probatio'].Schema=lambda data:data
        module('homeassistant.helpers.selector')
        spec=importlib.util.spec_from_file_location(package+'.config_flow',ROOT/'config_flow.py')
        flow_module=importlib.util.module_from_spec(spec);spec.loader.exec_module(flow_module)
        flow=flow_module.ConfigFlow()
        legacy=types.SimpleNamespace(entry_id='old123',data=self.entry.data)
        flow.hass=types.SimpleNamespace(config_entries=types.SimpleNamespace(async_entries=lambda domain:[legacy] if domain==backend.LEGACY_DOMAIN else []))
        form=await flow.async_step_user()
        self.assertEqual(form['step_id'],'legacy')
        result=await flow.async_step_legacy({})
        self.assertEqual(result['data']['legacy_entry_id'],'old123')
        self.assertEqual(result['data']['host'],self.entry.data['host'])
        self.assertEqual(result['title'],'Miner Ventiel Grundwasser Regler')

class FanTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        from controller_under_test.fan import FanController
        self.parent = backend.Controller(Hass(), types.SimpleNamespace(entry_id='test', data={'host':'127.0.0.1','port':7000,'miners':[],'prefix':'miners','command':'Miner:'}))
        self.config={'name':'0-10V Lüftersteuerung Loxone','sensor_host':'127.0.0.2','sensor_port':502,'unit':1,'host':'127.0.0.1','port':7000,'command':'Fan:','minimum':2,'maximum':10,'off_mode':'minimum'}
        self.f=FanController(self.parent,'fan1',self.config)
        self.parent.fans['fan1']=self.f
        self.sent=[]
        self.patch=patch.object(backend.socket,'socket')
        mock=self.patch.start();mock.return_value.__enter__.return_value.sendto.side_effect=lambda payload,target:self.sent.append((payload,target))
    async def asyncTearDown(self):
        self.patch.stop()
    def measured(self,temp):
        self.f.measurement=(temp,50,time.monotonic())
    async def test_minimum_sent_once_and_120_second_pause(self):
        self.measured(30)
        await self.f.command('enable',True)
        self.assertEqual(self.sent[0][0],b'Fan:2.0')
        await self.f.tick(None)
        self.assertEqual(len(self.sent),1)
        self.f.last_sent=time.monotonic()-121
        await self.f.tick(None)
        self.assertEqual(self.sent[-1][0],b'Fan:2.2')
    async def test_minimum_not_repeated_when_cold(self):
        self.measured(26);await self.f.command('enable',True)
        self.f.last_sent=time.monotonic()-121
        for _ in range(3):await self.f.tick(None)
        self.assertEqual(len(self.sent),1);self.assertEqual(self.f.output,2)
    async def test_independent_fans_and_settings_restored(self):
        from controller_under_test.fan import FanController
        self.f.output=3.2;await self.f.save()
        saved=self.parent.store.data['fans'][0]
        restored=FanController(self.parent,'fan1',saved['config'],saved)
        self.assertEqual(restored.output,3.2);self.assertEqual(restored.settings['pause'],120)
        self.assertFalse(restored.enabled);self.assertEqual(self.parent.output,4)
    async def test_off_minimum_hold_and_zero(self):
        for mode,expected in [('minimum',2),('hold',4),('zero',0)]:
            self.f.config['off_mode']=mode;self.f.output=4;self.f.last_sent_output=4;self.f.enabled=True
            await self.f.command('enable',False)
            self.assertEqual(self.f.output,expected);self.assertFalse(self.f.enabled)
        count=len(self.sent);await self.f.command('enable',False);self.assertEqual(len(self.sent),count)
    async def test_sensor_failure_holds_and_invalidates(self):
        from controller_under_test import fan
        self.measured(30);self.f.enabled=True
        with patch.object(fan,'read_climate',new=AsyncMock(side_effect=ValueError('ungültig'))):await self.f.poll(None)
        await self.f.tick(None)
        self.assertFalse(self.f.snapshot()['ready']);self.assertEqual(self.sent,[])
    async def test_fast_jump_clamps_to_configured_maximum(self):
        self.f.config['maximum']=3;self.measured(28);await self.f.command('enable',True)
        self.f.output=2.8;self.measured(32);await self.f.tick(None)
        self.assertEqual(self.sent[-1][0],b'Fan:3.0')
        await self.f.tick(None);self.assertEqual(len(self.sent),2)
    async def test_config_validation_is_atomic_and_target_unique(self):
        with self.assertRaises(ValueError):await self.f.command('configure',{'config':dict(self.config,minimum=9,maximum=2),'settings':self.f.settings})
        self.assertEqual(self.f.config['minimum'],2)
        with self.assertRaises(ValueError):self.parent.validate_fan_target(dict(self.config,command='Miner:'))
    async def test_settings_can_change_while_auto_on(self):
        self.measured(28);await self.f.command('enable',True)
        await self.f.command('configure',{'config':self.config,'settings':dict(self.f.settings,pause=150)})
        self.assertEqual(self.f.settings['pause'],150);self.assertTrue(self.f.enabled)
    async def test_manual_cannot_bypass_minimum(self):
        with self.assertRaises(ValueError):await self.f.command('manual',1)
        self.assertEqual(self.sent,[])

class ModbusTests(unittest.IsolatedAsyncioTestCase):
    async def test_signed_temperature_and_invalid_registers(self):
        from controller_under_test.modbus import decode_measurements
        self.assertEqual(decode_measurements((65036,5000,3)),(-5,50))
        for registers in [(32768,5000,3),(2800,65535,3),(2800,5000,0),(9000,5000,3)]:
            with self.assertRaises(ValueError):decode_measurements(registers)
    async def exchange(self, reply):
        from controller_under_test import modbus
        reader=asyncio.StreamReader();reader.feed_data(reply);reader.feed_eof()
        writer=types.SimpleNamespace(write=lambda data:setattr(self,'request',data),drain=AsyncMock(),close=lambda:None,wait_closed=AsyncMock())
        with patch.object(modbus.asyncio,'open_connection',new=AsyncMock(return_value=(reader,writer))):
            return await modbus.read_climate('127.0.0.1')
    async def test_read_three_holding_registers_in_one_request(self):
        import struct
        reply=struct.pack('>HHHBBBHHH',1,0,9,1,3,6,2750,5000,3)
        self.assertEqual(await self.exchange(reply),(27.5,50))
        self.assertEqual(self.request,bytes.fromhex('000100000006010300000003'))
    async def test_wrong_transaction_exception_and_truncated_reply(self):
        import struct
        for reply in [struct.pack('>HHHBBB',2,0,3,1,0x83,2),struct.pack('>HHHBBB',1,0,3,1,0x83,2),b'\0']:
            with self.assertRaises((ValueError,asyncio.IncompleteReadError)):await self.exchange(reply)

if __name__=='__main__':unittest.main(verbosity=2)

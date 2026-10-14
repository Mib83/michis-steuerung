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
from unittest.mock import patch
ROOT = Path(__file__).parent.parent / 'custom_components/miner_ventiel_grundwasser_regler'
def module(name, **attrs):
    m=types.ModuleType(name)
    for k,v in attrs.items():setattr(m,k,v)
    sys.modules[name]=m
    return m
identity=lambda f:f
module('probatio',Required=lambda x:x)
module('homeassistant')
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
if __name__=='__main__':unittest.main(verbosity=2)

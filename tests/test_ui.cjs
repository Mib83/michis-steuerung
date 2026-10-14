// UI behavior tests with a minimal DOM adapter; no visual rendering.
const fs=require('fs'),vm=require('vm'),assert=require('assert');
class Root{
  constructor(){this.elements={};this.activeElement=null;}
  set innerHTML(html){this.html=html;for(const m of html.matchAll(/id="([^"]+)"/g))this.elements[m[1]]={value:'',checked:false,disabled:false,style:{},textContent:'',reportValidity:()=>true,hidden:false,attributes:{},setAttribute(k,v){this.attributes[k]=v;},classList:{toggle(){}}};}
  getElementById(id){if(!this.elements[id])throw Error('Missing field '+id);return this.elements[id];}
  querySelectorAll(selector){const ids=Object.keys(this.elements);if(selector==='.sources input')return ids.filter(id=>/^source-(name|base|label)-/.test(id)).map(id=>this.elements[id]);if(selector.includes('.settings input'))return ['lower','upper','step','pause','stale','fast_threshold','fast_step','fast_enabled','fast_immediate'].map(id=>this.elements[id]);if(selector==='button.control')return ['auto','send','save','save-sources'].map(id=>this.elements[id]);throw Error(selector);}
}
let Panel;
const context={console,HTMLElement:class{attachShadow(){this.shadowRoot=new Root()}},customElements:{get:()=>false,define:(_name,cls)=>Panel=cls},setInterval,clearInterval,CustomEvent:class{}};
vm.createContext(context);vm.runInContext(fs.readFileSync(require('path').join(__dirname,'../custom_components/michis_steuerung/panel.js'),'utf8'),context);
(async()=>{
const p=new Panel();p.render();
const settings={lower:43,upper:44,step:.2,pause:15,stale:30,fast_enabled:true,fast_threshold:3,fast_step:.6,fast_immediate:true};
const state={settings,enabled:false,output:4,maximum:43.5,valid_count:16,remaining:0,status:'Manuell',miners:[],sources:[],history:[],target:'localhost:7000',version:'0.1.0',sent_output:4};
let sent;
p._hass={callWS:async msg=>{sent=msg;if(msg.action==='settings')state.settings=msg.value;if(msg.action==='enable')state.enabled=msg.value;return state;}};
p.state=state;p.update();
assert.equal(p.shadowRoot.getElementById('pause').value,15);
assert.equal(p.shadowRoot.getElementById('fast_enabled').checked,true);
const threshold=p.shadowRoot.getElementById('fast_threshold');threshold.value=4;threshold.oninput();p.update();assert.equal(threshold.value,4);
p.shadowRoot.getElementById('fast_immediate').checked=false;
p.shadowRoot.getElementById('save').onclick();await new Promise(r=>setTimeout(r,0));
assert.equal(sent.value.fast_threshold,4);assert.strictEqual(sent.value.fast_immediate,false);assert.strictEqual(sent.value.fast_enabled,true);assert.equal(sent.value.pause,15);
assert.equal(p.dirty,false);
assert.equal(p.shadowRoot.getElementById('regler-body').hidden,true);
assert.equal(p.shadowRoot.getElementById('compact-maximum').textContent,'43,5');
assert.equal(p.shadowRoot.getElementById('compact-output').textContent,'4,0');
assert(!p.shadowRoot.html.includes('id="menu"'));
p.shadowRoot.getElementById('fold').onclick();
assert.equal(p.shadowRoot.getElementById('regler-body').hidden,false);
assert.equal(p.shadowRoot.getElementById('fold').attributes['aria-expanded'],'true');
threshold.value=4.5;threshold.oninput();
p.shadowRoot.getElementById('fold').onclick();p.update();
assert.equal(p.shadowRoot.getElementById('regler-body').hidden,true);
assert.equal(threshold.value,4.5);
p.shadowRoot.getElementById('auto_compact').onchange();await new Promise(r=>setTimeout(r,0));
assert.equal(sent.action,'enable');assert.strictEqual(sent.value,true);
assert.equal(p.shadowRoot.getElementById('auto_compact').checked,true);
assert.equal(p.shadowRoot.getElementById('regler-body').hidden,true);

console.log('UI behavior OK: fields, checkbox values, unsaved edits, settings command. Fold, compact readings, switch and unsaved settings OK. Visual rendering not tested.');
})().catch(e=>{console.error(e);process.exit(1)});

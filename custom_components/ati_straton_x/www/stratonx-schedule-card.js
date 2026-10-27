/* ATI Straton X schedule / live card 0.6.0, no external dependencies. */
export const CHANNELS = [
  ["UV / Violet", "#c43ce3"], ["Royal blue", "#386bff"], ["Blue", "#00a7ef"],
  ["Cyan / Horti white", "#00b8b9"], ["White", "#9ba6b6"], ["Red", "#ef5555"],
];

export const DEFAULT_PRESETS = [{name:"Blue photo", duration_minutes:10, channels:[0,100,100,0,0,0]}];
export function validPresets(presets) {
  if(!Array.isArray(presets)||presets.length>20)return false;
  const names=new Set();
  return presets.every(p=>{
    if(!p || typeof p.name!=="string" || !p.name.trim() || p.name.length>60 ||
      names.has(p.name.trim().toLowerCase()) || !Number.isInteger(p.duration_minutes) ||
      p.duration_minutes<1 || p.duration_minutes>60 || !Array.isArray(p.channels) ||
      p.channels.length!==6 || !p.channels.every(v=>Number.isFinite(v)&&v>=0&&v<=100))return false;
    names.add(p.name.trim().toLowerCase());return true;
  });
}
const presetsFor = config => config.presets ?? DEFAULT_PRESETS;

const escape = value => String(value ?? "").replace(/[&<>"']/g, c =>
  ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const good = s => s && !["unknown", "unavailable"].includes(s.state);
export function validNodes(nodes) {
  let last = -1;
  return Array.isArray(nodes) && nodes.length >= 2 && nodes.length <= 128 &&
    nodes.every(n => {
      if (!n || !Number.isInteger(n.timestamp) || n.timestamp <= last || n.timestamp >= 86400 ||
          !Array.isArray(n.channelValues) || n.channelValues.length !== 6 ||
          !n.channelValues.every(v => Number.isInteger(v) && v >= 0 && v <= 1023)) return false;
      last = n.timestamp;
      return true;
    });
}
export function atTime(nodes, second) {
  if (!validNodes(nodes) || !Number.isFinite(second) || second < 0 || second > 86400) return null;
  const exact = nodes.find(n => n.timestamp === second);
  if (exact) return exact.channelValues.map(v => v * 100 / 1023);
  if (second < nodes[0].timestamp || second > nodes.at(-1).timestamp)
    return [...nodes[0].channelValues, ...nodes.at(-1).channelValues].every(v => v === 0) ? Array(6).fill(0) : null;
  const end = nodes.findIndex(n => n.timestamp > second);
  const a = nodes[end-1], b = nodes[end], f = (second-a.timestamp)/(b.timestamp-a.timestamp);
  return a.channelValues.map((v, i) => (v+(b.channelValues[i]-v)*f)*100/1023);
}
export function clockSeconds(value) {
  const m = /^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2}):(\d{2})$/.exec(value || "");
  if (!m) return null;
  const [,y,mo,d,h,mi,s] = m.map(Number);
  const date = new Date(Date.UTC(y,mo-1,d,h,mi,s));
  if (date.getUTCFullYear() !== y || date.getUTCMonth() !== mo-1 || date.getUTCDate() !== d ||
      h > 23 || mi > 59 || s > 59) return null;
  return h*3600+mi*60+s;
}
const timeLabel = s => s === null ? "Unknown" : String(Math.floor(s/3600)).padStart(2,"0")+":"+String(Math.floor(s%3600/60)).padStart(2,"0");

class StratonXScheduleCard extends HTMLElement {
  constructor() {
    super(); this.attachShadow({mode:"open"}); this.hiddenChannels = new Set();
    this.tab="schedule"; this.draft=Array(6).fill(0); this.duration=10; this.draftReady=false; this.busy=false; this.feedback="";
  }
  static getStubConfig(hass) {
    return {entity: Object.keys(hass.states).find(k => Array.isArray(hass.states[k].attributes.nodes)) || ""};
  }
  static getConfigElement() { return document.createElement("stratonx-schedule-card-editor"); }
  setConfig(config) {
    if (!(typeof config.entity === "string" && config.entity.startsWith("sensor.")) &&
        !(Number.isInteger(config.tank_id) && config.tank_id > 0 && config.tank_id < 65535))
      throw new Error("Select a Schedule points sensor or enter an ATI tank ID.");
    if (this.config && this.config.tank_id !== config.tank_id) { this.draftReady=false; this.feedback=""; }
    if(config.presets !== undefined && !validPresets(config.presets)) throw new Error("Presets need unique names, six percentages (0–100), and a duration of 1–60 minutes; maximum 20.");
    this.config = {...config}; this.selection = null; this.render();
  }
  set hass(hass) { this._hass = hass; if (!this.shadowRoot.activeElement?.matches(".live-slider, .duration")) this.render(); }
  getCardSize() { return 8; }
  getGridOptions() { return {columns:12, rows:"auto", min_columns:6}; }
  companions(schedule) {
    const states = this._hass.states, serial = schedule?.attributes.serial;
    const find = predicate => serial ? Object.values(states).find(s => s.attributes.serial === serial && predicate(s)) : null;
    return {
      clock: this.config.time_entity ? states[this.config.time_entity] :
        find(s => s.attributes.time_basis === "Light's configured local time; snapshot at last poll"),
      timer: this.config.live_entity ? states[this.config.live_entity] :
        find(s => String(s.attributes.description || "").startsWith("Device override timer snapshot")),
    };
  }

  async publishPresets() {
    if(this.busy || !this.config.tank_id)return;
    const presets=presetsFor(this.config);
    if(!presets.length){this.feedback="Add named presets in the card editor first.";this.render();return;}
    this.busy=true;this.feedback="Publishing presets…";this.render();
    try {
      await this._hass.callService("ati_straton_x","publish_presets",{tank_id:this.config.tank_id,presets:JSON.parse(JSON.stringify(presets))});
      this.feedback="Published for automations. Call ati_straton_x.activate_preset with this tank ID and preset name. Publish again after editing.";
    } catch(error) {this.feedback="Publish failed: "+(error?.message||String(error));}
    finally{this.busy=false;this.render();}
  }
  wifiFallback() {
    return Object.values(this._hass.states).some(s => s.attributes.tank_id === this.config.tank_id && s.attributes.transport === "wifi");
  }
  async sendLive(resume=false) {
    if(this.busy || !this.config.tank_id || (!resume && (!this.draftReady || this.wifiFallback()))) return;
    const tank=this.config.tank_id;
    if(!resume && (!Number.isInteger(this.duration)||this.duration<1||this.duration>60 ||
      !this.draft.every(v=>Number.isFinite(v)&&v>=0&&v<=100))) {
      this.feedback="Choose valid percentages and a duration of 1–60 minutes."; this.render(); return;
    }
    const data={tank_id:tank};
    if(!resume) {
      data.duration_minutes=this.duration;
      ["uv_violet","royal_blue","blue","horti_white","white","red"].forEach((key,i)=>data[key]=this.draft[i]);
    }
    this.busy=true; this.feedback="Sending to tank "+tank+"…";this.render();
    try {
      await this._hass.callService("ati_straton_x",resume?"resume_tank_schedule":"set_tank_live",data);
      this.feedback=resume?"Schedule resume confirmed by timers.":"Live timer confirmed. Requested levels sent; actual output is not measured.";
    } catch(error) {
      this.feedback="Action failed: "+(error?.message || String(error))+" Check group timers before retrying.";
    } finally {this.busy=false;this.render();}
  }
  livePanel(members) {
    const tank=this.config.tank_id, disabled=this.busy?" disabled":"";
    const timers=members.map(s=>{
      const timer=this.companions(s).timer;
      const value=good(timer)&&/^\d+$/.test(timer.state)?Number(timer.state):null;
      return '<li>'+escape(s.attributes.friendly_name?.replace(/ Schedule points$/, "")||s.attributes.serial)+
        ': '+(value===null?"Unknown":value===0?"Scheduled mode":Math.ceil(value/60)+" min remaining")+'</li>';
    }).join("");
    return '<div class="live-panel"><p class="notice">Temporary mix for '+(tank?'all lights in ATI tank '+escape(tank):'a tank group')+'. The saved schedule resumes when the timer ends.</p>'+
      (!tank?'<p>Set a Tank ID in this card’s configuration to enable group controls.</p>':'')+
      (this.wifiFallback()?'<p class="notice">Wi-Fi telemetry fallback active. Apply requires Bluetooth recovery. Resume can still attempt Bluetooth.</p>':'')+
      '<div class="presets">'+presetsFor(this.config).map((p,i)=>'<button data-named="'+i+'"'+disabled+'>'+escape(p.name)+'</button>').join("")+'<button data-preset="schedule"'+disabled+'>Copy schedule estimate</button><button data-preset="off"'+disabled+'>Temporary off</button></div>'+
      '<button class="publish"'+(this.busy||!tank?' disabled':'')+'>Publish presets to automations</button><p class="foot">Publishing saves the named card presets, not unsaved slider adjustments. Matching names in this tank are updated; lights do not change.</p>'+
      '<p class="foot">Presets fill the sliders and duration; press Apply to send. Edit named presets in the dashboard card editor.</p>'+
      CHANNELS.map(([name,color],i)=>'<label class="live-channel"><span>'+name+'</span><output id="level-'+i+'">'+this.draft[i]+'%</output><input class="live-slider" data-channel="'+i+'" type="range" min="0" max="100" step="1" value="'+this.draft[i]+'" style="accent-color:'+color+'" aria-label="'+name+' requested percentage"'+disabled+'></label>').join("")+
      '<label class="duration-label">Duration (minutes)<input class="duration" type="number" min="1" max="60" step="1" value="'+this.duration+'"'+disabled+'></label>'+
      '<div class="actions"><button class="apply"'+(this.busy||!tank||!this.draftReady||this.wifiFallback()?' disabled':'')+'>'+(this.busy?'Working…':'Apply to tank')+'</button><button class="resume"'+(this.busy||!tank?' disabled':'')+'>Resume schedule</button></div>'+
      '<p class="feedback" role="status">'+escape(this.feedback||'Requested levels — not measured output. Sliders do not change lights until Apply.')+'</p>'+
      '<details open><summary>Group timers · last poll</summary><ul>'+(timers||'<li>No configured group members available</li>')+'</ul></details></div>';
  }
  bindLive(members) {
    this.shadowRoot.querySelector(".publish").onclick=()=>this.publishPresets();
    this.shadowRoot.querySelectorAll("[data-named]").forEach(button=>button.onclick=()=>{
      const preset=presetsFor(this.config)[Number(button.dataset.named)];
      this.draft=[...preset.channels];this.duration=preset.duration_minutes;this.draftReady=true;
      this.feedback=preset.name+" loaded. Press Apply to send to the tank.";this.render();
    });
    this.shadowRoot.querySelectorAll(".live-slider").forEach(input=>{
      input.oninput=()=>{this.draft[Number(input.dataset.channel)]=Number(input.value);this.draftReady=true;
        this.shadowRoot.getElementById("level-"+input.dataset.channel).textContent=input.value+"%";
        this.shadowRoot.querySelector(".apply").disabled=this.busy||!this.config.tank_id||this.wifiFallback();};
    });
    this.shadowRoot.querySelector(".duration").oninput=e=>{this.duration=Number(e.target.value);};
    this.shadowRoot.querySelectorAll("[data-preset]").forEach(button=>button.onclick=()=>{
      if(button.dataset.preset==="schedule"){
        const member=members.find(s=>s.entity_id===this.activeEntity)||members[0];
        const clock=this.companions(member).clock;
        const time=good(clock)?clockSeconds(clock.state):null;
        const values=time===null?null:atTime(member?.attributes.nodes,time);
        if(!good(member)||!values){this.feedback="Schedule estimate unavailable. Refresh schedule and clock first.";this.render();return;}
        this.draft=values.map(Math.round);
      } else this.draft=Array(6).fill(0);
      this.draftReady=true;this.feedback="Draft prepared. Press Apply to send to the tank.";this.render();
    });
    this.shadowRoot.querySelector(".apply").onclick=()=>this.sendLive();
    this.shadowRoot.querySelector(".resume").onclick=()=>this.sendLive(true);
  }
  render() {
    if (!this.config || !this._hass) return;
    const members = this.config.tank_id ? Object.values(this._hass.states).filter(s =>
      s.attributes.tank_id === this.config.tank_id && Array.isArray(s.attributes.nodes)) : [];
    const selectedMember = members.find(s => s.entity_id === this.activeEntity) || members[0];
    const schedule = this.config.tank_id ? selectedMember : this._hass.states[this.config.entity];
    const nodes = schedule?.attributes.nodes;
    const matching = members.length > 0 && members.every(s => validNodes(s.attributes.nodes) && JSON.stringify(s.attributes.nodes) === JSON.stringify(nodes));
    const memberTimers = members.map(s => this.companions(s).timer);
    const anyOverride = memberTimers.some(t => good(t) && Number(t.state) > 0);
    const groupUnknown = members.some(s => !good(s)) || memberTimers.some(t => !good(t) || !/^\d+$/.test(t.state));

    const valid = validNodes(nodes), available = good(schedule);
    const {clock, timer} = this.companions(schedule);
    const now = good(clock) ? clockSeconds(clock.state) : null;
    const remaining = good(timer) && /^\d+$/.test(timer.state) ? Number(timer.state) : null;
    const live = (remaining !== null && remaining > 0) || anyOverride;
    const inspected = this.selection !== null;
    const selected = inspected ? this.selection : now;
    const values = valid && selected !== null && (inspected || (available && remaining === 0 && !live && !groupUnknown)) ? atTime(nodes, selected) : null;
    const title = this.config.title || (this.config.tank_id ? "Tank " + this.config.tank_id : schedule?.attributes.friendly_name?.replace(/ Schedule points$/, "")) || "Straton X";
    let notice = !available ? "Light unavailable — saved schedule only." :
      live ? (members.length ? "Live override active on a group member. Current estimates hidden; saved schedule shown." : "Live override active · "+Math.ceil(remaining/60)+" min remaining at last poll. Curves show the saved schedule.") :
      (remaining === null || groupUnknown) ? "A light or live-mode status is unknown — current estimates hidden." :
      now === null ? "Light clock unknown — current estimates hidden." : "Scheduled mode · estimates at the last light-clock reading";
    if (!valid) notice = "No valid schedule. Select a Schedule points sensor and refresh its schedule.";
    const x = s => 44+s/86400*572, y = v => 212-v/1023*176;
    let grid = [0,25,50,75,100].map(v => '<line x1="44" x2="616" y1="'+(212-v*1.76)+'" y2="'+(212-v*1.76)+'"/><text x="35" y="'+(216-v*1.76)+'" text-anchor="end">'+v+'</text>').join("");
    grid += [0,4,8,12,16,20,24].map(h => '<line x1="'+x(h*3600)+'" x2="'+x(h*3600)+'" y1="36" y2="212"/><text x="'+x(h*3600)+'" y="237" text-anchor="middle">'+String(h).padStart(2,"0")+':00</text>').join("");
    let curves = "";
    if (valid) {
      const plot = nodes.map(n => ({...n}));
      if ([...nodes[0].channelValues,...nodes.at(-1).channelValues].every(v => v===0)) {
        if (plot[0].timestamp>0) plot.unshift({timestamp:0,channelValues:Array(6).fill(0)});
        plot.push({timestamp:86400,channelValues:Array(6).fill(0)});
      }
      curves = CHANNELS.map(([name,color], i) => {
        if (this.hiddenChannels.has(i)) return "";
        const points = plot.map(n=>x(n.timestamp).toFixed(2)+","+y(n.channelValues[i]).toFixed(2)).join(" ");
        return '<polyline data-channel="'+i+'" points="'+points+'" fill="none" stroke="'+color+'" stroke-width="2.5" stroke-linejoin="round"/>'+
          nodes.map(n=>'<circle cx="'+x(n.timestamp)+'" cy="'+y(n.channelValues[i])+'" r="2.5" fill="'+color+'"/>').join("");
      }).join("");
    }
    const marker = now !== null ? '<line class="now" x1="'+x(now)+'" x2="'+x(now)+'" y1="28" y2="212"/><text class="now-label" x="'+Math.min(570,Math.max(90,x(now)))+'" y="18" text-anchor="middle">Light time '+timeLabel(now)+'</text>' : "";
    const cursor = inspected ? '<line class="cursor" x1="'+x(selected)+'" x2="'+x(selected)+'" y1="36" y2="212"/>' : "";
    this.shadowRoot.innerHTML = `<style>
      :host{display:block}ha-card{display:block;overflow:hidden;background:var(--ha-card-background,var(--card-background-color,#fff));color:var(--primary-text-color,#182435);border-radius:var(--ha-card-border-radius,18px)}
      .tabs{display:flex;gap:8px;margin:14px 0}.tabs button,.presets button,.actions button,.publish{border:1px solid var(--divider-color,#dbe1e9);border-radius:9px;padding:10px;background:transparent}.tabs button[aria-selected=true],.apply{background:var(--primary-color,#008db5)!important;color:var(--text-primary-color,#fff)}button:disabled{opacity:.45;cursor:default}.presets,.actions{display:flex;gap:8px;flex-wrap:wrap}.live-channel{display:grid;grid-template-columns:1fr auto;gap:5px;margin:18px 0;font-size:14px}.live-channel input{grid-column:1/-1}.live-channel output{font-weight:700}.duration-label{display:flex;justify-content:space-between;align-items:center;margin:20px 0;font-size:14px}.duration{width:70px;padding:8px;border:1px solid var(--divider-color,#aaa);border-radius:6px;background:transparent;color:inherit}.feedback,details{font-size:12px;line-height:1.6}.feedback{min-height:38px}
      .wrap{padding:20px}header{display:flex;justify-content:space-between;gap:12px;align-items:center}h2{margin:4px 0;font-size:20px;font-weight:650}.eyebrow{font-size:10px;font-weight:700;letter-spacing:1.8px;color:var(--secondary-text-color,#66768b)}
      .pill{padding:6px 10px;border:1px solid var(--divider-color,#dbe1e9);border-radius:20px;font-size:11px;white-space:nowrap}
      .group-info{font-size:12px;margin-top:12px;color:var(--secondary-text-color,#66768b)}.group-info label{display:block;margin-top:8px}.member{max-width:100%;padding:5px;color:inherit;background:var(--card-background-color,#fff);border:1px solid var(--divider-color,#dbe1e9);border-radius:5px}.notice{font-size:12px;line-height:1.6;color:var(--secondary-text-color,#66768b);min-height:38px;margin:12px 0 4px}
      svg{width:100%;display:block;overflow:visible}.grid line{stroke:var(--divider-color,#dbe1e9);stroke-width:.7}.grid text{fill:var(--secondary-text-color,#66768b);font-size:12px}
      .now{stroke:var(--primary-text-color,#182435);stroke-dasharray:4 4}.now-label{fill:var(--primary-text-color,#182435);font-size:12px;font-weight:600}.cursor{stroke:var(--secondary-text-color,#66768b)}
      .readout{display:flex;align-items:center;justify-content:space-between;margin-top:10px;font-size:12px;gap:8px}.readout strong{font-weight:650}
      button{font:inherit;color:inherit;cursor:pointer}.reset{border:0;background:transparent;color:var(--primary-color,#008db5);padding:8px}
      .channels{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px;margin-top:10px}
      .channel{background:transparent;border:1px solid var(--divider-color,#dbe1e9);border-radius:10px;display:flex;align-items:center;gap:8px;padding:11px 10px;text-align:left;min-width:0}
      .channel[aria-pressed=false]{opacity:.45}.swatch{width:9px;height:9px;border-radius:50%;flex-shrink:0}.name{font-size:12px;flex:1}.value{font-size:15px;font-weight:700;font-variant-numeric:tabular-nums}
      .foot{font-size:11px;line-height:1.5;color:var(--secondary-text-color,#66768b);margin:14px 0 0}
      input[type=range]{width:100%;margin:8px 0 0;accent-color:var(--primary-color,#008db5)}
      button:focus-visible,input:focus-visible{outline:2px solid var(--primary-color,#008db5);outline-offset:2px}
      @media(max-width:380px){.wrap{padding:14px}.channel{padding:10px 7px;gap:6px}.name{font-size:11px}}
      </style><ha-card><div class="wrap">
      <header><div><div class="eyebrow">${this.tab==="live"?"LIVE MODE":"LIGHT SCHEDULE"}</div><h2>${escape(title)}</h2></div><span class="pill">${this.tab==="live"?"TIMED OVERRIDE":"24 HOURS"}</span></header>
      <div class="tabs"><button data-tab="schedule" aria-selected="${this.tab==="schedule"}">Schedule</button><button data-tab="live" aria-selected="${this.tab==="live"}">Live mode</button></div>
      ${this.tab==="live" ? this.livePanel(members) : `
      ${this.config.tank_id ? `<div class="group-info">${members.length} configured lights · ${matching ? "saved schedules match" : "schedules differ or are unavailable"}<label>Schedule / clock shown: <select class="member">${members.map(s=>`<option value="${escape(s.entity_id)}" ${s===schedule?"selected":""}>${escape(s.attributes.friendly_name?.replace(/ Schedule points$/, "") || s.attributes.serial)}</option>`).join("")}</select></label></div>` : ""}
      <div class="notice" role="status">${escape(notice)}</div>
      <svg viewBox="0 0 640 250" role="img" aria-label="Saved lighting schedule, six channel percentages over 24 hours">
        <g class="grid">${grid}</g><g>${curves}</g>${marker}${cursor}
      </svg>
      <div class="readout"><strong>${inspected ? "Schedule at " : "Estimated at light time "}${timeLabel(selected)}</strong><button class="reset" type="button">Use light time</button></div>
      <input type="range" min="0" max="1440" step="1" value="${Math.floor((selected ?? 43200)/60)}" aria-label="Inspect saved schedule time" ${valid?"":"disabled"}>
      <div class="channels">${CHANNELS.map(([name,color],i)=>`<button class="channel" type="button" data-index="${i}" aria-pressed="${!this.hiddenChannels.has(i)}" aria-label="Toggle ${name} curve"><span class="swatch" style="background:${color}"></span><span class="name">${name}</span><span class="value">${values ? values[i].toFixed(1)+"%" : "—"}</span></button>`).join("")}</div>
      <p class="foot">Saved schedule · not live output. Tap a channel to hide its curve. Moonlight, acclimation and day-length adjustments are not included.</p>
      `}
      </div></ha-card>`;
    this.shadowRoot.querySelectorAll("[data-tab]").forEach(button=>button.onclick=()=>{this.tab=button.dataset.tab;this.render();});
    if(this.tab==="live"){this.bindLive(members);return;}
    const picker = this.shadowRoot.querySelector(".member");
    if (picker) picker.onchange = event => {this.activeEntity=event.target.value;this.selection=null;this.render();};
    this.shadowRoot.querySelector(".reset").onclick = () => {this.selection=null;this.render();};
    this.shadowRoot.querySelectorAll(".channel").forEach(button => button.onclick=()=>{
      const i=Number(button.dataset.index); this.hiddenChannels.has(i)?this.hiddenChannels.delete(i):this.hiddenChannels.add(i);
      this.render();this.shadowRoot.querySelector('[data-index="'+i+'"]').focus();
    });
    // Keep the range element alive during drag, then render on release/change.
    this.shadowRoot.querySelector("input").onchange = event => {
      this.selection=Number(event.target.value)*60;this.render();this.shadowRoot.querySelector("input").focus();
    };
  }
}
class StratonXScheduleEditor extends HTMLElement {

  savePresets(presets) {
    this.config={...this.config,presets};
    this.dispatchEvent(new CustomEvent("config-changed",{detail:{config:this.config},bubbles:true,composed:true}));
  }
  presetEditor() {
    const presets=JSON.parse(JSON.stringify(presetsFor(this.config)));
    const section=document.createElement("section");section.className="preset-editor";
    const heading=document.createElement("h3");heading.textContent="Named live presets";section.append(heading);
    const note=document.createElement("p");note.textContent="Saved with this card for all users. Channel order: UV / Violet, Royal blue, Blue, Cyan / Horti white, White, Red. Save the dashboard after editing.";section.append(note);
    presets.forEach((preset,index)=>{
      const box=document.createElement("fieldset");box.dataset.presetIndex=index;
      const legend=document.createElement("legend");legend.textContent="Preset "+(index+1);box.append(legend);
      const fields=[["name","Name",preset.name],["duration_minutes","Duration (minutes)",preset.duration_minutes],...CHANNELS.map(([label],i)=>["channel"+i,label+" (%)",preset.channels[i]])];
      fields.forEach(([key,label,value])=>{
        const wrap=document.createElement("label");wrap.textContent=label;
        const input=document.createElement("input");input.value=value;input.dataset.field=key;
        if(key==="name"){input.maxLength=60;input.required=true;}
        else{input.type="number";input.min=key==="duration_minutes"?"1":"0";input.max=key==="duration_minutes"?"60":"100";input.step=key==="duration_minutes"?"1":"any";input.required=true;}
        input.onchange=()=>{
          input.setCustomValidity("");
          if(!input.reportValidity())return;
          const next=JSON.parse(JSON.stringify(presetsFor(this.config)));
          if(key.startsWith("channel"))next[index].channels[Number(key.slice(7))]=Number(input.value);
          else next[index][key]=key==="name"?input.value.trim():Number(input.value);
          if(!validPresets(next)){input.setCustomValidity("Use a unique name and valid channel levels and duration.");input.reportValidity();return;}
          this.savePresets(next);
        };
        wrap.append(input);box.append(wrap);
      });
      const remove=document.createElement("button");remove.type="button";remove.className="remove-preset";remove.textContent="Delete preset";
      remove.onclick=()=>{const next=JSON.parse(JSON.stringify(presetsFor(this.config)));next.splice(index,1);this.savePresets(next);this.render();};
      box.append(remove);section.append(box);
    });
    const add=document.createElement("button");add.type="button";add.className="add-preset";add.textContent="Add preset";add.disabled=presets.length>=20;
    add.onclick=()=>{
      const next=JSON.parse(JSON.stringify(presetsFor(this.config)));let n=1;
      while(next.some(p=>p.name.trim().toLowerCase()==="preset "+n))n++;
      next.push({name:"Preset "+n,duration_minutes:10,channels:[0,0,0,0,0,0]});
      this.savePresets(next);this.render();
    };
    section.append(add);this.shadowRoot.append(section);
  }

  constructor(){super();this.attachShadow({mode:"open"});}
  setConfig(config){this.config={...config};this.render();}
  set hass(hass){this._hass=hass;if(!this.shadowRoot.activeElement)this.render();}
  render(){
    if(!this._hass||!this.config)return;
    this.shadowRoot.innerHTML='<style>label{display:block;margin:12px 0;font:inherit}fieldset{border:1px solid var(--divider-color,#aaa);border-radius:10px;margin:12px 0;padding:12px}button{padding:10px;cursor:pointer}.preset-editor p{font-size:13px}select,input{display:block;width:100%;box-sizing:border-box;padding:10px;margin-top:6px;background:var(--card-background-color,#fff);color:var(--primary-text-color,#182435);border:1px solid var(--divider-color,#aaa);border-radius:6px}</style>';
    for(const [key,label] of [["tank_id","Tank ID (group card; overrides single-light selection)"],["entity","Schedule points sensor (single light)"],["title","Title (optional)"],["time_entity","Light clock sensor (optional)"],["live_entity","Live mode timer sensor (optional)"]]){
      const wrap=document.createElement("label");wrap.textContent=label;
      const field=document.createElement(key==="entity"?"select":"input");
      if(key==="entity"){
        const blank=document.createElement("option");blank.value="";blank.textContent="Select a light";field.append(blank);
        for(const [id,state] of Object.entries(this._hass.states)){
          if(!Array.isArray(state.attributes.nodes)&&id!==this.config.entity)continue;
          const o=document.createElement("option");o.value=id;o.textContent=state.attributes.friendly_name||id;field.append(o);
        }
      }
      field.value=this.config[key]||"";
      field.onchange=()=>{const next={...this.config,[key]:key==="tank_id"?Number(field.value):field.value};if(!field.value)delete next[key];this.config=next;this.dispatchEvent(new CustomEvent("config-changed",{detail:{config:next},bubbles:true,composed:true}));};
      wrap.append(field);this.shadowRoot.append(wrap);
    }
    this.presetEditor();
  }
}
if(!customElements.get("stratonx-schedule-card"))customElements.define("stratonx-schedule-card",StratonXScheduleCard);
if(!customElements.get("stratonx-schedule-card-editor"))customElements.define("stratonx-schedule-card-editor",StratonXScheduleEditor);
window.customCards=window.customCards||[];
if(!window.customCards.some(c=>c.type==="stratonx-schedule-card"))window.customCards.push({type:"stratonx-schedule-card",name:"ATI Straton X Schedule",description:"Six-channel saved schedule with light-clock marker and live-override status.",preview:true});

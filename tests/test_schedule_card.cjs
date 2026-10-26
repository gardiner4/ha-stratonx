// Run with Playwright installed: node tests/test_schedule_card.cjs
const { chromium } = require("playwright");
const fs = require("node:fs");
const path = require("node:path");
const assert = require("node:assert/strict");
(async () => {
 const root = path.resolve(__dirname, "..");
 const source = fs.readFileSync(path.join(root,"custom_components/ati_straton_x/www/stratonx-schedule-card.js"),"utf8");
 const browser = await chromium.launch({headless:true, ...(process.env.CARD_BROWSER_CHANNEL ? {channel:process.env.CARD_BROWSER_CHANNEL}: {})});
 try {
  const page = await browser.newPage({viewport:{width:390,height:900}});
  const errors=[];page.on("pageerror",e=>errors.push(e.message));
  await page.route("http://card.test/**",route=>route.fulfill({
   contentType:route.request().url().endsWith(".js")?"text/javascript":"text/html",
   body:route.request().url().endsWith(".js")?source:'<html><head><style>body{margin:16px;background:#eef3f8;font-family:Arial}stratonx-schedule-card{display:block;max-width:760px;margin:auto}</style></head><body><script type="module">import * as api from "/card.js";window.api=api;window.ready=true;</script></body></html>'
  }));
  await page.goto("http://card.test/");
  await page.waitForFunction(()=>window.ready);
  await page.evaluate(()=>{
   const nodes=[{timestamp:28800,channelValues:[0,0,0,0,0,0]},
    {timestamp:38520,channelValues:[313,798,798,437,443,187]},
    {timestamp:69480,channelValues:[313,798,798,437,444,187]},
    {timestamp:79200,channelValues:[0,0,0,0,0,0]}];
   window.states={
    "sensor.renamed_schedule":{state:"4",attributes:{serial:"A",friendly_name:"Aquarium light Schedule points",nodes}},
    "sensor.renamed_clock":{state:"2026-10-26 14:55:00",attributes:{serial:"A",time_basis:"Light's configured local time; snapshot at last poll"}},
    "sensor.renamed_timer":{state:"0",attributes:{serial:"A",description:"Device override timer snapshot; zero means no timed override, not light off"}},
    "sensor.other_timer":{state:"600",attributes:{serial:"B",description:"Device override timer snapshot"}}
   };
   window.card=document.createElement("stratonx-schedule-card");
   card.setConfig({entity:"sensor.renamed_schedule"});card.hass={states};document.body.append(card);
  });
  assert.equal(await page.locator(".channel").count(),6);
  assert.match(await page.locator(".notice").innerText(),/Scheduled mode/);
  assert.equal(await page.locator(".value").nth(0).innerText(),"30.6%");
  assert.equal(await page.locator("polyline").count(),6);
  await page.locator(".channel").nth(0).click();
  assert.equal(await page.locator("polyline").count(),5);
  await page.locator(".channel").nth(0).click();
  await page.locator('input[type=range]').fill("480");
  await page.locator('input[type=range]').dispatchEvent("change");
  assert.match(await page.locator(".readout").innerText(),/Schedule at 08:00/);
  assert.equal(await page.locator(".value").nth(0).innerText(),"0.0%");
  await page.locator(".reset").click();
  await page.screenshot({path:path.join(root,"card-mobile.png"),fullPage:true});
  await page.setViewportSize({width:1000,height:900});
  await page.screenshot({path:path.join(root,"card-desktop.png"),fullPage:true});
  await page.evaluate(()=>{document.body.style.background="#101722";document.body.style.setProperty("--card-background-color","#192332");document.body.style.setProperty("--primary-text-color","#e7eef9");document.body.style.setProperty("--secondary-text-color","#aab9cd");document.body.style.setProperty("--divider-color","#344358");states["sensor.renamed_timer"].state="120";card.hass={states};});
  assert.match(await page.locator(".notice").innerText(),/Live override active/);
  assert.equal(await page.locator(".value").nth(0).innerText(),"—");
  assert.equal(await page.locator("polyline").count(),6);
  await page.screenshot({path:path.join(root,"card-dark-override.png"),fullPage:true});
  await page.evaluate(()=>{states["sensor.renamed_timer"].state="unknown";card.hass={states};});
  assert.match(await page.locator(".notice").innerText(),/status is unknown/);
  await page.evaluate(()=>{states["sensor.renamed_schedule"].state="unavailable";card.hass={states};});
  assert.match(await page.locator(".notice").innerText(),/unavailable/);
  await page.evaluate(()=>{card.setConfig({entity:"sensor.renamed_schedule",title:'<img src=x onerror="window.injected=true">'});});
  assert.equal(await page.locator("img").count(),0);
  const calculations=await page.evaluate(()=>({
   invalid:api.validNodes([{timestamp:1,channelValues:[0,0,0,0,0,0]},{timestamp:1,channelValues:[0,0,0,0,0,0]}]),
   invalidClock:api.clockSeconds("2000-00-00 00:00:00"),
   goodClock:api.clockSeconds("2026-10-26 14:55:00"),
   ramp:api.atTime([{timestamp:0,channelValues:[0,0,0,0,0,0]},{timestamp:7200,channelValues:[1023,1023,1023,1023,1023,1023]}],3600),
   outside:api.atTime([{timestamp:100,channelValues:[100,0,0,0,0,0]},{timestamp:7200,channelValues:[0,0,0,0,0,0]}],0)
  }));
  assert.deepEqual(calculations,{invalid:false,invalidClock:null,goodClock:53700,ramp:[50,50,50,50,50,50],outside:null});
  await page.evaluate(()=>{
   const editor=document.createElement("stratonx-schedule-card-editor");
   editor.setConfig({entity:"sensor.renamed_schedule"});editor.hass={states};
   editor.addEventListener("config-changed",event=>window.edited=event.detail.config);
   document.body.append(editor);
  });
  await page.locator("stratonx-schedule-card-editor input").nth(1).fill("My lighting");
  await page.locator("stratonx-schedule-card-editor input").nth(1).dispatchEvent("change");
  assert.equal(await page.evaluate(()=>window.edited.title),"My lighting");
  await page.evaluate(()=>{
   for(const [id,state] of Object.entries(states)) {state.entity_id=id;state.attributes.tank_id=42;}
   states["sensor.renamed_schedule"].state="4";
   states["sensor.renamed_timer"].state="0";
   states["sensor.second_schedule"]=JSON.parse(JSON.stringify(states["sensor.renamed_schedule"]));
   states["sensor.second_schedule"].entity_id="sensor.second_schedule";
   states["sensor.second_schedule"].attributes.serial="B";
   states["sensor.second_schedule"].attributes.friendly_name="Second light Schedule points";
   states["sensor.other_timer"].state="0";
   states["sensor.second_clock"]={...states["sensor.renamed_clock"],entity_id:"sensor.second_clock",attributes:{...states["sensor.renamed_clock"].attributes,serial:"B"}};
   card.setConfig({tank_id:42,title:"Aquarium lighting"});card.hass={states};
  });
  assert.match(await page.locator(".group-info").innerText(),/2 configured lights.*saved schedules match/);
  assert.equal(await page.locator(".member option").count(),2);
  await page.evaluate(()=>{states["sensor.second_schedule"].attributes.nodes[1].channelValues[0]=500;card.hass={states};});
  assert.match(await page.locator(".group-info").innerText(),/schedules differ/);
  await page.locator(".member").selectOption("sensor.second_schedule");
  assert.match(await page.locator(".value").nth(0).innerText(),/^[0-9]/);
  await page.evaluate(()=>{states["sensor.other_timer"].state="120";card.hass={states};});
  assert.match(await page.locator(".notice").innerText(),/group member/);
  assert.equal(await page.locator(".value").nth(0).innerText(),"—");
  await page.setViewportSize({width:390,height:900});
  await page.screenshot({path:path.join(root,"card-group-mobile.png"),fullPage:true});

  await page.evaluate(()=>{
    window.calls=[]; window.fail=false; window.hold=false;
    card.hass={states,callService:async(domain,service,data)=>{
      calls.push({domain,service,data});
      if(window.fail)throw new Error("Mock unavailable member");
      if(window.hold)await new Promise(resolve=>window.finishCall=resolve);
    }};
  });
  await page.locator('[data-tab="live"]').click();
  assert.equal(await page.locator(".live-slider").count(),6);
  assert.equal(await page.locator(".apply").isDisabled(),true);
  await page.locator('[data-preset="blue"]').click();
  assert.deepEqual(await page.evaluate(()=>card.draft),[0,100,100,0,0,0]);
  assert.equal(await page.evaluate(()=>calls.length),0);
  await page.locator(".live-slider").nth(0).fill("15");
  await page.locator(".duration").fill("12");
  await page.locator('[data-tab="schedule"]').click();
  await page.locator('[data-tab="live"]').click();
  assert.equal(await page.locator(".live-slider").nth(0).inputValue(),"15");
  await page.evaluate(()=>window.hold=true);
  await page.locator(".apply").click();
  assert.equal(await page.locator(".apply").isDisabled(),true);
  await page.evaluate(()=>card.sendLive());
  assert.equal(await page.evaluate(()=>calls.length),1);
  assert.deepEqual(await page.evaluate(()=>calls[0]),{domain:"ati_straton_x",service:"set_tank_live",data:{tank_id:42,duration_minutes:12,uv_violet:15,royal_blue:100,blue:100,horti_white:0,white:0,red:0}});
  await page.evaluate(()=>{window.hold=false;window.finishCall();});
  await page.waitForFunction(()=>!card.busy);
  await page.locator(".resume").click();
  assert.deepEqual(await page.evaluate(()=>calls[1]),{domain:"ati_straton_x",service:"resume_tank_schedule",data:{tank_id:42}});
  await page.locator(".duration").fill("61");
  await page.locator(".apply").click();
  assert.equal(await page.evaluate(()=>calls.length),2);
  assert.match(await page.locator(".feedback").innerText(),/1–60/);
  await page.locator(".duration").fill("10");
  await page.locator('[data-preset="off"]').click();
  assert.deepEqual(await page.evaluate(()=>card.draft),[0,0,0,0,0,0]);
  await page.evaluate(()=>window.fail=true);
  await page.locator(".apply").click();
  assert.match(await page.locator(".feedback").innerText(),/Action failed.*Mock unavailable/);
  await page.locator('[data-preset="schedule"]').click();
  assert.equal(await page.locator(".live-slider").nth(0).inputValue(),"40");
  await page.screenshot({path:path.join(root,"card-live-mobile.png"),fullPage:true});
  await page.evaluate(()=>card.setConfig({entity:"sensor.renamed_schedule"}));
  assert.equal(await page.locator(".apply").isDisabled(),true);
  assert.equal(await page.locator(".resume").isDisabled(),true);
  assert.deepEqual(errors,[]);
  console.log("PASS: rendering, six curves, interpolation, time inspection, toggles, override/unknown/unavailable states, renamed sensors, escaping and editor. Screenshots saved.");
 } finally { await browser.close(); }
})().catch(error=>{console.error(error);process.exitCode=1;});

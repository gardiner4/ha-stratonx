# ATI Straton X for Home Assistant

Monitor ATI Straton X lights through Bluetooth using Home Assistant's Bluetooth adapter or a connectable ESPHome Bluetooth proxy.

Experimental version 0.6.0. Tested with light firmware 1.4.0.2.

## Installation with HACS

1. Open **HACS** and select **Custom repositories** from the menu.
2. Add `https://github.com/gardiner4/ha-stratonx` with the type **Integration**.
3. Find **ATI Straton X** in HACS and download it.
4. Restart Home Assistant.

### Manual installation

Copy the `custom_components/ati_straton_x` folder into Home Assistant's `/config/custom_components/` folder, then restart Home Assistant.

## Add your lights

1. Make sure Home Assistant has a working Bluetooth adapter or connectable ESPHome Bluetooth proxy within range of the lights.
2. Open **Settings > Devices & services**.
3. Configure a discovered Straton X light, or choose **Add integration > ATI Straton X** and select a light.
4. Enter the light's passcode if prompted. The default is `0`.
5. Repeat for each light.

Each light appears as a separate device. Its tank ID is read automatically; manage tank membership in the ATI app.

## Available features

- Two light temperature sensors and a controller temperature sensor.
- Firmware and hardware versions, tank ID, and last successful update.
- The light's local date/time, hardware clock, and approximate clock offset from Home Assistant.
- **Identify light** button: briefly blinks the white channel on the selected light (firmware 1.4.0.2).
- Six **Estimated channel output** sensors calculated from the saved schedule and light clock.
- Saved lighting schedule, available in the schedule sensor's attributes.
- **Refresh schedule** button.
- **Live mode remaining** sensor for each light (seconds remaining at the last poll).
- Timed tank-group live mode with six adjustable channels, plus **Resume tank schedule**.
- **Sync clock** button for firmware 1.4.0.2. This sends the current UTC time; it does not verify the resulting clock reading.

## Temporary photo, maintenance, or off mode

1. Find the **Tank group** value on one of your lights.
2. Open **Developer tools > Actions** and select **ATI Straton X: Set tank live mode**.
3. Enter that tank ID, choose a duration of **1–60 minutes**, and set all six channel percentages.
4. Run the action. The lights automatically return to their saved schedule when their own timer expires, even if Home Assistant disconnects.

Use **ATI Straton X: Resume tank schedule** with the same tank ID to end live mode early. Set all six channels to zero for temporary off. Resuming follows the current schedule; it does not force the lights on during scheduled darkness.

To save a photo or maintenance preset, create a Home Assistant script containing the live-mode action with your chosen values. No channel levels are prescribed by this integration.

These actions affect the **entire ATI tank group**, including group members not added to Home Assistant. Configure tank membership in the ATI app first. They replace an existing temporary override without changing the saved schedule. Group control currently requires firmware 1.4.0.2; testing with separate physical tank groups is still pending.

The integration contacts each configured group member and verifies its timer; a single firmware broadcast can miss lights. Add every light to Home Assistant and keep its integration enabled. Timer readback does not confirm actual channel output or delivery to undiscovered members. If any member fails verification, the action reports an error and attempts to resume the schedule on the configured group; the device timer is the fallback for unreachable lights.

### Example: Blue Photo script

Create a new script under **Settings > Automations & scenes > Scripts**, open **Edit in YAML**, and paste the example below. Replace `12345` with your light's **Tank group** value before running it.

This example requests **Royal Blue at 100% and Blue at 100%**, with the other four channels at zero, for **10 minutes**. Adjust the levels and duration for your tank.

```yaml
alias: Blue Photo
description: Royal Blue and Blue for 10 minutes, then resume the saved schedule.
mode: single
sequence:
  - action: ati_straton_x.set_tank_live
    data:
      tank_id: 12345 # Replace with your ATI tank ID.
      duration_minutes: 10
      uv_violet: 0
      royal_blue: 100
      blue: 100
      horti_white: 0
      white: 0
      red: 0
```

Save the script and run it directly or add it to a dashboard button. The lights handle the timer, so the script needs no delay or restore step. Use **Resume tank schedule** with the same tank ID to finish early. This changes temporary lighting only; it does not edit the saved schedule.

## Schedule dashboard card

The bundled **ATI Straton X Schedule** card displays six colored channel curves across 24 hours, schedule points, and a marker at the light's last reported local time. Drag the time slider to inspect the saved levels at any time; select **Use light time** to return. Tap a channel to hide or show its curve.

The Schedule tab is read-only; the Live mode tab provides explicit timed group controls. During a live override it keeps the saved schedule visible and hides the current estimate. The slider can still inspect scheduled values, clearly labeled **Schedule at**. Missing clocks or timer states hide current estimates; unavailable lights show a notice. Moonlight, acclimation, and day-length adjustments are not included.

### Add the card

1. Update the integration to **0.6.0 or later** and restart Home Assistant.
2. Enable **Advanced mode** in your Home Assistant profile if Resources is not visible.
3. Open **Settings > Dashboards > Resources**, and add this URL as a **JavaScript module**:
   `/ati_straton_x/stratonx-schedule-card.js?v=0.6.0`
4. Reload your browser or Companion app, edit a dashboard, and add **ATI Straton X Schedule**.
5. Enter an ATI **Tank ID** for one card per group, or select a **Schedule points** sensor for a single-light card.

The card finds that fixture's clock and live timer by serial number, so renaming a light does not affect discovery. You can optionally select explicit clock and timer entity IDs in the editor.

Group mode discovers configured schedule sensors by their actual tank ID. It compares their saved nodes and reports whether they match. A selector lets you inspect each member's schedule and clock; it does not assume every light is synchronized. A live override or unknown timer on any discovered member hides the current estimate. Only lights added to Home Assistant are included.

Manual group card configuration:

```yaml
type: custom:stratonx-schedule-card
tank_id: 12345 # Replace with your ATI tank ID.
title: Aquarium lighting
```

For a single-light card, replace `tank_id` with `entity: sensor.your_light_schedule_points`. Optional configuration keys are `time_entity` and `live_entity`. The integration serves the JavaScript; there is no separate card repository or external chart library. Register the resource once. When updating the card, update its URL's version suffix and reload the frontend.

## Updates

Lights are polled every **60 seconds** by default. Change this to **30–300 seconds** in the integration's options.

Clock readings are snapshots taken during each poll. Positive clock offset means the hardware clock is ahead of Home Assistant; small offsets include Bluetooth delay and one-second clock resolution.

Schedules are read once at integration startup/reload, then only when you press **Refresh schedule**. A detected tank-group change also discards and reloads the cached schedule. After editing in the ATI app, finish the edit and press **Refresh schedule**; the graph and estimates otherwise keep using the cached program. If a schedule download fails, successful telemetry and the previous schedule are retained, and the schedule sensor records the error. Retry with the button; regular polls do not repeatedly retry the large download.

## Estimated channel output

Each light has six percentage sensors labeled **Estimated**: UV/Violet, Royal blue, Blue, Cyan/Horti white, White, and Red. Values use linear interpolation between saved schedule points and the light's own local-clock snapshot. They update during normal polling, with no additional Bluetooth requests.

These are **schedule estimates, not measured live output**. The daytime plateau matched the ATI app's Main Light values during testing; transitions still need comparison on a physical light. Do not compare these with the app's Total tab, which can show different values.

Estimates become **unknown** when a timed live override is active, its timer state is unknown, the clock is invalid, or the schedule cannot be interpreted. Failed polls make the entities unavailable. Estimates resume after a successful poll confirms the override has ended. Outside the schedule's time range, zero is estimated only if both boundary nodes are zero; other boundary cases remain unknown.

Moonlight, acclimation, and day-length adjustments are **not included or detected**. If you use those features, these sensors can differ from actual output. Sensor attributes include this limitation, the calculation status, the light-clock snapshot, and the schedule's last-read time. Schedule changes in the ATI app appear after **Refresh schedule** or an integration reload.

## Current limitations

Actual live channel output has not been decoded. Channel percentages entered for live mode are requested targets, not measured output. The displayed schedule contains saved channel settings. Schedule editing and permanent on/off control are not supported.

Other firmware versions have not been verified.

## Troubleshooting

If a light is missing or unavailable, check Bluetooth range and that the adapter or proxy supports active connections. A failed telemetry read caused by a Bluetooth or transport error gets one fresh connection attempt after a two-second pause. Identity and tank membership are checked again, and read requests use the configured passcode. If both attempts fail, entities become unavailable and recovery polls run after 30, 60, then at most 120 seconds; a successful poll restores the configured interval. Connection time and shared-proxy queueing add to these delays. Identity/format errors are not immediately retried. Identify, clock sync, and live-mode commands are never automatically replayed by this recovery mechanism.

To stop polling, disable the light's integration entry under **Settings > Devices & services**.


### Live mode tab

Open **Live mode** on a card configured with a Tank ID. Adjust six channel sliders and a duration of 1–60 minutes, then press **Apply to tank**. Moving sliders and choosing presets only prepares a draft; it does not send commands. The action affects the entire ATI tank group, potentially including lights not configured in Home Assistant.

- **Blue photo** prepares Royal blue and Blue at 100%, with the other channels at zero.
- **Copy schedule estimate** prepares the selected light's saved schedule levels at its last reported clock time. These are estimates, not live output.
- **Temporary off** prepares all channels at zero. Press Apply to start the timed blackout.
- **Resume schedule** ends the override; the lamp's saved program decides its output.

Group timers show snapshots from the last poll. Successful actions confirm timer state, not actual channel output. Slider drafts stay in the current card while switching tabs. Named presets are saved separately in the card configuration; they are not Home Assistant scenes. The existing group services require supported firmware and available configured members; failures are shown on the card. Single-light cards must be given an explicit Tank ID before group controls are enabled.

## Named live presets

Presets are saved in each dashboard card's configuration and shared across your Home Assistant browsers and phones. They do not modify the light's saved schedule.

### Create or edit a preset

1. Open the dashboard's **Edit dashboard** mode, then edit the **ATI Straton X Schedule** card.
2. Under **Named live presets**, edit **Blue photo**, or choose **Add preset**.
3. Enter a unique name, a duration of 1–60 minutes, and six channel percentages from 0–100.
4. Save the card and finish editing the dashboard.
5. Open **Live mode**, select the named preset, and press **Apply to tank**.

Selecting a preset loads its values without sending a command. You can adjust the loaded sliders for a one-time change; edit the card to permanently change a preset. **Delete preset** removes it from the card after you save. **Resume schedule** ends the override early.

Presets belong to the card, not the fixture firmware or a global preset library. Separate cards can have different presets, even for the same tank. An omitted `presets` option supplies the default Blue photo preset; `presets: []` removes all named presets. Up to 20 presets are supported. These are not native Home Assistant scenes; use the documented script/service example for automations or voice control.

### Example card: Photo and Maintenance

Register this JavaScript module in **Settings → Dashboards → Resources** after installing the integration:

```text
/ati_straton_x/stratonx-schedule-card.js?v=0.6.0
```

Then add a manual card with the following YAML. Replace `12345` with your ATI tank ID (shown in the integration's entity attributes). The Maintenance values below are an example mix; adjust them for your aquarium.

```yaml
type: custom:stratonx-schedule-card
title: Aquarium lighting
tank_id: 12345
presets:
  - name: Photo
    duration_minutes: 10
    channels: [0, 100, 100, 0, 0, 0]
  - name: Maintenance
    duration_minutes: 30
    channels: [0, 20, 20, 20, 20, 0]
```

Channel order is **UV / Violet, Royal blue, Blue, Cyan / Horti white, White, Red**. All six percentages are required. Each preset name must be unique within the card.

For a second tank, add another card with its own Tank ID and presets. Group commands affect all lights in the ATI tank group, potentially including lights not configured in Home Assistant. Supported firmware and group availability requirements still apply.

The card is bundled at [custom_components/ati_straton_x/www/stratonx-schedule-card.js](custom_components/ati_straton_x/www/stratonx-schedule-card.js); there is no separate frontend repository to install.

## Use presets in scripts, automations, and Alexa (0.5.0)

1. Save your named presets in the dashboard card editor.
2. Open **Live mode** and press **Publish presets to automations**. Publishing saves the named card definitions, not temporary slider edits, and does not change the lights.
3. In a script or automation, use **ATI Straton X: Activate published preset** with the Tank ID and preset name.

Published presets are stored in Home Assistant and survive restarts. They work with the dashboard closed. Names are case-insensitive within each tank. Publishing updates matching names and retains other published names. After changing a card preset, publish again; scripts then use the new levels and duration without edits. If different cards publish the same name for the same tank, the last publication wins.

### Script example

Create a script in **Settings → Automations & scenes → Scripts**, choose **Edit in YAML**, and use the following example. Replace `12345` with your Tank ID and `Photo` with a published name. A complete example is also in [examples/preset-script.yaml](examples/preset-script.yaml).

```yaml
alias: Aquarium photo mode
mode: single
sequence:
  - action: ati_straton_x.activate_preset
    data:
      tank_id: 12345
      name: Photo
```

The lamp's timer restores its saved schedule; no delay or restore step is needed in the script. Repeated runs after the previous call completes restart the preset timer. Existing firmware checks, group availability checks and timer verification apply. A missing/deleted preset fails rather than guessing a mix.

Expose the resulting script through your existing Home Assistant Alexa connection, then activate it by name or use it in an Alexa routine. Alexa configuration/discovery is separate from this integration. See the [official Alexa Smart Home documentation](https://www.home-assistant.io/integrations/alexa.smart_home/#script).

### Published preset management

- `ati_straton_x.publish_presets`: Tank ID and a list of `name`, `duration_minutes`, and six `channels`; saves without sending light commands.
- `ati_straton_x.activate_preset`: Tank ID and name; starts the saved timed mix.
- `ati_straton_x.list_presets`: Tank ID; returns the saved definitions as response data.
- `ati_straton_x.delete_preset`: Tank ID and name; removes the published copy without changing lights or the card. Removing/renaming a preset in the card does not delete the published copy; use this action for cleanup.

Published presets are included in Home Assistant configuration backups. Card presets and published presets are separate until you press Publish; editing a preset never silently changes an automation's behavior.


## Bluetooth diagnostics (0.5.1)

Each light has three diagnostic sensors:

- **Bluetooth signal**: advertisement RSSI in dBm (closer to zero is stronger).
- **Bluetooth reporting proxy**: name of the receiving adapter/proxy when Home Assistant can resolve it, otherwise its source identifier. The raw source is also an attribute.
- **Last Bluetooth advertisement**: timestamp of the last advertisement known to Home Assistant.

These use the shared connectable-scanner advertisement cache, checked every 30 seconds, and never open extra Bluetooth connections. Signal and source become unavailable after 180 seconds without a fresh advertisement. Last advertisement and last successful telemetry poll remain visible during an outage. Advertisement timestamps are refreshed while HA is running, not restored across restarts.

RSSI is not the proxy's Wi-Fi signal or a measurement of an active GATT connection. A light can advertise strongly yet reject a connection. Compare the source and timestamp when troubleshooting; switching receivers can change RSSI.

## Optional Wi-Fi fallback and address discovery (0.6.0)

Bluetooth remains the primary connection. If telemetry fails, an optional serial-verified HTTP connection can supply temperature, identity, tank group, and valid clock readings. The **Telemetry connection** diagnostic sensor shows `bluetooth` or `wifi`. Each telemetry entity also includes its transport and last-read timestamp.

1. Add the light through Bluetooth as usual.
2. Open **Settings → Devices & services → ATI Straton X**, then the light's **Configure** options.
3. Enter its bare **Wi-Fi IP address or hostname**. Alternatively, leave the address blank and enter **Scan subnet once**, such as `192.168.1.0/24`. Use your lights' actual network, which may differ from Home Assistant's network.
4. Submit. The integration only saves an address that returns the same fixture serial. A scan searches one private IPv4 subnet of /24 or smaller, with limited concurrency. It may take up to two minutes and can miss slow devices; enter the address manually if needed.
5. Clear both Wi-Fi fields and submit to disable fallback.

Scanning happens only when requested in options, never on every poll. There is no verified Bluetooth IP lookup or Straton mDNS discovery in this release. If DHCP changes the address, rerun the scan or update it; reserving an address in your router avoids this. A hostname can also track address changes.

Wi-Fi reads use `settings_get` (or `setting_get` on other versions), `temp_get`, `time_get`, and `schedule.json`. There are no HTTP settings, clock, firmware, or lighting writes. Firmware must expose these endpoints and Home Assistant must be able to reach them. Identity is checked on every fallback read; an address reused by another device is rejected. Passwords returned by the settings endpoint are discarded.

Schedules remain startup/manual only. A failed requested Bluetooth schedule read can use Wi-Fi; the schedule sensor records its source and read time. Failed downloads preserve an existing same-tank schedule.

Bluetooth is retried on subsequent polls, with recovery delays capped at 120 seconds. Wi-Fi success does not prove Bluetooth controls work: Identify and Sync clock are unavailable during fallback, and starting a group live mode requires Bluetooth telemetry for every configured member. Resume still makes a best-effort Bluetooth attempt.

The HTTP live-mode timer has not been verified. During Wi-Fi fallback its sensor and channel estimates are **unknown**, rather than reusing stale Bluetooth timer data. Invalid or unset clock dates are also unknown. The saved schedule graph remains available; live controls and estimates recover after a successful Bluetooth poll.

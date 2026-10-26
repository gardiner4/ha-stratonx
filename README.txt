# ATI Straton X for Home Assistant

Monitor ATI Straton X lights through Bluetooth using Home Assistant's Bluetooth adapter or a connectable ESPHome Bluetooth proxy.

Experimental version 0.4.0. Tested with light firmware 1.4.0.2.

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

The card is read-only. During a live override it keeps the saved schedule visible and hides the current estimate. The slider can still inspect scheduled values, clearly labeled **Schedule at**. Missing clocks or timer states hide current estimates; unavailable lights show a notice. Moonlight, acclimation, and day-length adjustments are not included.

### Add the card

1. Update the integration to **0.4.0 or later** and restart Home Assistant.
2. Enable **Advanced mode** in your Home Assistant profile if Resources is not visible.
3. Open **Settings > Dashboards > Resources**, and add this URL as a **JavaScript module**:
   `/ati_straton_x/stratonx-schedule-card.js?v=0.4.0`
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

Schedules refresh every **15 minutes**, or when you press **Refresh schedule**. After editing a schedule in the ATI app, finish the edit before refreshing it in Home Assistant.

## Estimated channel output

Each light has six percentage sensors labeled **Estimated**: UV/Violet, Royal blue, Blue, Cyan/Horti white, White, and Red. Values use linear interpolation between saved schedule points and the light's own local-clock snapshot. They update during normal polling, with no additional Bluetooth requests.

These are **schedule estimates, not measured live output**. The daytime plateau matched the ATI app's Main Light values during testing; transitions still need comparison on a physical light. Do not compare these with the app's Total tab, which can show different values.

Estimates become **unknown** when a timed live override is active, its timer state is unknown, the clock is invalid, or the schedule cannot be interpreted. Failed polls make the entities unavailable. Estimates resume after a successful poll confirms the override has ended. Outside the schedule's time range, zero is estimated only if both boundary nodes are zero; other boundary cases remain unknown.

Moonlight, acclimation, and day-length adjustments are **not included or detected**. If you use those features, these sensors can differ from actual output. Sensor attributes include this limitation, the calculation status, the light-clock snapshot, and the schedule's last-read time. Schedule changes in the ATI app appear after **Refresh schedule** or the next scheduled refresh.

## Current limitations

Actual live channel output has not been decoded. Channel percentages entered for live mode are requested targets, not measured output. The displayed schedule contains saved channel settings. Schedule editing and permanent on/off control are not supported.

Other firmware versions have not been verified.

## Troubleshooting

If a light is missing or unavailable, check Bluetooth range and that the adapter or proxy supports active connections. Failed polls retry automatically with increasing delays.

To stop polling, disable the light's integration entry under **Settings > Devices & services**.

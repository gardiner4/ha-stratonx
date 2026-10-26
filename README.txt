# ATI Straton X for Home Assistant

Monitor ATI Straton X lights through Bluetooth using Home Assistant's Bluetooth adapter or a connectable ESPHome Bluetooth proxy.

Experimental version 0.3.0. Tested with light firmware 1.4.0.2.

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

## Updates

Lights are polled every **60 seconds** by default. Change this to **30–300 seconds** in the integration's options.

Clock readings are snapshots taken during each poll. Positive clock offset means the hardware clock is ahead of Home Assistant; small offsets include Bluetooth delay and one-second clock resolution.

Schedules refresh every **15 minutes**, or when you press **Refresh schedule**. After editing a schedule in the ATI app, finish the edit before refreshing it in Home Assistant.

## Current limitations

Actual live channel output has not been decoded. Channel percentages entered for live mode are requested targets, not measured output. The displayed schedule contains saved channel settings. Schedule editing and permanent on/off control are not supported.

Other firmware versions have not been verified.

## Troubleshooting

If a light is missing or unavailable, check Bluetooth range and that the adapter or proxy supports active connections. Failed polls retry automatically with increasing delays.

To stop polling, disable the light's integration entry under **Settings > Devices & services**.

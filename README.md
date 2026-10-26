# ATI Straton X for Home Assistant

Monitor ATI Straton X lights through Bluetooth using Home Assistant's Bluetooth adapter or a connectable ESPHome Bluetooth proxy.

Experimental version 0.2.0. Tested with light firmware 1.4.0.2.

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
- **Sync clock** button for firmware 1.4.0.2. This sends the current UTC time; it does not verify the resulting clock reading.

## Updates

Lights are polled every **60 seconds** by default. Change this to **30–300 seconds** in the integration's options.

Clock readings are snapshots taken during each poll. Positive clock offset means the hardware clock is ahead of Home Assistant; small offsets include Bluetooth delay and one-second clock resolution.

Schedules refresh every **15 minutes**, or when you press **Refresh schedule**. After editing a schedule in the ATI app, finish the edit before refreshing it in Home Assistant.

## Current limitations

This version does not support on/off control, brightness changes, schedule editing, or live channel output. The displayed schedule contains saved channel settings, not current output.

Other firmware versions have not been verified.

## Troubleshooting

If a light is missing or unavailable, check Bluetooth range and that the adapter or proxy supports active connections. Failed polls retry automatically with increasing delays.

To stop polling, disable the light's integration entry under **Settings > Devices & services**.

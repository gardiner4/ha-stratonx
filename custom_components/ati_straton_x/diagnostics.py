"""Diagnostics omit passcodes and raw configuration."""
async def async_get_config_entry_diagnostics(hass, entry):
    coordinator = entry.runtime_data
    return {"data": coordinator.data, "poll_interval_seconds": coordinator.interval, "update_success": coordinator.last_update_success, "consecutive_failures": coordinator.failures}

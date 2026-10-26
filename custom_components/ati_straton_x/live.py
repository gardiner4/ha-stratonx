"""Bounded group overrides. Timer readback does not confirm channel output."""
import asyncio
from .protocol import header, live_timer_packet, live_channels_packet, live_remaining


async def apply_live(write, query, tank, passcode, seconds, channels=None):
    """Arm the device timer before changing targets; resume on partial failure."""
    timer = live_timer_packet(tank, seconds, passcode)
    if seconds and seconds < 10:
        raise ValueError("Live mode must last at least 10 seconds")
    output = live_channels_packet(tank, channels, passcode) if seconds else None
    getter = header(0xC2, tank, passcode, 0xB2)
    resume = live_timer_packet(tank, 0, passcode)
    attempted = False
    try:
        attempted = True
        await write(timer)
        remaining = live_remaining(await query(getter))
        if seconds:
            if not max(1, seconds - 8) <= remaining <= seconds:
                raise ValueError("Live timer did not confirm the requested duration")
            await write(output)
            remaining = live_remaining(await query(getter))
            if not 1 <= remaining <= seconds:
                raise ValueError("Live timer is not active after setting channels")
        elif remaining != 0:
            raise ValueError("Resume schedule did not clear the live timer")
        return remaining
    except (Exception, asyncio.CancelledError):
        if attempted:
            try:
                await write(resume)
            except Exception:
                # The already-armed device timer remains the fallback.
                pass
        raise

"""MCP server exposing Harvia Xenio WiFi sauna controls as tools."""

import os
import logging
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from mcp.server.fastmcp import FastMCP

from .harvia_api import HarviaClient

logging.basicConfig(level=logging.INFO)
_LOGGER = logging.getLogger(__name__)


@asynccontextmanager
async def _lifespan(server: FastMCP) -> AsyncIterator[dict]:
    """Create and tear down the HarviaClient for the server lifetime."""
    username = os.environ.get("HARVIA_USERNAME", "")
    password = os.environ.get("HARVIA_PASSWORD", "")
    if not username or not password:
        raise RuntimeError(
            "HARVIA_USERNAME and HARVIA_PASSWORD environment variables are required"
        )

    client = HarviaClient(username, password)
    try:
        await client.connect()
        yield {"client": client}
    finally:
        await client.close()


mcp = FastMCP("Harvia Sauna", lifespan=_lifespan)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _c_to_f(celsius: float) -> float:
    return round(celsius * 9 / 5 + 32, 1)


def _f_to_c(fahrenheit: float) -> float:
    return round((fahrenheit - 32) * 5 / 9)


async def _resolve_device_id(ctx, device_id: str | None) -> str:
    """If device_id is None, auto-resolve to the first device."""
    if device_id:
        return device_id
    client: HarviaClient = ctx.request_context.lifespan_context["client"]
    devices = await client.list_devices()
    if not devices:
        raise ValueError("No sauna devices found on this account")
    return devices[0]["deviceId"]


def _format_status(device: dict) -> dict:
    """Build a human-friendly status dict from raw device data."""
    status: dict = {
        "device_id": device.get("deviceId"),
        "name": device.get("displayName"),
        "power": "on" if device.get("active") or device.get("heatOn") else "off",
        "lights": "on" if device.get("light") else "off",
        "fan": "on" if device.get("fan") else "off",
        "steamer": "on" if device.get("steamEn") or device.get("steamOn") else "off",
    }

    target_c = device.get("targetTemp")
    if target_c is not None:
        status["target_temperature_f"] = _c_to_f(target_c)
        status["target_temperature_c"] = target_c

    current_c = device.get("temperature")
    if current_c is not None:
        status["current_temperature_f"] = _c_to_f(current_c)
        status["current_temperature_c"] = current_c

    humidity = device.get("humidity")
    if humidity is not None:
        status["humidity_pct"] = humidity

    target_rh = device.get("targetRh")
    if target_rh is not None:
        status["target_humidity_pct"] = target_rh

    remaining = device.get("remainingTime")
    if remaining is not None:
        status["remaining_time_min"] = remaining

    status_codes = device.get("statusCodes")
    if status_codes is not None:
        door_digit = int(str(status_codes)[1])
        status["door"] = "open" if door_digit == 9 else "closed"

    return status


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

@mcp.tool()
async def list_devices(ctx) -> list[dict]:
    """List all Harvia sauna devices on the account."""
    client: HarviaClient = ctx.request_context.lifespan_context["client"]
    try:
        devices = await client.list_devices()
        return [_format_status(d) for d in devices]
    except Exception as e:
        return [{"error": f"Failed to list devices: {e}"}]


@mcp.tool()
async def get_sauna_status(ctx, device_id: str | None = None) -> dict:
    """Get full sauna status (temperature, humidity, power, lights, etc.).

    Args:
        device_id: Device ID. Omit to use the first device.
    """
    client: HarviaClient = ctx.request_context.lifespan_context["client"]
    try:
        did = await _resolve_device_id(ctx, device_id)
        state = await client.get_device_state(did)
        latest = await client.get_latest_data(did)
        merged = {**state, **latest, "deviceId": did}
        return _format_status(merged)
    except Exception as e:
        return {"error": f"Failed to get status: {e}"}


@mcp.tool()
async def turn_sauna_on(ctx, device_id: str | None = None) -> dict:
    """Turn the sauna heater ON.

    Args:
        device_id: Device ID. Omit to use the first device.
    """
    client: HarviaClient = ctx.request_context.lifespan_context["client"]
    try:
        did = await _resolve_device_id(ctx, device_id)
        await client.send_state_change(did, {"active": 1})
        return {"status": "ok", "device_id": did, "power": "on"}
    except Exception as e:
        return {"error": f"Failed to turn sauna on: {e}"}


@mcp.tool()
async def turn_sauna_off(ctx, device_id: str | None = None) -> dict:
    """Turn the sauna heater OFF.

    Args:
        device_id: Device ID. Omit to use the first device.
    """
    client: HarviaClient = ctx.request_context.lifespan_context["client"]
    try:
        did = await _resolve_device_id(ctx, device_id)
        await client.send_state_change(did, {"active": 0})
        return {"status": "ok", "device_id": did, "power": "off"}
    except Exception as e:
        return {"error": f"Failed to turn sauna off: {e}"}


@mcp.tool()
async def set_temperature(ctx, temperature: float, device_id: str | None = None) -> dict:
    """Set the target sauna temperature.

    Args:
        temperature: Target temperature in Fahrenheit (104-230°F).
        device_id: Device ID. Omit to use the first device.
    """
    client: HarviaClient = ctx.request_context.lifespan_context["client"]
    try:
        if temperature < 104 or temperature > 230:
            return {"error": "Temperature must be between 104°F and 230°F (40-110°C)"}
        celsius = _f_to_c(temperature)
        did = await _resolve_device_id(ctx, device_id)
        await client.send_state_change(did, {"targetTemp": celsius})
        return {
            "status": "ok",
            "device_id": did,
            "target_temperature_f": temperature,
            "target_temperature_c": celsius,
        }
    except Exception as e:
        return {"error": f"Failed to set temperature: {e}"}


@mcp.tool()
async def toggle_lights(ctx, on: bool, device_id: str | None = None) -> dict:
    """Turn the sauna lights on or off.

    Args:
        on: True to turn lights on, False to turn off.
        device_id: Device ID. Omit to use the first device.
    """
    client: HarviaClient = ctx.request_context.lifespan_context["client"]
    try:
        did = await _resolve_device_id(ctx, device_id)
        await client.send_state_change(did, {"light": int(on)})
        return {"status": "ok", "device_id": did, "lights": "on" if on else "off"}
    except Exception as e:
        return {"error": f"Failed to toggle lights: {e}"}


@mcp.tool()
async def toggle_steamer(ctx, on: bool, device_id: str | None = None) -> dict:
    """Turn the sauna steamer on or off.

    Args:
        on: True to turn steamer on, False to turn off.
        device_id: Device ID. Omit to use the first device.
    """
    client: HarviaClient = ctx.request_context.lifespan_context["client"]
    try:
        did = await _resolve_device_id(ctx, device_id)
        await client.send_state_change(did, {"steamEn": int(on)})
        return {"status": "ok", "device_id": did, "steamer": "on" if on else "off"}
    except Exception as e:
        return {"error": f"Failed to toggle steamer: {e}"}


@mcp.tool()
async def toggle_fan(ctx, on: bool, device_id: str | None = None) -> dict:
    """Turn the sauna fan on or off.

    Args:
        on: True to turn fan on, False to turn off.
        device_id: Device ID. Omit to use the first device.
    """
    client: HarviaClient = ctx.request_context.lifespan_context["client"]
    try:
        did = await _resolve_device_id(ctx, device_id)
        await client.send_state_change(did, {"fan": int(on)})
        return {"status": "ok", "device_id": did, "fan": "on" if on else "off"}
    except Exception as e:
        return {"error": f"Failed to toggle fan: {e}"}


@mcp.tool()
async def set_humidity(ctx, humidity: int, device_id: str | None = None) -> dict:
    """Set the target humidity level.

    Args:
        humidity: Target relative humidity percentage (0-140%).
        device_id: Device ID. Omit to use the first device.
    """
    client: HarviaClient = ctx.request_context.lifespan_context["client"]
    try:
        if humidity < 0 or humidity > 140:
            return {"error": "Humidity must be between 0% and 140%"}
        did = await _resolve_device_id(ctx, device_id)
        await client.send_state_change(did, {"targetRh": humidity})
        return {"status": "ok", "device_id": did, "target_humidity_pct": humidity}
    except Exception as e:
        return {"error": f"Failed to set humidity: {e}"}

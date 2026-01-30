# Harvia Sauna MCP Server

MCP (Model Context Protocol) server for controlling Harvia Xenio WiFi sauna controllers through Claude Code. Uses the same backend API as the MyHarvia mobile app.

## Setup

1. Install the package:

```bash
pip install -e .
```

2. Register with Claude Code, providing your MyHarvia credentials:

```bash
claude mcp add harvia-sauna \
  -e HARVIA_USERNAME=you@example.com \
  -e HARVIA_PASSWORD=yourpass \
  -- python -m mcp_server
```

3. Restart Claude Code. Then you can use natural language:
   - "What's my sauna status?"
   - "Turn on the sauna"
   - "Set the temperature to 175"
   - "Turn on the lights"

## Available Tools

| Tool | Description | Parameters |
|------|-------------|------------|
| `list_devices` | List all sauna devices on the account | none |
| `get_sauna_status` | Full status (temp, humidity, power, lights, etc.) | `device_id?` |
| `turn_sauna_on` | Power on the heater | `device_id?` |
| `turn_sauna_off` | Power off the heater | `device_id?` |
| `set_temperature` | Set target temp in Fahrenheit (104-230) | `temperature`, `device_id?` |
| `toggle_lights` | Lights on/off | `on`, `device_id?` |
| `toggle_steamer` | Steamer on/off | `on`, `device_id?` |
| `toggle_fan` | Fan on/off | `on`, `device_id?` |
| `set_humidity` | Set target humidity (0-140%) | `humidity`, `device_id?` |

All tools with `device_id?` auto-resolve to the first device in single-device setups.

## Testing with MCP Inspector

```bash
npx @modelcontextprotocol/inspector python -m mcp_server
```

## Compatibility

Tested with the Harvia Xenio WiFi (CX001WIFI). Should work with any sauna controller compatible with the MyHarvia app.

## Credits

Based on the Home Assistant integration by Ruben Harms. Uses the unofficial MyHarvia API and is not associated with Harvia.

# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

MCP server for controlling Harvia Xenio WiFi sauna controllers through Claude Code. Uses the same backend API as the MyHarvia mobile app. All code lives under `mcp_server/`.

## Development Setup

Install in editable mode: `pip install -e .` from the project root.

Dependencies are declared in `pyproject.toml`: `mcp`, `aiohttp`, `boto3`, `pycognito`.

To test with MCP Inspector: `npx @modelcontextprotocol/inspector python -m mcp_server`

To register with Claude Code:
```bash
claude mcp add harvia-sauna -e HARVIA_USERNAME=you@example.com -e HARVIA_PASSWORD=yourpass -- python -m mcp_server
```

## Architecture

### Communication Stack

1. **AWS Cognito Authentication** (`harvia_api.py`) — User credentials are exchanged for JWT tokens via `pycognito`. Tokens auto-refresh before every API call via `check_token(renew=True)`.

2. **GraphQL over HTTPS** (`harvia_api.py`) — Device discovery (`getDeviceTree`), state queries (`getDeviceState`, `getLatestData`), and control mutations (`requestStateChange`) go through AppSync POST endpoints.

3. **MCP Tool Layer** (`server.py`) — `FastMCP` server with a lifespan context manager that creates/destroys the `HarviaClient`. Nine tools expose sauna controls. Credentials come from `HARVIA_USERNAME` and `HARVIA_PASSWORD` environment variables.

### File Structure

- **`mcp_server/harvia_api.py`** — `HarviaClient` class. Handles all authentication, endpoint discovery, token management, and GraphQL queries/mutations. Uses `aiohttp.ClientSession` for HTTP and `asyncio.to_thread()` for synchronous pycognito calls.

- **`mcp_server/server.py`** — `FastMCP` server definition with 9 tool functions. Lifespan context manager creates/destroys the API client. All temperature tools accept Fahrenheit and convert to Celsius internally (the Harvia API uses Celsius natively).

- **`mcp_server/__main__.py`** — Entry point: `python -m mcp_server`. Runs the MCP server over stdio transport.

### Key Implementation Details

- Temperature range: 104-230 degrees F (40-110 degrees C). All tools accept/display Fahrenheit; conversion happens internally.
- Humidity setpoint range: 0-140%.
- Door sensor state is derived from `statusCodes`: 2nd digit == 9 means door open.
- Polling model (no WebSockets): each tool call fetches fresh data on demand.
- Tools with optional `device_id` auto-resolve to the first device for single-device setups.
- Endpoint discovery: fetches from `https://prod.myharvia-cloud.net/{type}/endpoint` for users, device, events, and data.
- Region: `eu-west-1` (AWS Cognito).

"""Standalone Harvia Xenio WiFi API client (no Home Assistant dependency)."""

import asyncio
import json
import logging

import aiohttp
from pycognito import Cognito

REGION = "eu-west-1"

_LOGGER = logging.getLogger(__name__)


class HarviaClient:
    """Async client for the Harvia cloud API (MyHarvia backend)."""

    def __init__(self, username: str, password: str) -> None:
        self.username = username
        self.password = password
        self._session: aiohttp.ClientSession | None = None
        self._endpoints: dict | None = None
        self._cognito: Cognito | None = None
        self._token_data: dict | None = None

    # -- lifecycle -----------------------------------------------------------

    async def connect(self) -> None:
        """Create HTTP session, discover endpoints, and authenticate."""
        self._session = aiohttp.ClientSession()
        await self._fetch_endpoints()
        await self._authenticate()

    async def close(self) -> None:
        """Tear down the HTTP session."""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    # -- endpoint discovery --------------------------------------------------

    async def _fetch_endpoints(self) -> None:
        self._endpoints = {}
        for name in ("users", "device", "events", "data"):
            url = f"https://prod.myharvia-cloud.net/{name}/endpoint"
            async with self._session.get(url) as resp:
                self._endpoints[name] = await resp.json()

    # -- cognito auth --------------------------------------------------------

    async def _get_cognito(self) -> Cognito:
        if self._cognito is None:
            ep = self._endpoints["users"]
            user_pool_id = ep["userPoolId"]
            client_id = ep["clientId"]
            id_token = ep["identityPoolId"]
            self._cognito = await asyncio.to_thread(
                Cognito,
                user_pool_id,
                client_id,
                username=self.username,
                user_pool_region=REGION,
                id_token=id_token,
            )
        return self._cognito

    async def _authenticate(self) -> None:
        if self._token_data is not None:
            return
        client = await self._get_cognito()
        await asyncio.to_thread(client.authenticate, password=self.password)
        self._token_data = {
            "access_token": client.access_token,
            "refresh_token": client.refresh_token,
            "id_token": client.id_token,
        }

    async def _refresh_tokens(self) -> None:
        client = await self._get_cognito()
        await self._authenticate()
        await asyncio.to_thread(client.check_token, renew=True)
        self._token_data = {
            "access_token": client.access_token,
            "refresh_token": client.refresh_token,
            "id_token": client.id_token,
        }

    async def _id_token(self) -> str:
        await self._refresh_tokens()
        return self._token_data["id_token"]

    # -- low-level GraphQL ---------------------------------------------------

    async def _post(self, endpoint_key: str, query: dict) -> dict:
        """POST a GraphQL query/mutation to the specified AppSync endpoint."""
        token = await self._id_token()
        headers = {"authorization": token}
        url = self._endpoints[endpoint_key]["endpoint"]
        async with self._session.post(url, json=query, headers=headers) as resp:
            return await resp.json()

    # -- public API methods --------------------------------------------------

    async def list_devices(self) -> list[dict]:
        """Return a list of device dicts with full state + latest data merged."""
        tree_query = {
            "operationName": "Query",
            "variables": {},
            "query": "query Query {\n  getDeviceTree\n}\n",
        }
        tree_resp = await self._post("device", tree_query)
        tree_data = json.loads(tree_resp["data"]["getDeviceTree"])
        if not tree_data:
            return []

        devices = []
        for node in tree_data[0]["c"]:
            device_id = node["i"]["name"]
            state = await self.get_device_state(device_id)
            latest = await self.get_latest_data(device_id)
            merged = {**state, **latest, "deviceId": device_id}
            devices.append(merged)
        return devices

    async def get_device_state(self, device_id: str) -> dict:
        """Fetch the reported device state (getDeviceState)."""
        query = {
            "operationName": "Query",
            "variables": {"deviceId": device_id},
            "query": (
                "query Query($deviceId: ID!) {\n"
                "  getDeviceState(deviceId: $deviceId) {\n"
                "    desired\n    reported\n    timestamp\n    __typename\n"
                "  }\n}\n"
            ),
        }
        resp = await self._post("device", query)
        return json.loads(resp["data"]["getDeviceState"]["reported"])

    async def get_latest_data(self, device_id: str) -> dict:
        """Fetch the latest sensor/runtime data (getLatestData)."""
        query = {
            "operationName": "Query",
            "variables": {"deviceId": device_id},
            "query": (
                "query Query($deviceId: String!) {\n"
                "  getLatestData(deviceId: $deviceId) {\n"
                "    deviceId\n    timestamp\n    sessionId\n    type\n    data\n"
                "    __typename\n"
                "  }\n}\n"
            ),
        }
        resp = await self._post("data", query)
        item = resp["data"]["getLatestData"]
        data = json.loads(item["data"])
        data["timestamp"] = item["timestamp"]
        data["type"] = item["type"]
        return data

    async def send_state_change(self, device_id: str, payload: dict) -> dict:
        """Send a requestStateChange mutation."""
        query = {
            "operationName": "Mutation",
            "variables": {
                "deviceId": device_id,
                "state": json.dumps(payload),
                "getFullState": False,
            },
            "query": (
                "mutation Mutation($deviceId: ID!, $state: AWSJSON!, $getFullState: Boolean) {\n"
                "  requestStateChange(deviceId: $deviceId, state: $state, getFullState: $getFullState)\n"
                "}\n"
            ),
        }
        return await self._post("device", query)

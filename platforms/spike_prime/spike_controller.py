import asyncio
from bleak import BleakClient

SERVICE_UUID = "0000fd02-0000-1000-8000-00805f9b34fb"  # LEGO hub service

class SpikeHubController:
    def __init__(self, address: str):
        self.address = address
        self._client = BleakClient(address)

    async def __aenter__(self):
        await self._client.connect()
        # In a real implementation you'd do LWP3 handshake here
        print(f"Connected to {self.address}")
        return self

    async def __aexit__(self, exc_type, exc, tb):
        await self._client.disconnect()
        print(f"Disconnected from {self.address}")

    # Placeholder methods so your earlier example runs without errors
    async def set_light(self, color: str):
        print(f"[{self.address}] set_light({color}) (not implemented yet)")

    async def run_motor(self, port: str, speed: int, duration: int):
        print(f"[{self.address}] run_motor({port}, speed={speed}, duration={duration}) (not implemented yet)")

    async def read_motor_angle(self, port: str) -> int:
        print(f"[{self.address}] read_motor_angle({port}) (not implemented yet)")
        return 0

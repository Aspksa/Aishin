import asyncio
from .events import EventBus
from .state import StateManager

class Heartbeat:
    def __init__(self, interval_seconds: int = 60):
        self.interval_seconds = interval_seconds
        self.state = StateManager()
        self.events = EventBus()
        self._stop = asyncio.Event()

    async def run(self):
        ticks = 0
        while not self._stop.is_set():
            state = self.state.heartbeat()
            ticks += 1
            if ticks == 1 or ticks % 10 == 0:
                self.events.emit('aishin.heartbeat', scope=state.current_scope, payload={'status':state.status,'activity':state.activity}, importance=0.1)
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self.interval_seconds)
            except asyncio.TimeoutError:
                pass

    def stop(self):
        self._stop.set()

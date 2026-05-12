import asyncio
import websockets
import json
import threading


class Bridge3D:
    """WebSocket bridge between Python backend and the React 3D Dashboard.
    
    Sends: volume data (Python → Browser)
    Receives: avatar change commands (Browser → Python)
    """

    def __init__(self, port=8765):
        self.port = port
        self.clients = set()
        self.on_change_avatar = None
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()
        print(f"[Bridge3D] WebSocket server starting on ws://localhost:{self.port}")

    def _run_loop(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_until_complete(self._serve())

    async def _serve(self):
        async with websockets.serve(
            self._handler,
            "localhost",
            self.port,
            ping_interval=20,
            ping_timeout=20,
        ) as server:
            print(f"[Bridge3D] WebSocket server is LIVE on port {self.port}")
            await asyncio.Future()  # run forever

    async def _handler(self, websocket):
        """Handle a single client connection."""
        self.clients.add(websocket)
        print(f"[Bridge3D] Client connected. Total clients: {len(self.clients)}")
        try:
            # This loop receives messages FROM the browser
            async for raw_message in websocket:
                print(f"[Bridge3D] >>> Received from browser: {raw_message}")
                try:
                    data = json.loads(raw_message)
                    msg_type = data.get("type", "")

                    if msg_type == "change_avatar" and self.on_change_avatar:
                        avatar_val = data.get("avatar", "real")
                        print(f"[Bridge3D] Triggering avatar change to: {avatar_val}")
                        # Run in a separate thread so we don't block the event loop
                        threading.Thread(
                            target=self.on_change_avatar,
                            args=(avatar_val,),
                            daemon=True,
                        ).start()

                except json.JSONDecodeError:
                    print(f"[Bridge3D] Bad JSON: {raw_message}")
                except Exception as e:
                    print(f"[Bridge3D] Error processing message: {e}")

        except websockets.exceptions.ConnectionClosed:
            pass
        finally:
            self.clients.discard(websocket)
            print(f"[Bridge3D] Client disconnected. Total clients: {len(self.clients)}")

    # ── Outgoing messages (Python → Browser) ──────────────────────────

    def set_volume(self, volume):
        """Send current audio volume to all connected dashboards."""
        if not self.clients:
            return
        self._broadcast({"type": "volume", "value": volume})

    def set_emotion(self, emotion):
        """Send an emotion tag to all connected dashboards."""
        if not self.clients:
            return
        self._broadcast({"type": "emotion", "value": emotion})

    def _broadcast(self, payload):
        """Thread-safe broadcast to every connected WebSocket client."""
        message = json.dumps(payload)

        async def _send_all():
            dead = set()
            for ws in list(self.clients):
                try:
                    await ws.send(message)
                except Exception:
                    dead.add(ws)
            self.clients -= dead

        asyncio.run_coroutine_threadsafe(_send_all(), self.loop)

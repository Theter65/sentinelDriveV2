"""Thread-safe, in-process fan-out for live browser updates."""

import json
import queue
import threading
import uuid


class RealtimeHub:
    """Publishes committed MQTT updates to authenticated SSE clients."""

    def __init__(self, queue_size=64):
        self._queue_size = queue_size
        self._lock = threading.Lock()
        self._subscribers = {}

    def subscribe(self, scope, bus_id=None):
        token = uuid.uuid4().hex
        subscriber_queue = queue.Queue(maxsize=self._queue_size)
        with self._lock:
            self._subscribers[token] = (scope, bus_id, subscriber_queue)
        return token, subscriber_queue

    def unsubscribe(self, token):
        with self._lock:
            self._subscribers.pop(token, None)

    def publish(self, event_name, payload, bus_id=None):
        message = (event_name, json.dumps(payload, separators=(",", ":"), ensure_ascii=False))
        with self._lock:
            subscribers = tuple(self._subscribers.values())

        for scope, subscribed_bus_id, subscriber_queue in subscribers:
            if scope == "tracking" and not (
                event_name == "mqtt_status"
                or (event_name == "location" and subscribed_bus_id == bus_id)
            ):
                continue
            if scope == "dashboard" and event_name not in {"location", "mqtt_status"}:
                continue
            if scope == "status" and event_name != "mqtt_status":
                continue
            try:
                subscriber_queue.put_nowait(message)
            except queue.Full:
                # Keep the newest state if a browser cannot consume updates quickly enough.
                try:
                    subscriber_queue.get_nowait()
                except queue.Empty:
                    pass
                try:
                    subscriber_queue.put_nowait(message)
                except queue.Full:
                    pass


realtime_hub = RealtimeHub()

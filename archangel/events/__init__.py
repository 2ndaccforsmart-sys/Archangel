"""Event bus & Agent lifecycle — communication backbone and supervision for Archangel."""

from __future__ import annotations

import asyncio
import fnmatch
import logging
import threading
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


class EventBus:
    """Thread-safe event bus supporting sync/async pub-sub, wildcards, and event history."""

    _instance: Optional["EventBus"] = None
    _lock = threading.Lock()

    def __init__(self, history_size: int = 100) -> None:
        self._handlers: Dict[str, List[Callable[[dict[str, Any]], None]]] = {}
        self._history: deque = deque(maxlen=history_size)
        self._executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="eventbus-worker")
        self._handler_lock = threading.Lock()
        logger.debug("EventBus initialized (history_size=%d).", history_size)

    @classmethod
    def get_instance(cls) -> "EventBus":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """Reset the singleton instance (primarily for testing)."""
        with cls._lock:
            if cls._instance:
                cls._instance._executor.shutdown(wait=False)
                cls._instance = None

    def publish(self, event_type: str, payload: dict[str, Any]) -> None:
        """Publish an event synchronously to all matching subscribers."""
        event_record = {
            "event_type": event_type,
            "payload": payload,
            "timestamp": time.time(),
        }
        with self._handler_lock:
            self._history.append(event_record)
            matching_handlers = []
            for pattern, handlers in self._handlers.items():
                if pattern == event_type or fnmatch.fnmatch(event_type, pattern):
                    matching_handlers.extend(handlers)

        logger.debug("Event published: %s (matching handlers: %d)", event_type, len(matching_handlers))

        for handler in matching_handlers:
            try:
                handler(payload)
            except Exception as exc:
                logger.error("Handler error for event '%s': %s", event_type, exc, exc_info=True)

    def publish_async(self, event_type: str, payload: dict[str, Any]) -> None:
        """Publish an event asynchronously on a background thread pool."""
        self._executor.submit(self.publish, event_type, payload)

    def subscribe(self, event_pattern: str, handler: Callable[[dict[str, Any]], None]) -> None:
        """Subscribe a callback handler to an event pattern (supports wildcards like 'lead.*')."""
        with self._handler_lock:
            handlers = self._handlers.setdefault(event_pattern, [])
            if handler not in handlers:
                handlers.append(handler)
                logger.debug("Subscribed %s to pattern '%s'", getattr(handler, '__name__', str(handler)), event_pattern)

    def unsubscribe(self, event_pattern: str, handler: Callable[[dict[str, Any]], None]) -> None:
        """Unsubscribe a callback handler from an event pattern."""
        with self._handler_lock:
            handlers = self._handlers.get(event_pattern, [])
            if handler in handlers:
                handlers.remove(handler)
                logger.debug("Unsubscribed %s from pattern '%s'", getattr(handler, '__name__', str(handler)), event_pattern)

    def get_history(self, limit: int = 50, pattern: Optional[str] = None) -> List[dict[str, Any]]:
        """Retrieve recent published event history."""
        with self._handler_lock:
            events = list(self._history)

        if pattern:
            events = [e for e in events if fnmatch.fnmatch(e["event_type"], pattern)]

        return events[-limit:]


class GuardianAgent:
    """Supervisor agent that monitors runtime health, agent status, and error metrics."""

    def __init__(self, event_bus: Optional[EventBus] = None) -> None:
        self.event_bus = event_bus or EventBus.get_instance()
        self._component_health: Dict[str, str] = {}
        self._error_counts: Dict[str, int] = {}
        self._last_heartbeats: Dict[str, float] = {}
        self._lock = threading.Lock()

        # Subscribe to health and lifecycle events
        self.event_bus.subscribe("agent.*", self._handle_agent_event)
        self.event_bus.subscribe("health.*", self._handle_health_event)
        logger.debug("GuardianAgent created and subscribed to agent/health events.")

    def _handle_agent_event(self, payload: dict[str, Any]) -> None:
        agent_name = payload.get("agent", "unknown")
        status = payload.get("status", "running")
        with self._lock:
            self._component_health[agent_name] = status
            self._last_heartbeats[agent_name] = time.time()

            if status == "failed":
                self._error_counts[agent_name] = self._error_counts.get(agent_name, 0) + 1
                logger.warning("Guardian detected failure in agent '%s' (total failures: %d)",
                               agent_name, self._error_counts[agent_name])

    def _handle_health_event(self, payload: dict[str, Any]) -> None:
        component = payload.get("component", "system")
        status = payload.get("status", "healthy")
        with self._lock:
            self._component_health[component] = status

    def record_heartbeat(self, agent_name: str) -> None:
        with self._lock:
            self._last_heartbeats[agent_name] = time.time()
            if self._component_health.get(agent_name) == "offline":
                self._component_health[agent_name] = "running"

    def record_failure(self, agent_name: str, error_msg: str) -> None:
        with self._lock:
            self._error_counts[agent_name] = self._error_counts.get(agent_name, 0) + 1
            failures = self._error_counts[agent_name]
            if failures >= 3:
                self._component_health[agent_name] = "degraded"
            logger.error("Guardian recorded failure for '%s': %s (count=%d)", agent_name, error_msg, failures)

        self.event_bus.publish("agent.failed", {
            "agent": agent_name,
            "error": error_msg,
            "failures": failures,
            "status": self._component_health.get(agent_name, "degraded"),
        })

    def get_system_health(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "components": dict(self._component_health),
                "error_counts": dict(self._error_counts),
                "last_heartbeats": dict(self._last_heartbeats),
            }


class CommanderAgent:
    """Orchestrator responsible for agent registration, lifecycle management, and command routing."""

    def __init__(self, event_bus: Optional[EventBus] = None) -> None:
        self.event_bus = event_bus or EventBus.get_instance()
        self._registered_agents: Set[str] = set()
        self._agent_states: Dict[str, str] = {}
        self._lock = threading.Lock()
        logger.debug("CommanderAgent created.")

    def register_agent(self, agent_name: str) -> None:
        with self._lock:
            self._registered_agents.add(agent_name)
            self._agent_states[agent_name] = "registered"
        self.event_bus.publish("agent.registered", {"agent": agent_name, "status": "registered"})

    def start_agent(self, agent_name: str) -> bool:
        with self._lock:
            if agent_name not in self._registered_agents:
                logger.warning("Cannot start unregistered agent '%s'", agent_name)
                return False
            self._agent_states[agent_name] = "running"

        self.event_bus.publish("agent.started", {"agent": agent_name, "status": "running"})
        return True

    def stop_agent(self, agent_name: str) -> bool:
        with self._lock:
            if agent_name not in self._registered_agents:
                return False
            self._agent_states[agent_name] = "stopped"

        self.event_bus.publish("agent.stopped", {"agent": agent_name, "status": "stopped"})
        return True

    def get_agent_states(self) -> Dict[str, str]:
        with self._lock:
            return dict(self._agent_states)

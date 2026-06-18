from __future__ import annotations
import time
from dataclasses import dataclass, field


HEARTBEAT_TIMEOUT = 30  # seconds
AFFINITY_MAX = 500     # max profile entries per node
OFFLINE_PURGE_AFTER = 86400  # seconds (24h) before removing offline node


@dataclass
class NodeState:
    node_id: str
    url: str
    max_sessions: int
    current_sessions: int = 0
    last_heartbeat: float = 0.0
    affinity: dict[str, float] = field(default_factory=dict)  # profile_id → last_used_ts
    cpu_percent: float = 0
    memory_percent: float = 0
    disk_percent: float = 0

    @property
    def available_slots(self) -> int:
        return max(0, self.max_sessions - self.current_sessions)

    @property
    def online(self) -> bool:
        return (time.time() - self.last_heartbeat) < HEARTBEAT_TIMEOUT


class NodeRegistry:
    def __init__(self):
        self._nodes: dict[str, NodeState] = {}

    def register_or_heartbeat(self, node_id: str, url: str, max_sessions: int, current_sessions: int, cpu_percent: float = 0, memory_percent: float = 0, disk_percent: float = 0) -> None:
        if node_id in self._nodes:
            n = self._nodes[node_id]
            n.url = url
            n.max_sessions = max_sessions
            n.current_sessions = current_sessions
            n.last_heartbeat = time.time()
            n.cpu_percent = cpu_percent
            n.memory_percent = memory_percent
            n.disk_percent = disk_percent
        else:
            self._nodes[node_id] = NodeState(
                node_id=node_id, url=url, max_sessions=max_sessions,
                current_sessions=current_sessions, last_heartbeat=time.time(),
                cpu_percent=cpu_percent, memory_percent=memory_percent, disk_percent=disk_percent,
            )

    def get_available_nodes(self) -> list[NodeState]:
        return [n for n in self._nodes.values() if n.online and n.available_slots > 0]

    def select_node(self, profile_id: str) -> NodeState | None:
        available = self.get_available_nodes()
        if not available:
            return None
        # Affinity: prefer node that last used this profile
        for n in available:
            if profile_id in n.affinity:
                return n
        # Fallback: most available slots
        return max(available, key=lambda n: n.available_slots)

    def update_affinity(self, node_id: str, profile_id: str) -> None:
        n = self._nodes.get(node_id)
        if n:
            n.affinity[profile_id] = time.time()
            # LRU eviction
            if len(n.affinity) > AFFINITY_MAX:
                oldest = sorted(n.affinity, key=n.affinity.get)[:len(n.affinity) - AFFINITY_MAX]
                for k in oldest:
                    del n.affinity[k]

    def increment_sessions(self, node_id: str) -> None:
        n = self._nodes.get(node_id)
        if n:
            n.current_sessions += 1

    def decrement_sessions(self, node_id: str) -> None:
        n = self._nodes.get(node_id)
        if n and n.current_sessions > 0:
            n.current_sessions -= 1

    def all_nodes(self) -> list[NodeState]:
        return list(self._nodes.values())

    def purge_offline(self) -> int:
        """Remove nodes that have been offline longer than OFFLINE_PURGE_AFTER."""
        now = time.time()
        to_remove = [nid for nid, n in self._nodes.items()
                     if (now - n.last_heartbeat) > OFFLINE_PURGE_AFTER]
        for nid in to_remove:
            del self._nodes[nid]
        return len(to_remove)

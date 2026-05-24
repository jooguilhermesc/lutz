"""Conversation state machine for the Lutz agentic layer.

Implements the state diagram from docs/agentic-chat-architecture.md §4:

    IDLE → GOAL_EXTRACTION → PLANNING → AWAITING_CONFIRMATION
                                               │
                                               ├─ CONFIRMED → EXECUTING → STEP_COMPLETE
                                               │       ↑                    │
                                               │       └── (next step) ─────┘
                                               │
                                               ├─ ADJUSTING → PLANNING (replans)
                                               │
                                               └─ CANCELLED → IDLE
"""
from __future__ import annotations

import threading
from dataclasses import dataclass, field
from enum import Enum


class ConversationState(Enum):
    IDLE = "idle"
    GOAL_EXTRACTION = "goal_extraction"
    PLANNING = "planning"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    EXECUTING = "executing"
    STEP_COMPLETE = "step_complete"
    ADJUSTING = "adjusting"
    CANCELLED = "cancelled"


@dataclass
class AgentPlan:
    steps: list[dict]
    current_step: int = 0
    goal: str = ""
    inclusion_criterion: str | None = None


@dataclass
class ConversationContext:
    session_id: str
    state: ConversationState = ConversationState.IDLE
    plan: AgentPlan | None = None
    messages: list[dict] = field(default_factory=list)
    preferred_model: str | None = None


class ConversationManager:
    """Manages conversation sessions and their state transitions.

    Thread-safe: a global lock guards session creation; per-session locks
    guard mutations so concurrent requests on the same session_id are
    serialised without blocking unrelated sessions.
    """

    def __init__(self) -> None:
        self._sessions: dict[str, ConversationContext] = {}
        self._lock = threading.Lock()                        # guards _sessions / _session_locks creation
        self._session_locks: dict[str, threading.Lock] = {}  # per-session mutation lock

    def _get_session_lock(self, session_id: str) -> threading.Lock:
        """Return the per-session lock, creating it under the global lock if needed."""
        with self._lock:
            if session_id not in self._session_locks:
                self._session_locks[session_id] = threading.Lock()
            return self._session_locks[session_id]

    def get_or_create(self, session_id: str) -> ConversationContext:
        """Return existing session or create a new one with state=IDLE."""
        with self._lock:
            if session_id not in self._sessions:
                self._sessions[session_id] = ConversationContext(session_id=session_id)
                self._session_locks[session_id] = threading.Lock()
            return self._sessions[session_id]

    def transition(self, session_id: str, new_state: ConversationState) -> None:
        """Change the state of a session."""
        with self._get_session_lock(session_id):
            ctx = self._sessions.get(session_id)
            if ctx is None:
                ctx = self.get_or_create(session_id)
            ctx.state = new_state

    def set_plan(self, session_id: str, plan: AgentPlan) -> None:
        """Assign a plan to a session."""
        with self._get_session_lock(session_id):
            ctx = self._sessions.get(session_id)
            if ctx is None:
                ctx = self.get_or_create(session_id)
            ctx.plan = plan

    def advance_step(self, session_id: str) -> bool:
        """Increment current_step. Return True if there is a next step, False otherwise."""
        with self._get_session_lock(session_id):
            ctx = self._sessions.get(session_id)
            if ctx is None:
                ctx = self.get_or_create(session_id)
            if ctx.plan is None:
                return False
            next_index = ctx.plan.current_step + 1
            if next_index < len(ctx.plan.steps):
                ctx.plan.current_step = next_index
                return True
            return False

    def cancel(self, session_id: str) -> None:
        """Cancel the current plan and reset state to IDLE."""
        with self._get_session_lock(session_id):
            ctx = self._sessions.get(session_id)
            if ctx is None:
                ctx = self.get_or_create(session_id)
            ctx.state = ConversationState.IDLE
            ctx.plan = None

    def is_terminal(self, ctx: ConversationContext) -> bool:
        """Return True when the context is in a terminal state (IDLE or CANCELLED)."""
        return ctx.state in (ConversationState.IDLE, ConversationState.CANCELLED)

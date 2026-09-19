"""Bounded multi-application sequencing over an authorized execution gateway."""

import asyncio
from dataclasses import dataclass
import threading
import time
import logging
from .errors import ObservationUnavailable
from .verification import matches as verification_matches


@dataclass(frozen=True)
class DesktopStep:
    application_id: str
    action: str
    target: dict
    arguments: dict
    expected: dict
    permission: str
    recovery: str = "pause"

    def __post_init__(self):
        if self.action not in {"invoke", "select", "expand", "collapse", "set_text", "focus", "scroll", "search", "submit_message"}:
            raise ValueError("Unknown semantic desktop action")
        allowed = {"text", "destination", "destination_text"} if self.action == "submit_message" else {"text"} if self.action in {"set_text", "search"} else {"direction"} if self.action == "scroll" else set()
        if self.action == "set_text":
            allowed.update({"pointer_focus", "expected_previous"})
        if not isinstance(self.arguments, dict) or set(self.arguments) - allowed:
            raise ValueError("Unknown action argument")
        if "pointer_focus" in self.arguments and type(self.arguments["pointer_focus"]) is not bool:
            raise ValueError("Editor pointer focus must be a boolean")
        if "expected_previous" in self.arguments and (not isinstance(self.arguments["expected_previous"], str)
                                                       or len(self.arguments["expected_previous"]) > 5001):
            raise ValueError("Previous editor text must be bounded")
        if self.action in {"set_text", "search"} and (not isinstance(self.arguments.get("text"), str) or len(self.arguments["text"]) > (200 if self.action == "search" else 5000)):
            raise ValueError("Bounded text is required")
        if self.action == "submit_message" and (self.permission != "communication.send" or
                not isinstance(self.arguments.get("text"), str) or not 1 <= len(self.arguments["text"]) <= 4000
                or not isinstance(self.arguments.get("destination"), list) or not 1 <= len(self.arguments["destination"]) <= 3
                or not isinstance(self.arguments.get("destination_text"), str) or not 1 <= len(self.arguments["destination_text"]) <= 4000):
            raise ValueError("Message submission requires a bounded body and communication permission")
        if not self.application_id or not self.expected:
            raise ValueError("Application and verification criteria are required")
        if self.recovery != "pause":
            raise ValueError("Only pause-for-review recovery is currently supported")
        if set(self.expected) - {"name", "control_type", "value", "enabled", "selected", "runtime_id", "name_token"}:
            raise ValueError("Unknown verification criterion")
        if "name_token" in self.expected and (self.expected.get("control_type") != "Window"
                or not isinstance(self.expected["name_token"], str) or not self.expected["name_token"].strip()
                or len(self.expected["name_token"]) > 200):
            raise ValueError("A bounded window-title destination is required")


class DesktopWorkflow:
    """The gateway owns permissions and confirmations; this engine cannot grant them."""

    def __init__(self, sessions, gateway, *, timeout=15, max_steps=30, stop_event=None):
        if not 0 < timeout <= 60 or not 1 <= max_steps <= 100:
            raise ValueError("Invalid workflow bounds")
        self.sessions = sessions
        self.gateway = gateway
        self.timeout = timeout
        self.max_steps = max_steps
        self.stop_event = stop_event or threading.Event()
        self.status = "READY"
        self.history = []
        self.paused = False

    def emergency_stop(self):
        self.stop_event.set()  # Safe to call directly from the Qt thread.

    def pause(self):
        self.paused = True

    def resume(self):
        self.paused = False

    def check(self):
        if self.stop_event.is_set():
            raise asyncio.CancelledError("Desktop control stopped")

    async def checkpoint(self):
        self.check()
        while self.paused:
            self.status = "PAUSED"
            await asyncio.sleep(.05)
            self.check()

    async def run(self, steps, identities):
        if not 1 <= len(steps) <= self.max_steps:
            raise ValueError("Desktop plan exceeds step limit")
        if any(step.application_id not in identities for step in steps):
            raise ValueError("Plan references an undiscovered application")
        try:
            for step in steps:
                await self.checkpoint()
                self.status = "SWITCHING_APP"
                session = (self.sessions.select_session(step.application_id) if step.application_id in self.sessions.sessions
                           else self.sessions.select(identities[step.application_id]))
                # Gateway must authorize observation and verify the selected app identity.
                observation = await asyncio.wait_for(self.gateway.observe(session), self.timeout)
                session.observe(observation)
                if step.action != "set_text" and any(verification_matches(control, step.expected)
                                                      for control in observation.get("controls", [])):
                    raise ValueError("The postcondition already exists; specify evidence of this action's result")
                await self.checkpoint()
                self.status = "WAITING_FOR_CONFIRMATION"
                # Permission names from a plan are only claims: the gateway derives actual
                # requirements from the operation and its consequential action class.
                permit = await self.gateway.authorize(session, step)
                await self.checkpoint()
                self.status = "ACTING"
                await asyncio.wait_for(self.gateway.execute(session, step, permit, self.stop_event), self.timeout)
                self.status = "VERIFYING"
                deadline = time.monotonic() + self.timeout
                snapshot_failures = 0
                while True:
                    await self.checkpoint()
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise TimeoutError("Expected application state was not observed")
                    try:
                        observation = await asyncio.wait_for(self.gateway.observe(session), remaining)
                    except ObservationUnavailable:
                        snapshot_failures += 1
                        if snapshot_failures >= 3:
                            raise
                        logging.getLogger(__name__).info("Accessibility snapshot changed during verification; re-observing without repeating input")
                        await asyncio.sleep(min(.05, max(0, deadline - time.monotonic())))
                        continue
                    session.observe(observation)
                    matches = [control for control in observation.get("controls", [])
                               if verification_matches(control, step.expected)]
                    if len(matches) == 1:
                        session.last_verified_state = dict(step.expected)
                        if hasattr(self.gateway, "verified"):
                            self.gateway.verified(session, step)
                        break
                    await asyncio.sleep(min(.1, max(0, deadline - time.monotonic())))
                self.history.append({"application_id": step.application_id, "action": step.action,
                                     "verified": True})
            self.status = "COMPLETED"
        except asyncio.CancelledError:
            self.status = "CANCELLED"
            raise
        except (InterruptedError, PermissionError, TimeoutError, ValueError, LookupError):
            self.status = "PAUSED_REVIEW_REQUIRED"
            raise
        except Exception:
            self.status = "FAILED"
            raise
        return {"status": self.status, "history": list(self.history)}

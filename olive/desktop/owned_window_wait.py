"""One cancellable attach request; only a not-yet-visible window is retried."""
import asyncio
from copy import deepcopy
import time
from .owned_launch import NoOwnedWindow


class OwnedWindowTimeout(TimeoutError):
    """A verified launch did not expose a unique eligible window in time."""


async def wait_for_owned_window(record, check, *, timeout=5.0, interval=0.05,
                                clock=time.monotonic, sleep=asyncio.sleep, probe=None):
    started = clock()
    attempts = 0
    first = None

    async def resolve():
        return await asyncio.to_thread(record.resolve)

    def evidence():
        nonlocal first
        if first is None:
            first = deepcopy(record.resolution)
        record.resolution['wait'] = dict(attempts=attempts,
            elapsed_ms=round((clock()-started)*1000, 2), first=first)

    while True:
        check()
        if clock()-started >= timeout:
            evidence()
            record.resolution['outcome'] = 'owned_window_readiness_timeout'
            raise OwnedWindowTimeout('Owned window readiness timed out; no target selected')
        attempts += 1
        try:
            # Also bound a stalled process/window query, without replaying it.
            remaining = timeout - (clock()-started)
            budget = asyncio.timeout(max(0, remaining))
            async with budget:
                window = await (probe or resolve)()
            check()
            evidence()
            return window
        except NoOwnedWindow:
            evidence()
            # Only visibility/readiness absence qualifies, never identity rejection.
            if any(record.resolution.get('window_rejections', {}).values()):
                raise
            check()
            remaining = timeout - (clock()-started)
            if remaining <= 0:
                record.resolution['outcome'] = 'owned_window_readiness_timeout'
                raise OwnedWindowTimeout('Owned window readiness timed out; no target selected') from None
            await sleep(min(interval, remaining))
        except TimeoutError:
            evidence()
            if not budget.expired():
                # A query's own exception is not a readiness deadline.
                raise
            record.resolution['outcome'] = 'owned_window_query_timeout'
            raise OwnedWindowTimeout('Owned window query timed out; no target selected') from None
        except BaseException:
            evidence()
            raise

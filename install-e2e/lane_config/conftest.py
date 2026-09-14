"""These guards read files. They must never need a running stack.

install-e2e/conftest.py has a session-scoped autouse `_stack_ready` that blocks
on the control plane and fails with "Is the stack running?". It applies to every
test under install-e2e/, which is why the lane-config guards next door could not
be run on their own -- and so nothing ran them at all. Overriding the fixture
here (nearest conftest wins) is what lets a plain
`pytest install-e2e/lane_config` pass on a machine with no jarvis on it.
"""
import pytest


@pytest.fixture(scope="session", autouse=True)
def _stack_ready() -> None:
    return None

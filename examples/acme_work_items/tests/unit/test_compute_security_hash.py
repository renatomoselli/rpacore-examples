from __future__ import annotations

import hashlib

from rpacore import Status

from skills.compute_security_hash import ComputeSecurityHash
from tests.conftest import run_skill


def test_compute_security_hash_matches_known_vector(example_config) -> None:
    state = {
        "validated": True,
        "client_id": "C123",
        "wiid": "WI456",
        "work_item_id": "1001",
        "discovered_hash": "fingerprint",
    }
    transaction = run_skill(
        ComputeSecurityHash(name="compute", execution_order=1),
        state=state,
        config=example_config,
    )
    assert transaction.status is Status.SUCCESSFUL
    assert transaction.state["security_hash"] == hashlib.sha1(b"C123WI456").hexdigest()
    assert transaction.state["update_intent_id"] == hashlib.sha256(
        f"1001|fingerprint|{transaction.state['security_hash']}".encode()
    ).hexdigest()

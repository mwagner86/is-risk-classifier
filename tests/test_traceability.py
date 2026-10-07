"""Every acceptance criterion, counter-measure and invariant has at least one test."""

import re
from pathlib import Path

REQUIRED = {
    *(f"AK-0{s}.{n}" for s in (1, 2, 3) for n in (1, 2, 3)),
    "US-04a",
    "US-04b",
    *(f"M-0{n}" for n in range(1, 10)),
    "INV-02",
    "INV-03",
    "SM",
}


def test_every_requirement_has_a_test() -> None:
    found = set()
    for path in Path(__file__).parent.glob("test_*.py"):
        found |= set(re.findall(r'req\("([^"]+)"\)', path.read_text()))
    assert REQUIRED - found == set()

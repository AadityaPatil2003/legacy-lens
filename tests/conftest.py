from pathlib import Path

import pytest

SAMPLES = Path(__file__).resolve().parent.parent / "samples"


@pytest.fixture
def samples() -> Path:
    return SAMPLES


@pytest.fixture
def read(samples):
    def _read(relative: str) -> str:
        return (samples / relative).read_text()

    return _read

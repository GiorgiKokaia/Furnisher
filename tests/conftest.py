from pathlib import Path

import pytest

from furnisher.authoring import load_plan

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def studio():
    return load_plan(FIXTURES / "studio.yaml")


@pytest.fixture
def two_bedroom():
    return load_plan(FIXTURES / "two-bedroom.yaml")

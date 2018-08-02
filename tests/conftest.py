import pytest
import multio


def pytest_addoption(parser):
    parser.addoption(
        "--async", action="store", default="trio", help="asynclib: trio or curio"
    )


@pytest.fixture
def asynclib(request):
    libstr = request.config.getoption("--async")
    multio.init(libstr)
    return multio.asynclib

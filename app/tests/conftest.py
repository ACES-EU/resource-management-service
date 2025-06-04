from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def mock_kube_config():
    with patch("kubernetes.config.load_kube_config") as mock:
        mock.return_value = None
        yield

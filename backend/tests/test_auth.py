import pytest
from unittest.mock import MagicMock, patch, PropertyMock
from backend.auth import AuthManager


@pytest.fixture
def auth_manager(tmp_path):
    session_file = str(tmp_path / "tidal-session.json")
    return AuthManager(session_file=session_file)


def test_auth_manager_initial_state(auth_manager):
    assert auth_manager.is_authenticated is False
    assert auth_manager.session is None


def test_get_auth_status_unauthenticated(auth_manager):
    status = auth_manager.get_status()
    assert status["authenticated"] is False
    assert status["username"] is None


def test_get_device_link():
    mock_login = MagicMock()
    mock_login.verification_uri_complete = "https://link.tidal.com/ABC123"
    mock_login.user_code = "ABC123"
    mock_login.expires_in = 300
    mock_future = MagicMock()

    mock_session = MagicMock()
    mock_session.login_oauth.return_value = (mock_login, mock_future)

    with patch("backend.auth.tidalapi.Session", return_value=mock_session):
        manager = AuthManager()
        result = manager.get_device_link()

    assert result["url"] == "https://link.tidal.com/ABC123"
    assert result["code"] == "ABC123"
    assert result["expires_in"] == 300
    assert manager._device_login == mock_login
    assert manager._device_future == mock_future

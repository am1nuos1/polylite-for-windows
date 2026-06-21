import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from PySide6 import QtWidgets

from polymarket_terminal.auth import LoginAction, LoginDialog, safe_api_error_message


@pytest.fixture
def app() -> QtWidgets.QApplication:
    existing = QtWidgets.QApplication.instance()
    if existing is not None:
        return existing
    return QtWidgets.QApplication([])


def test_login_reports_missing_environment_credentials(
    app: QtWidgets.QApplication,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("POLYMARKET_KEY_ID", raising=False)
    monkeypatch.delenv("POLYMARKET_SECRET_KEY", raising=False)
    dialog = LoginDialog()
    assert "Environment variables not found" in dialog.environment_status.text()
    assert dialog.credentials().is_empty
    dialog.close()


def test_login_loads_environment_credentials(
    app: QtWidgets.QApplication,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("POLYMARKET_KEY_ID", "key-id")
    monkeypatch.setenv("POLYMARKET_SECRET_KEY", "secret-key")
    dialog = LoginDialog()
    credentials = dialog.credentials()
    assert credentials.api_key_id == "key-id"
    assert credentials.secret_key == "secret-key"
    assert "Loaded API credentials" in dialog.environment_status.text()
    dialog.close()


def test_login_continue_without_api_action(app: QtWidgets.QApplication) -> None:
    dialog = LoginDialog()
    dialog.continue_without_api()
    assert dialog.result() == LoginAction.CONTINUE_WITHOUT_API
    dialog.close()


def test_safe_api_error_messages_do_not_echo_exception_text() -> None:
    class AuthenticationError(Exception):
        pass

    class APITimeoutError(Exception):
        pass

    class APIConnectionError(Exception):
        pass

    assert safe_api_error_message(AuthenticationError("secret value")) == "Authentication failed"
    assert safe_api_error_message(APITimeoutError("secret value")) == "Request timed out"
    assert safe_api_error_message(APIConnectionError("secret value")) == "Network error"
    assert safe_api_error_message(Exception("secret value")) == "Unable to connect"

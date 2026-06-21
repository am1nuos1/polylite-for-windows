from __future__ import annotations

from PySide6 import QtWidgets

from polymarket_terminal.client import PolymarketClient
from polymarket_terminal.credentials import Credentials, credentials_from_environment


class LoginAction:
    SUBMIT = 1
    CONTINUE_WITHOUT_API = 2


class LoginDialog(QtWidgets.QDialog):
    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Polymarket US Login")
        self.api_key_input = QtWidgets.QLineEdit()
        self.secret_key_input = QtWidgets.QLineEdit()
        self.secret_key_input.setEchoMode(QtWidgets.QLineEdit.EchoMode.Password)
        self.environment_status = QtWidgets.QLabel()
        self.environment_status.setWordWrap(True)
        self.load_environment_button = QtWidgets.QPushButton("Load from environment")
        self.load_environment_button.clicked.connect(self.load_from_environment)
        self.continue_without_api_button = QtWidgets.QPushButton("Continue without API")
        self.continue_without_api_button.clicked.connect(self.continue_without_api)

        form = QtWidgets.QFormLayout()
        form.addRow("API Key ID", self.api_key_input)
        form.addRow("Secret Key", self.secret_key_input)

        self.buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Ok
            | QtWidgets.QDialogButtonBox.StandardButton.Cancel
        )
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)

        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(self.environment_status)
        layout.addLayout(form)
        layout.addWidget(self.load_environment_button)
        layout.addWidget(self.continue_without_api_button)
        layout.addWidget(self.buttons)
        self.load_from_environment()

    def credentials(self) -> Credentials:
        return Credentials(
            api_key_id=self.api_key_input.text().strip(),
            secret_key=self.secret_key_input.text().strip(),
        )

    def load_from_environment(self) -> bool:
        credentials, message = credentials_from_environment()
        self.environment_status.setText(message)
        if credentials is None:
            self.api_key_input.clear()
            self.secret_key_input.clear()
            return False
        self.api_key_input.setText(credentials.api_key_id)
        self.secret_key_input.setText(credentials.secret_key)
        return True

    def continue_without_api(self) -> None:
        self.done(LoginAction.CONTINUE_WITHOUT_API)


def safe_api_error_message(exc: Exception) -> str:
    name = exc.__class__.__name__
    if name == "AuthenticationError":
        return "Authentication failed"
    if name in {"APITimeoutError", "TimeoutError"}:
        return "Request timed out"
    if name in {"APIConnectionError", "ConnectError", "NetworkError"}:
        return "Network error"
    return "Unable to connect"


def safe_market_error_message(exc: Exception) -> str:
    name = exc.__class__.__name__
    if name in {"APITimeoutError", "TimeoutError"}:
        return "Search timed out"
    if name in {"APIConnectionError", "ConnectError", "NetworkError"}:
        return "Network error"
    return "Search unavailable"


async def authenticate_with_prompt(
    parent: QtWidgets.QWidget,
) -> tuple[PolymarketClient | None, bool]:
    while True:
        login = LoginDialog(parent)
        action = login.exec()
        if action == LoginAction.CONTINUE_WITHOUT_API:
            return None, True
        if action != QtWidgets.QDialog.DialogCode.Accepted:
            return None, False
        credentials = login.credentials()
        if credentials.is_empty:
            QtWidgets.QMessageBox.warning(
                parent,
                "API credentials required",
                "API credentials were not found in environment variables. Enter them manually.",
            )
            continue

        client = PolymarketClient(credentials)
        try:
            await client.connect()
            await client.balances_raw()
        except Exception as exc:
            credentials.clear()
            await client.close()
            QtWidgets.QMessageBox.warning(parent, "API error", safe_api_error_message(exc))
            continue
        return client, True


async def authenticate_credentials(
    credentials: Credentials,
) -> tuple[PolymarketClient | None, str | None]:
    client = PolymarketClient(credentials)
    try:
        await client.connect()
        await client.balances_raw()
    except Exception as exc:
        credentials.clear()
        await client.close()
        return None, safe_api_error_message(exc)
    return client, None

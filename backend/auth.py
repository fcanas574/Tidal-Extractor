import logging
from pathlib import Path
from typing import Optional

import tidalapi
from tidalapi import Quality, Config

logger = logging.getLogger(__name__)


class AuthManager:
    def __init__(self, session_file: str = "tidal-session.json"):
        self.session_file = Path(session_file)
        self.session: Optional[tidalapi.Session] = None
        self._device_login = None
        self._device_future = None

    @property
    def is_authenticated(self) -> bool:
        if self.session is None:
            return False
        try:
            return self.session.check_login()
        except Exception:
            return False

    def get_status(self) -> dict:
        if not self.is_authenticated:
            return {"authenticated": False, "username": None}
        try:
            user = self.session.user
            username = user.username if user else None
        except Exception:
            username = None
        return {"authenticated": True, "username": username}

    def get_device_link(self) -> dict:
        """Initiate OAuth device link flow."""
        config = Config(quality=Quality.high_lossless)
        self.session = tidalapi.Session(config)
        login, future = self.session.login_oauth()
        self._device_login = login
        self._device_future = future
        return {
            "url": login.verification_uri_complete,
            "code": login.user_code,
            "expires_in": login.expires_in,
        }

    def wait_for_device_auth(self) -> bool:
        """Block until the user completes device auth."""
        if not self._device_future:
            return False
        try:
            self._device_future.result()
            self.session.save_session_to_file(self.session_file)
            logger.info("Tidal auth successful, session saved")
            return True
        except Exception as e:
            logger.error(f"Device auth failed: {e}")
            return False

    def load_saved_session(self, quality: str = "high_lossless") -> bool:
        """Try to load a previously saved session."""
        quality_enum = {
            "hi_res_lossless": Quality.hi_res_lossless,
            "high_lossless": Quality.high_lossless,
            "low_320k": Quality.low_320k,
            "low_96k": Quality.low_96k,
        }.get(quality, Quality.high_lossless)

        config = Config(quality=quality_enum)
        self.session = tidalapi.Session(config)
        try:
            if self.session_file.exists():
                self.session.login_session_file(self.session_file)
                if self.session.check_login():
                    logger.info("Loaded saved Tidal session")
                    return True
        except Exception as e:
            logger.warning(f"Failed to load saved session: {e}")
        self.session = None
        return False

    def logout(self):
        """Clear the saved session and reset."""
        if self.session_file.exists():
            self.session_file.unlink()
        self.session = None
        self._device_login = None
        self._device_future = None

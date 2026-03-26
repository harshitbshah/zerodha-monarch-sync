import os
import pytest
from unittest.mock import MagicMock, patch

import kite_auth

_ENV = {
    "ZERODHA_USER_ID": "AB1234",
    "ZERODHA_PASSWORD": "hunter2",
    "ZERODHA_TOTP_KEY": "JBSWY3DPEHPK3PXP",
}


def _mock_session(enctoken="enc_test"):
    """Pre-wired mock session for the happy-path login flow."""
    s = MagicMock()

    # Step 1: GET /user/login — sets kf_session cookie
    init_r = MagicMock()
    s.get.return_value = init_r

    # Step 2: POST /api/login
    login_r = MagicMock()
    login_r.json.return_value = {"status": "success", "data": {"request_id": "req_id"}}

    # Step 3: POST /api/twofa — server sets enctoken cookie
    twofa_r = MagicMock()
    twofa_r.json.return_value = {"status": "success"}

    s.post.side_effect = [login_r, twofa_r]

    # enctoken returned from cookies
    s.cookies.get.return_value = enctoken
    return s


class TestLogin:
    def test_happy_path_returns_enctoken(self):
        s = _mock_session(enctoken="the_enctoken")
        with patch("kite_auth.requests.Session", return_value=s), \
             patch("kite_auth.pyotp.TOTP") as mock_totp, \
             patch.dict(os.environ, _ENV):
            mock_totp.return_value.now.return_value = "123456"
            assert kite_auth.login() == "the_enctoken"

    def test_totp_value_sent_in_twofa_call(self):
        s = _mock_session()
        with patch("kite_auth.requests.Session", return_value=s), \
             patch("kite_auth.pyotp.TOTP") as mock_totp, \
             patch.dict(os.environ, _ENV):
            mock_totp.return_value.now.return_value = "999888"
            kite_auth.login()

        twofa_call = s.post.call_args_list[1]
        assert twofa_call[1]["data"]["twofa_value"] == "999888"
        assert twofa_call[1]["data"]["twofa_type"] == "totp"

    def test_bad_credentials_raises(self):
        s = MagicMock()
        s.get.return_value = MagicMock()
        bad_r = MagicMock()
        bad_r.json.return_value = {"status": "error", "message": "Invalid credentials"}
        s.post.return_value = bad_r

        with patch("kite_auth.requests.Session", return_value=s), \
             patch("kite_auth.pyotp.TOTP") as mock_totp, \
             patch.dict(os.environ, _ENV):
            mock_totp.return_value.now.return_value = "123456"
            with pytest.raises(RuntimeError, match="Login failed"):
                kite_auth.login()

    def test_bad_twofa_raises(self):
        s = _mock_session()
        bad_twofa_r = MagicMock()
        bad_twofa_r.json.return_value = {"status": "error", "message": "Invalid TOTP"}
        login_r, _ = list(s.post.side_effect)
        s.post.side_effect = [login_r, bad_twofa_r]

        with patch("kite_auth.requests.Session", return_value=s), \
             patch("kite_auth.pyotp.TOTP") as mock_totp, \
             patch.dict(os.environ, _ENV):
            mock_totp.return_value.now.return_value = "000000"
            with pytest.raises(RuntimeError, match="Twofa failed"):
                kite_auth.login()

    def test_missing_enctoken_raises(self):
        s = _mock_session()
        s.cookies.get.return_value = None  # no enctoken set

        with patch("kite_auth.requests.Session", return_value=s), \
             patch("kite_auth.pyotp.TOTP") as mock_totp, \
             patch.dict(os.environ, _ENV):
            mock_totp.return_value.now.return_value = "123456"
            with pytest.raises(RuntimeError, match="No enctoken"):
                kite_auth.login()

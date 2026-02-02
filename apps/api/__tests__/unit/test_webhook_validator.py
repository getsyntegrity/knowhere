
import pytest
from unittest.mock import patch
from shared.services.webhook.validator import validate_webhook_url

@pytest.mark.parametrize("url,expected_valid,error_fragment", [
    ("https://example.com/webhook", True, None),
    ("http://example.com/webhook", False, "Must be HTTPS"),
    ("ftp://example.com", False, "Invalid scheme"),
    ("https://", False, "URL must have a hostname"),
])
def test_validation_scheme_basic(url, expected_valid, error_fragment):
    with patch("shared.services.webhook.validator.app_config") as mock_config:
        # Default to production for these tests
        mock_config.ENVIRONMENT = "production"
        
        is_valid, error = validate_webhook_url(url)
        assert is_valid == expected_valid
        if error_fragment:
            assert error and error_fragment in error

@patch("shared.services.webhook.validator.app_config")
def test_validation_dev_mode(mock_config):
    # Test DEV mode allows http
    mock_config.ENVIRONMENT = "development"
    is_valid, error = validate_webhook_url("http://example.com/webhook")
    assert is_valid is True
    assert error is None

@patch("socket.gethostbyname")
@patch("ipaddress.ip_address")
def test_validation_ssrf_blocking(mock_ip_address, mock_gethost, monkeypatch):
    # Mock DNS resolution
    mock_gethost.return_value = "127.0.0.1"
    
    # Mock IP address object to simulate private/loopback
    mock_ip = mock_ip_address.return_value
    mock_ip.is_loopback = True
    mock_ip.is_private = False
    
    is_valid, error = validate_webhook_url("https://localhost/webhook")
    assert is_valid is False
    assert "Loopback" in error

    # Test Private
    mock_ip.is_loopback = False
    mock_ip.is_private = True
    is_valid, error = validate_webhook_url("https://internal/webhook")
    assert is_valid is False
    assert "Private" in error

    # Test Good IP
    mock_ip.is_loopback = False
    mock_ip.is_private = False
    mock_ip.is_link_local = False
    mock_ip.is_multicast = False
    mock_ip.is_reserved = False
    
    is_valid, error = validate_webhook_url("https://google.com/webhook")
    assert is_valid is True
    assert error is None

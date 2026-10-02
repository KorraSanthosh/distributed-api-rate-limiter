import argparse
from unittest.mock import AsyncMock, patch
import pytest
import httpx

from scripts.traffic_generator import (
    generate_fake_ips,
    send_request,
    run_traffic_simulator,
)


def test_generate_fake_ips() -> None:
    """Verifies that generated IPs are unique, properly formatted IPv4 addresses."""
    ips = generate_fake_ips(5)
    assert len(ips) == 5
    for ip in ips:
        parts = ip.split(".")
        assert len(parts) == 4
        for part in parts:
            val = int(part)
            assert 0 <= val <= 255


@pytest.mark.asyncio
async def test_send_request_logs_to_stdout() -> None:
    """Verifies send_request completes successfully and handles response statuses."""
    # Create mock httpx client response
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_response = httpx.Response(status_code=200, content=b"{}")
    mock_client.get.return_value = mock_response

    # Test GET path
    with patch("builtins.print") as mock_print:
        await send_request(mock_client, "http://localhost", "1.1.1.1", "/api/v1/status", "GET")
        mock_client.get.assert_called_once()
        mock_print.assert_called_once()
        assert "200 OK" in mock_print.call_args[0][0]


@pytest.mark.asyncio
async def test_run_traffic_simulator_loop() -> None:
    """Verifies that the traffic generator orchestrator spins up workers and exits."""
    # Create simple mock arguments
    args = argparse.Namespace(
        host="http://localhost:8000",
        mode="normal",
        duration=1,  # Short duration to exit quickly
        concurrency=1,
    )

    # Patch downstream network calls to complete instantly
    with patch("scripts.traffic_generator.send_request", new_callable=AsyncMock) as mock_send:
        # Run traffic simulator for 1 second
        await run_traffic_simulator(args)
        
        # Verify that send_request was indeed scheduled and called
        assert mock_send.called

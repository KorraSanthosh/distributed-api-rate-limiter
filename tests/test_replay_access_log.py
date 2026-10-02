import gzip
import ipaddress

from scripts.replay_access_log import ROUTES, client_ip, map_route, parse_line, read_entries

GOOD = '199.72.81.55 - - [01/Jul/1995:00:00:01 -0400] "GET /history/apollo/ HTTP/1.0" 200 6245'
HOSTNAME = 'unicomp6.unicomp.net - - [01/Jul/1995:00:00:06 -0400] "GET /shuttle/countdown/ HTTP/1.0" 200 3985'


def test_parse_line_extracts_fields() -> None:
    entry = parse_line(GOOD)
    assert entry is not None
    assert entry.host == "199.72.81.55"
    assert entry.method == "GET"
    assert entry.path == "/history/apollo/"
    # 01/Jul/1995 00:00:01 -0400 == 04:00:01 UTC
    assert entry.timestamp == 804571201.0


def test_parse_line_rejects_malformed() -> None:
    assert parse_line("garbage") is None
    assert parse_line('host - - [bad-date] "GET / HTTP/1.0" 200 1') is None


def test_map_route_is_stable_and_valid() -> None:
    assert map_route("/history/apollo/") == map_route("/history/apollo/")
    assert {map_route(f"/p/{i}") for i in range(200)} == set(ROUTES)  # all routes get used


def test_client_ip_keeps_public_ips() -> None:
    assert client_ip("199.72.81.55") == "199.72.81.55"


def test_client_ip_maps_hostnames_and_private_ips_to_benchmark_range() -> None:
    bench = ipaddress.ip_network("198.18.0.0/15")
    for host in ("unicomp6.unicomp.net", "10.1.2.3", "192.168.0.9", "127.0.0.1"):
        ip = client_ip(host)
        assert ipaddress.ip_address(ip) in bench
        assert client_ip(host) == ip  # stable per host


def test_read_entries_slices_and_skips_bad_lines(tmp_path) -> None:
    log = tmp_path / "access.log.gz"
    with gzip.open(log, "wt") as fh:
        fh.write("\n".join([GOOD, "garbage line", HOSTNAME, GOOD]) + "\n")
    entries = list(read_entries(str(log), start=1, count=2))
    assert [e.host for e in entries] == ["unicomp6.unicomp.net", "199.72.81.55"]  # bad line skipped

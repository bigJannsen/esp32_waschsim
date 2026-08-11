"""Lokale Mock-Tests fuer die Produktionslogik des NetworkManager."""

import asyncio

from network_manager import NetworkManager


class FakeWLAN:
    def __init__(self, name, events, connected_after=None, ip="192.168.4.1", activation_ok=True):
        self.name = name
        self.events = events
        self.connected_after = connected_after
        self.ip = ip
        self.activation_ok = activation_ok
        self.active_state = False
        self.connect_calls = 0
        self.status_polls = 0
        self.ifconfig_error = None

    def active(self, value=None):
        if value is None:
            return self.active_state
        self.events.append((self.name, "active", value))
        self.active_state = bool(value) and self.activation_ok

    def config(self, **kwargs):
        self.events.append((self.name, "config", kwargs))

    def connect(self, ssid, password):
        self.connect_calls += 1
        self.events.append((self.name, "connect", ssid, password))

    def disconnect(self):
        self.events.append((self.name, "disconnect"))

    def isconnected(self):
        self.status_polls += 1
        return self.connected_after is not None and self.status_polls > self.connected_after

    def ifconfig(self):
        if self.ifconfig_error:
            raise self.ifconfig_error
        return (self.ip, "255.255.255.0", self.ip, self.ip)


class FakeNetwork:
    AP_IF = 1
    STA_IF = 0
    AUTH_WPA2_PSK = 3

    def __init__(self, sta=None, ap=None):
        self.events = []
        self.sta = sta or FakeWLAN("sta", self.events)
        self.ap = ap or FakeWLAN("ap", self.events)

    def WLAN(self, interface):
        self.events.append(("network", "WLAN", interface))
        return self.sta if interface == self.STA_IF else self.ap


def manager(network, **kwargs):
    return NetworkManager(
        sta_ssid="test-sta",
        sta_passwort="test-passwort",
        network_backend=network,
        asyncio_backend=asyncio,
        poll_ms=1,
        wlan_timeout_s=0.003,
        **kwargs
    )


def run(awaitable):
    return asyncio.run(awaitable)


def test_sta_sofort_erfolgreich():
    network = FakeNetwork()
    network.sta.connected_after = 0
    network.sta.ip = "10.0.0.10"
    status = run(manager(network).verbinde_wlan())
    assert status == {"ok": True, "mode": "station", "ssid": "test-sta", "ip": "10.0.0.10"}


def test_sta_nach_mehreren_polls_erfolgreich():
    network = FakeNetwork()
    network.sta.connected_after = 3
    network.sta.ip = "10.0.0.11"
    status = run(manager(network).verbinde_wlan())
    assert status["mode"] == "station"
    assert network.sta.status_polls == 4


def test_nicht_erreichbare_ssid_startet_ap_nach_timeout():
    network = FakeNetwork()
    status = run(manager(network).verbinde_oder_starte_ap())
    assert status["ok"] is True
    assert status["mode"] == "access_point"
    assert status["sta_error"]["error"] == "STA_TIMEOUT"
    assert network.sta.active_state is False


def test_connect_exception_startet_ap_fallback():
    network = FakeNetwork()

    def connect_fehler(ssid, password):
        raise OSError("connect kaputt")

    network.sta.connect = connect_fehler
    status = run(manager(network).verbinde_oder_starte_ap())
    assert status["mode"] == "access_point"
    assert status["sta_error"]["error"] == "STA_CONNECT_ERROR"


def test_sta_ifconfig_problem_wird_sauber_behandelt():
    network = FakeNetwork()
    network.sta.connected_after = 0
    network.sta.ifconfig_error = OSError("keine Konfiguration")
    status = run(manager(network).verbinde_oder_starte_ap())
    assert status["mode"] == "access_point"
    assert status["sta_error"]["error"] == "STA_STATUS_ERROR"


def test_ap_startet_mit_gueltiger_ip_und_bewaehrter_reihenfolge():
    network = FakeNetwork()
    status = run(manager(network).starte_access_point())
    assert status["ip"] == "192.168.4.1"
    ap_events = [event for event in network.events if event[0] == "ap"]
    assert ap_events[0] == ("ap", "active", True)
    assert ap_events[1][1] == "config"
    assert ap_events[1][2]["authmode"] == network.AUTH_WPA2_PSK


def test_ap_kann_nicht_aktiviert_werden():
    network = FakeNetwork()
    network.ap.activation_ok = False
    status = run(manager(network).starte_access_point())
    assert status["ok"] is False
    assert status["error"] == "AP_START_ERROR"


def test_sta_und_ap_fehlgeschlagen_liefert_keinen_bereit_status():
    network = FakeNetwork()
    network.ap.activation_ok = False
    status = run(manager(network).verbinde_oder_starte_ap())
    assert status["ok"] is False
    assert status["mode"] is None
    assert status["error"] == "NETWORK_UNAVAILABLE"
    assert status["sta_error"]["ok"] is False
    assert status["ap_error"]["ok"] is False


def test_legacy_ap_verwendet_sta_ueberhaupt_nicht():
    network = FakeNetwork()
    status = run(manager(network).starte("legacy_ap"))
    assert status["mode"] == "access_point"
    assert ("network", "WLAN", network.STA_IF) not in network.events


def test_auto_versucht_sta_vor_ap():
    network = FakeNetwork()
    status = run(manager(network).starte("auto"))
    assert status["mode"] == "access_point"
    sta_connect = next(i for i, event in enumerate(network.events) if event[0:2] == ("sta", "connect"))
    ap_start = next(i for i, event in enumerate(network.events) if event == ("ap", "active", True))
    assert sta_connect < ap_start


def test_ungueltige_ip_fuehrt_zum_fallback():
    network = FakeNetwork()
    network.sta.connected_after = 0
    network.sta.ip = "0.0.0.0"
    status = run(manager(network).starte("auto"))
    assert status["mode"] == "access_point"
    assert status["sta_error"]["error"] == "STA_STATUS_ERROR"

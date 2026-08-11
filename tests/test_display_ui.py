import pytest

from display import DisplayManager
from tests.fake_ssd1306 import FakeSSD1306


class Clock:
    def __init__(self):
        self.now = 0

    def ticks_ms(self):
        return self.now

    def ticks_diff(self, newer, older):
        return newer - older

    def advance(self, milliseconds):
        self.now += milliseconds


@pytest.fixture
def ui():
    display = FakeSSD1306()
    clock = Clock()
    return DisplayManager(display, clock), display, clock


def test_bootscreen_und_dirty_rendering(ui):
    manager, display, _ = ui
    assert "Miele & Cie.KG" in display.content()
    assert "ESP-Waschsim" in display.content()
    frames = len(display.frames)
    manager.update()
    assert len(display.frames) == frames


def test_wlan_und_access_point(ui):
    manager, display, clock = ui
    clock.advance(5000); manager.update()
    manager.wlan_connecting()
    assert "verbindet" in display.content()
    manager.access_point()
    assert "Access Point" in display.content()
    assert "verbinden" in display.content()


def test_basis_enthaelt_alle_fertigen_werte(ui):
    manager, display, _ = ui
    manager.basisanzeige(25.0, 60.0, 1200.0, 122.3, None)
    text = display.content()
    for expected in ("Heizung: --", "T1: 25.0", "T2: 60.0", "1200.0 Pa", "122.3 mmWS"):
        assert expected in text


@pytest.mark.parametrize("payload", [
    {"mode": "same", "temperature_1_c": 25.0, "temperature_2_c": 25.0},
    {"mode": "separate", "temperature_1_c": 25.0, "temperature_2_c": 60.0},
    {"mode": "single", "channel": 1, "temperature_1_c": 30.0, "temperature_2_c": 60.0},
    {"mode": "single", "channel": 2, "temperature_1_c": 25.0, "temperature_2_c": 30.0},
])
def test_ntc_update_zeigt_stets_beide_kanaele(ui, payload):
    manager, display, _ = ui
    manager.ntc_update(payload)
    assert "NTC1: {}".format(payload["temperature_1_c"]) in display.content()
    assert "NTC2: {}".format(payload["temperature_2_c"]) in display.content()


@pytest.mark.parametrize("event,duration,state", [
    ("ntc", 10000, DisplayManager.NTC_UPDATE),
    ("pressure", 10000, DisplayManager.DRUCK_UPDATE),
    ("status", 15000, DisplayManager.STATUS),
])
def test_temporaere_seiten_laufen_ohne_sleep_ab(ui, event, duration, state):
    manager, _, clock = ui
    if event == "ntc":
        manager.ntc_update({"temperature_1_c": 1.0, "temperature_2_c": 2.0})
    elif event == "pressure":
        manager.druck_update({"pressure_pa": 100.0, "pressure_mmws": 10.2})
    else:
        manager.statusanzeige({"ok": True, "hardware": {}, "pressure_mmws": 0.0})
    assert manager.hole_zustand() == state
    clock.advance(duration); manager.update()
    assert manager.hole_zustand() == DisplayManager.BASIS


def test_neues_event_ersetzt_temporaere_seite_heizung_aber_nicht(ui):
    manager, _, _ = ui
    manager.ntc_update({"temperature_1_c": 1.0, "temperature_2_c": 2.0})
    manager.aktualisiere_basiswerte(1.0, 2.0, 0.0, 0.0, True)
    assert manager.hole_zustand() == DisplayManager.NTC_UPDATE
    manager.druck_update({"pressure_pa": 100.0, "pressure_mmws": 10.2})
    assert manager.hole_zustand() == DisplayManager.DRUCK_UPDATE


def test_status_enthaelt_systemdaten(ui):
    manager, display, _ = ui
    manager.statusanzeige({
        "ok": True, "api_version": "v1", "backend": "real",
        "pressure_mmws": 122.3,
        "hardware": {"temperature_1_c": 25.0, "temperature_2_c": 60.0, "pressure_pa": 1200.0},
    })
    text = display.content()
    assert "Status: ok" in text and "real API:v1" in text and "122.3 mmWS" in text

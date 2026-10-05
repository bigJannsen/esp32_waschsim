"""Tests fuer Persistenz, Safe-State und optionale Hardware."""

import json
import sys
import types
from hardware import HardwareAbstraktion, _RealBackend


class _FakePin:
    IN = 0
    OUT = 1
    PULL_UP = 2
    werte = {}
    initialisierungen = []

    def __init__(self, gpio, mode=None, pull=None):
        self.gpio = gpio
        self.initialisierungen.append((gpio, mode, pull))

    def value(self, wert=None):
        if wert is not None:
            self.werte[self.gpio] = wert
        return self.werte.get(self.gpio, 1)


class _FakeSPI:
    def __init__(self, *args, **kwargs):
        pass

    def write(self, data):
        pass


class _FakePWM:
    def __init__(self, pin):
        pass

    def freq(self, value):
        pass

    def duty_u16(self, value):
        pass


def _hardware_mit_fake_machine(monkeypatch, tmp_path):
    _FakePin.werte = {}
    _FakePin.initialisierungen = []
    machine = types.SimpleNamespace(Pin=_FakePin, SPI=_FakeSPI, PWM=_FakePWM)
    monkeypatch.setitem(sys.modules, "machine", machine)
    monkeypatch.chdir(tmp_path)
    return HardwareAbstraktion()


def test_relaiseingaenge_nutzen_korrekte_pins_und_pullup(monkeypatch, tmp_path):
    hardware = _hardware_mit_fake_machine(monkeypatch, tmp_path)
    assert _RealBackend.HEIZUNG_GPIO == 27
    assert _RealBackend.FRIWA_GPIO == 26
    assert _FakePin.initialisierungen.count((27, _FakePin.IN, _FakePin.PULL_UP)) == 1
    assert _FakePin.initialisierungen.count((26, _FakePin.IN, _FakePin.PULL_UP)) == 1
    assert hardware.hat_heizungseingang() is True
    assert hardware.hat_friwa_eingang() is True


def test_relaiseingaenge_sind_active_low_und_im_status(monkeypatch, tmp_path):
    hardware = _hardware_mit_fake_machine(monkeypatch, tmp_path)
    _FakePin.werte.update({27: 1, 26: 1})
    assert hardware.ist_heizung_aktiv() is False
    assert hardware.ist_friwa_aktiv() is False

    _FakePin.werte.update({27: 0, 26: 0})
    assert hardware.ist_heizung_aktiv() is True
    assert hardware.ist_friwa_aktiv() is True
    status = hardware.lese_status()
    assert status["heizung_aktiv"] is True
    assert status["friwa_aktiv"] is True


def test_relaiseingaenge_ohne_machine_sind_neutral(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    hardware = HardwareAbstraktion()
    assert hardware.ist_heizung_aktiv() is False
    assert hardware.ist_friwa_aktiv() is False
    assert hardware.hat_heizungseingang() is False
    assert hardware.hat_friwa_eingang() is False


def test_persistenz_getrennt_und_safe_state_unveraendert(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    hardware = HardwareAbstraktion()
    hardware.setze_ntc_zustand(1, 25.0, 61)
    hardware.setze_ntc_zustand(2, 60.0, 16)
    hardware.setze_druck_zustand(1200.0, 0.5594274061990212)
    vorher = hardware.lese_status()
    hardware.setze_sicheren_zustand()
    assert hardware.lese_status() == vorher
    with open("config.json", encoding="utf-8") as datei:
        gespeichert = json.load(datei)
    assert gespeichert["temperature_1_c"] == 25.0
    assert gespeichert["temperature_2_c"] == 60.0
    assert gespeichert["ntc_code_1"] == 61
    assert gespeichert["ntc_code_2"] == 16
    assert gespeichert["pressure_pa"] == 1200.0


def test_neustart_laesst_persistierte_fachdaten_bestehen(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    hardware = HardwareAbstraktion()
    hardware.setze_ntc_zustand(None, 25.0, 61)
    hardware.setze_druck_zustand(1200.0, 0.5)
    neu = HardwareAbstraktion()
    neu.setze_sicheren_zustand()
    status = neu.lese_status()
    assert status["temperature_1_c"] == status["temperature_2_c"] == 25.0
    assert status["ntc_code_1"] == status["ntc_code_2"] == 61
    assert status["pressure_pa"] == 1200.0
    assert status["pwm_duty"] == 0.5

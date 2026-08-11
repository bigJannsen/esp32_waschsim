"""Tests fuer Persistenz, Safe-State und optionale Hardware."""

import json
from hardware import HardwareAbstraktion, _RealBackend


def test_heizung_ohne_dokumentierten_pin_neutral():
    assert _RealBackend.HEIZUNG_GPIO is None
    assert HardwareAbstraktion().ist_heizung_aktiv() is False


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

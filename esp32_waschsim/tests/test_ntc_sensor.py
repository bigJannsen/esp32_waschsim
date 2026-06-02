"""Unit-Tests fuer NtcSensor mit deterministischer Mock-Hardware."""

import pytest

from mock_hardware import MockHardware
from sensors import NtcSensor


def test_ntc_25_grad_schreibt_auf_beide_digipots():
    hardware = MockHardware()
    sensor = NtcSensor(hardware)

    code = sensor.verarbeite_temperatur(25.0)

    assert isinstance(code, int)
    assert hardware.letzter_ntc_code_kanal_1 == code
    assert hardware.letzter_ntc_code_kanal_2 == code
    assert hardware.letzter_ntc_code == code


def test_ntc_grenzwert_0_grad():
    hardware = MockHardware()
    sensor = NtcSensor(hardware)

    code = sensor.verarbeite_temperatur(0.0)

    assert isinstance(code, int)
    assert hardware.letzter_ntc_code_kanal_1 == code
    assert hardware.letzter_ntc_code_kanal_2 == code


def test_ntc_grenzwert_100_grad():
    hardware = MockHardware()
    sensor = NtcSensor(hardware)

    code = sensor.verarbeite_temperatur(100.0)

    assert isinstance(code, int)
    assert hardware.letzter_ntc_code_kanal_1 == code
    assert hardware.letzter_ntc_code_kanal_2 == code


def test_ntc_mittelwert_40_grad():
    hardware = MockHardware()
    sensor = NtcSensor(hardware)

    code = sensor.verarbeite_temperatur(40.0)

    assert isinstance(code, int)
    assert hardware.letzter_ntc_code_kanal_1 == code
    assert hardware.letzter_ntc_code_kanal_2 == code


@pytest.mark.parametrize("ungueltig", [True, False])
def test_ntc_bool_ungueltig(ungueltig):
    sensor = NtcSensor(MockHardware())

    with pytest.raises(ValueError):
        sensor.verarbeite_temperatur(ungueltig)


def test_ntc_int_derzeit_ungueltig():
    sensor = NtcSensor(MockHardware())

    with pytest.raises(ValueError):
        sensor.verarbeite_temperatur(25)

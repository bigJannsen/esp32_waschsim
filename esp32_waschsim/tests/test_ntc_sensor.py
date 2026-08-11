"""Unit-Tests fuer NtcSensor mit deterministischer Mock-Hardware."""

import pytest
from mock_hardware import MockHardware
from sensors import NtcSensor


@pytest.mark.parametrize("temperatur", [0, 25.0, 100])
def test_ntc_grenz_und_stuetzwerte_aktualisieren_beide_kanaele(temperatur):
    hardware = MockHardware()
    code = NtcSensor(hardware).verarbeite_temperatur(temperatur)
    assert isinstance(code, int)
    assert hardware.temperature_1_c == float(temperatur)
    assert hardware.temperature_2_c == float(temperatur)
    assert hardware.letzter_ntc_code_kanal_1 == code
    assert hardware.letzter_ntc_code_kanal_2 == code


@pytest.mark.parametrize("ungueltig", [True, False, -0.1, 100.1, "25"])
def test_ntc_ungueltige_werte(ungueltig):
    with pytest.raises(ValueError):
        NtcSensor(MockHardware()).verarbeite_temperatur(ungueltig)


def test_ntc_einzelkanal_laesst_anderen_unveraendert():
    hardware = MockHardware()
    sensor = NtcSensor(hardware)
    sensor.verarbeite_temperatur(25, channel=1)
    code_1 = hardware.letzter_ntc_code_kanal_1
    sensor.verarbeite_temperatur(60, channel=2)
    assert hardware.letzter_ntc_code_kanal_1 == code_1
    assert hardware.temperature_1_c == 25.0
    assert hardware.temperature_2_c == 60.0

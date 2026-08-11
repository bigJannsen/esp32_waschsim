"""Unit-Tests fuer PressureSensor mit deterministischer Mock-Hardware."""

import pytest
from mock_hardware import MockHardware
from sensors import PressureSensor


@pytest.mark.parametrize("druck,erwartet", [(0, 0.233), (2452.0, 0.900)])
def test_pressure_grenzwerte(druck, erwartet):
    hardware = MockHardware()
    duty = PressureSensor(hardware).verarbeite_druck_pa(druck)
    assert duty == erwartet
    assert hardware.pressure_pa == float(druck)
    assert hardware.letztes_pwm_duty == duty


def test_pressure_mittelwert():
    duty = PressureSensor(MockHardware()).verarbeite_druck_pa(1200)
    assert PressureSensor.DUTY_MIN_NORM < duty < PressureSensor.DUTY_MAX_NORM


def test_pressure_pa_zu_mmws():
    assert PressureSensor(MockHardware()).berechne_druck_mmws(981) == pytest.approx(100.0)


@pytest.mark.parametrize("ungueltig", [True, False, -0.1, 2452.1, "1200"])
def test_pressure_ungueltige_werte(ungueltig):
    with pytest.raises(ValueError):
        PressureSensor(MockHardware()).verarbeite_druck_pa(ungueltig)

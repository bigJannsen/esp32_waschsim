"""Unit-Tests fuer PressureSensor mit deterministischer Mock-Hardware."""

import pytest

from mock_hardware import MockHardware
from sensors import PressureSensor


def test_pressure_minimum():
    hardware = MockHardware()
    sensor = PressureSensor(hardware)

    duty = sensor.verarbeite_druck_pa(0.0)

    assert duty == PressureSensor.DUTY_MIN_NORM
    assert hardware.letztes_pwm_duty == duty


def test_pressure_maximum():
    hardware = MockHardware()
    sensor = PressureSensor(hardware)

    duty = sensor.verarbeite_druck_pa(2452.0)

    assert duty == PressureSensor.DUTY_MAX_NORM
    assert hardware.letztes_pwm_duty == duty


def test_pressure_mittelwert():
    hardware = MockHardware()
    sensor = PressureSensor(hardware)

    duty = sensor.verarbeite_druck_pa(1200.0)

    assert PressureSensor.DUTY_MIN_NORM <= duty <= PressureSensor.DUTY_MAX_NORM
    assert hardware.letztes_pwm_duty == duty


def test_pressure_bool_ungueltig():
    sensor = PressureSensor(MockHardware())

    with pytest.raises(ValueError):
        sensor.verarbeite_druck_pa(True)


def test_pressure_int_derzeit_ungueltig():
    sensor = PressureSensor(MockHardware())

    with pytest.raises(ValueError):
        sensor.verarbeite_druck_pa(1200)


@pytest.mark.parametrize("ungueltig", [-0.1, 2452.1])
def test_pressure_ausserhalb_bereich(ungueltig):
    sensor = PressureSensor(MockHardware())

    with pytest.raises(ValueError):
        sensor.verarbeite_druck_pa(ungueltig)

"""Tests fuer das zentrale, einmalige Polling der digitalen Eingaenge."""

from main import SystemAnwendung


class _HardwareMitEingaengen:
    def __init__(self):
        self.status_aufrufe = 0

    def lese_status(self):
        self.status_aufrufe += 1
        return {
            "temperature_1_c": 25.0,
            "temperature_2_c": 60.0,
            "pressure_pa": 981.0,
            "heizung_aktiv": True,
            "friwa_aktiv": True,
        }

    def hat_heizungseingang(self):
        return True

    def hat_friwa_eingang(self):
        return True


class _DisplayRecorder:
    def __init__(self):
        self.werte = None
        self.update_aufrufe = 0

    def aktualisiere_basiswerte(self, *werte):
        self.werte = werte

    def update(self):
        self.update_aufrufe += 1


def test_systemaktualisierung_verwendet_gemeinsamen_hardwarestatus():
    hardware = _HardwareMitEingaengen()
    app = SystemAnwendung.__new__(SystemAnwendung)
    app.hardware = hardware
    app.druck_sensor = type(
        "DruckDummy", (), {"berechne_druck_mmws": staticmethod(lambda pa: pa / 9.81)}
    )()
    app.display_manager = _DisplayRecorder()

    app._aktualisiere_basisdaten()

    assert hardware.status_aufrufe == 1
    assert app.display_manager.werte == (25.0, 60.0, 981.0, 100.0, True, True)
    assert app.display_manager.update_aufrufe == 1

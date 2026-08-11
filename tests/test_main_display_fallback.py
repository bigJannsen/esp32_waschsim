from main import SystemAnwendung


class HardwareOhneDisplay:
    def lese_status(self):
        return {
            "temperature_1_c": 0.0, "temperature_2_c": 0.0,
            "ntc_code_1": 0, "ntc_code_2": 0,
            "pressure_pa": 0.0, "pwm_duty": 0.0,
        }

    def initialisiere_hardware(self):
        pass

    def setze_sicheren_zustand(self):
        pass

    def initialisiere_display(self):
        raise OSError("OLED nicht erreichbar")


class NetzwerkDummy:
    pass


def test_fehlendes_oled_bricht_initialisierung_nicht_ab():
    app = SystemAnwendung(HardwareOhneDisplay(), NetzwerkDummy())
    app.initialisiere_hardware()
    assert app.display_manager is None

"""Hardware-nahe Abstraktionsschicht mit austauschbaren Backends."""

import json
import os


class _MockBackend:
    """Simuliertes Hardware-Backend ohne externe Abhaengigkeiten."""

    def __init__(self):
        """Erzeugt den initialen Mock-Zustand."""
        self.letzter_ntc_code = 0
        self.letzter_ntc_code_kanal_1 = 0
        self.letzter_ntc_code_kanal_2 = 0
        self.letztes_pwm_duty = 0.0

    def write_digipot(self, channel, code):
        """Speichert den Digipot-Code pro Kanal im Mock-Zustand."""
        if channel not in (1, 2):
            raise ValueError("channel muss 1 oder 2 sein")

        if code < 0:
            code = 0
        elif code > 255:
            code = 255

        if channel == 1:
            self.letzter_ntc_code_kanal_1 = code
        else:
            self.letzter_ntc_code_kanal_2 = code
        self.letzter_ntc_code = code

    def write_ntc_code(self, ntc_code):
        """Schreibt denselben NTC-Code auf beide simulierten Digipot-Kanaele."""
        self.write_digipot(1, ntc_code)
        self.write_digipot(2, ntc_code)

    def setze_ntc_code(self, ntc_code):
        """Kompatibilitaetsmethode fuer bestehende Aufrufe."""
        self.write_ntc_code(ntc_code)

    def setze_pwm_duty(self, duty):
        """Speichert den PWM-Duty im Mock-Zustand."""
        self.letztes_pwm_duty = duty


class _RealBackend:
    """Optionales Hardware-Backend fuer echte Peripherieobjekte."""

    DIGIPOT_CS_1 = 5
    DIGIPOT_CS_2 = 18
    DIGIPOT_SPI_ID = 1
    DIGIPOT_SPI_BAUDRATE = 1_000_000
    DIGIPOT_SPI_SCK = 14
    DIGIPOT_SPI_MOSI = 13
    DIGIPOT_SPI_MISO = 12
    DIGIPOT_WRITE_WIPER_0 = 0x00

    def __init__(self, **konfiguration):
        """Initialisiert das reale Backend mit externer Konfiguration."""
        try:
            machine = __import__("machine")
        except ImportError:
            machine = None

        self._machine = machine

        self._ntc_code_setzer = konfiguration.get("ntc_code_setzer")
        self._pwm_setzer = konfiguration.get("pwm_setzer")

        if self._ntc_code_setzer is not None and not callable(self._ntc_code_setzer):
            raise ValueError("ntc_code_setzer muss aufrufbar sein")
        if self._pwm_setzer is not None and not callable(self._pwm_setzer):
            raise ValueError("pwm_setzer muss aufrufbar sein")

        self.letzter_ntc_code = 0
        self.letzter_ntc_code_kanal_1 = 0
        self.letzter_ntc_code_kanal_2 = 0
        self.letztes_pwm_duty = 0.0

        self._spi = None
        self._digipot_cs_1 = None
        self._digipot_cs_2 = None

        if self._machine is not None:
            self._spi = machine.SPI(
                self.DIGIPOT_SPI_ID,
                baudrate=self.DIGIPOT_SPI_BAUDRATE,
                polarity=0,
                phase=0,
                sck=machine.Pin(self.DIGIPOT_SPI_SCK),
                mosi=machine.Pin(self.DIGIPOT_SPI_MOSI),
                miso=machine.Pin(self.DIGIPOT_SPI_MISO),
            )
            self._digipot_cs_1 = machine.Pin(self.DIGIPOT_CS_1, machine.Pin.OUT)
            self._digipot_cs_2 = machine.Pin(self.DIGIPOT_CS_2, machine.Pin.OUT)
            self._digipot_cs_1.value(1)
            self._digipot_cs_2.value(1)

    @staticmethod
    def _clamp_code(code):
        """Begrenzt den Digipot-Code auf den gueltigen MCP4161-Bereich."""
        if code < 0:
            return 0
        if code > 255:
            return 255
        return code

    def write_digipot(self, channel, code):
        """Schreibt einen Digipot-Code auf den ausgewaehlten MCP4161-Kanal."""
        if channel not in (1, 2):
            raise ValueError("channel muss 1 oder 2 sein")

        code = self._clamp_code(int(code))

        if channel == 1:
            self.letzter_ntc_code_kanal_1 = code
            cs_pin = self._digipot_cs_1
        else:
            self.letzter_ntc_code_kanal_2 = code
            cs_pin = self._digipot_cs_2

        if self._spi is not None and cs_pin is not None:
            cs_pin.value(0)
            self._spi.write(bytes((self.DIGIPOT_WRITE_WIPER_0, code)))
            cs_pin.value(1)

    def write_ntc_code(self, ntc_code):
        """Schreibt denselben NTC-Code auf beide MCP4161-Digipots."""
        code = self._clamp_code(int(ntc_code))
        if self._ntc_code_setzer is not None:
            self._ntc_code_setzer(code)
        self.write_digipot(1, code)
        self.write_digipot(2, code)
        self.letzter_ntc_code = code

    def setze_ntc_code(self, ntc_code):
        """Delegiert den NTC-Code an die konfigurierte reale Ausgabe."""
        self.write_ntc_code(ntc_code)

    def setze_pwm_duty(self, duty):
        """Delegiert den PWM-Duty an die konfigurierte reale Ausgabe."""
        if self._pwm_setzer is not None:
            self._pwm_setzer(duty)
        self.letztes_pwm_duty = duty


class HardwareAbstraktion:
    """Hardware-nahe Abstraktion fuer Aktor-Ausgaben."""

    _KONFIG_DATEINAME = "config.json"

    def __init__(self, backend="mock", **konfiguration):
        """Erzeugt die HardwareAbstraktion mit Mock- oder Real-Backend."""
        if backend == "mock":
            self._backend = _MockBackend()
        elif backend == "real":
            self._backend = _RealBackend(**konfiguration)
        else:
            raise ValueError("backend muss 'mock' oder 'real' sein")

        self._backend_name = backend
        self._persistenz_defaults = {
            "letzte_temperatur_c": 0.0,
            "letzter_ntc_code": 0,
            "letzter_druck_pa": 0.0,
            "letztes_pwm_duty": 0.0,
            "letzter_status_ok": True,
            "letzter_status_text": "OK",
        }
        self._persistenz_daten = dict(self._persistenz_defaults)
        self._letzte_gespeicherte_konfiguration = None

        geladene_konfiguration = self.lade_konfiguration()
        self.wende_konfiguration_an(geladene_konfiguration)

    def initialisiere_hardware(self):
        """Kompatibilitaetsmethode ohne Initialisierungsarbeit."""
        return None

    def konfiguriere_wlan_ap(self, ssid, passwort):
        """Kompatibilitaetsmethode fuer fruehere Stufen ohne WLAN-Implementierung."""
        _ = (ssid, passwort)
        return None

    def initialisiere_display(self):
        """Kompatibilitaetsmethode fuer fruehere Stufen ohne Display-Implementierung."""
        return None

    def _normalisiere_konfiguration(self, daten):
        """Validiert und normalisiert persistierte Konfigurationsdaten."""
        if not isinstance(daten, dict):
            raise ValueError("konfiguration muss ein dict sein")

        normalisiert = dict(self._persistenz_defaults)

        if "letzte_temperatur_c" in daten:
            if isinstance(daten["letzte_temperatur_c"], bool):
                raise ValueError("letzte_temperatur_c darf kein bool sein")
            normalisiert["letzte_temperatur_c"] = float(daten["letzte_temperatur_c"])

        if "letzter_ntc_code" in daten:
            if isinstance(daten["letzter_ntc_code"], bool):
                raise ValueError("letzter_ntc_code darf kein bool sein")
            normalisiert["letzter_ntc_code"] = int(daten["letzter_ntc_code"])

        if "letzter_druck_pa" in daten:
            if isinstance(daten["letzter_druck_pa"], bool):
                raise ValueError("letzter_druck_pa darf kein bool sein")
            normalisiert["letzter_druck_pa"] = float(daten["letzter_druck_pa"])

        if "letztes_pwm_duty" in daten:
            if isinstance(daten["letztes_pwm_duty"], bool):
                raise ValueError("letztes_pwm_duty darf kein bool sein")
            normalisiert["letztes_pwm_duty"] = float(daten["letztes_pwm_duty"])

        if "letzter_status_ok" in daten:
            if not isinstance(daten["letzter_status_ok"], bool):
                raise ValueError("letzter_status_ok muss bool sein")
            normalisiert["letzter_status_ok"] = daten["letzter_status_ok"]

        if "letzter_status_text" in daten:
            if not isinstance(daten["letzter_status_text"], str):
                raise ValueError("letzter_status_text muss str sein")
            normalisiert["letzter_status_text"] = daten["letzter_status_text"]

        if normalisiert["letzter_ntc_code"] < 0 or normalisiert["letzter_ntc_code"] > 255:
            raise ValueError("letzter_ntc_code muss im Bereich 0 bis 255 liegen")
        if normalisiert["letztes_pwm_duty"] < 0.0 or normalisiert["letztes_pwm_duty"] > 1.0:
            raise ValueError("letztes_pwm_duty muss im Bereich 0.0 bis 1.0 liegen")

        return normalisiert

    def lade_konfiguration(self):
        """Laedt und validiert die persistierte Konfiguration aus 'config.json'."""
        defaults = dict(self._persistenz_defaults)
        try:
            with open(self._KONFIG_DATEINAME, "r", encoding="utf-8") as datei:
                inhalt = json.load(datei)
            normalisiert = self._normalisiere_konfiguration(inhalt)
            self._letzte_gespeicherte_konfiguration = dict(normalisiert)
            return normalisiert
        except OSError:
            defaults["letzter_status_ok"] = False
            defaults["letzter_status_text"] = "Konfiguration fehlt"
            self._letzte_gespeicherte_konfiguration = None
            return defaults
        except (ValueError, TypeError):
            defaults["letzter_status_ok"] = False
            defaults["letzter_status_text"] = "Konfiguration ungueltig"
            self._letzte_gespeicherte_konfiguration = None
            return defaults

    def speichere_konfiguration(self, daten):
        """Speichert Konfigurationsdaten robust und flash-schonend."""
        try:
            normalisiert = self._normalisiere_konfiguration(daten)
        except (ValueError, TypeError):
            self._persistenz_daten["letzter_status_ok"] = False
            self._persistenz_daten["letzter_status_text"] = "Persistenzfehler"
            return None

        if normalisiert == self._letzte_gespeicherte_konfiguration:
            return None

        temp_datei = self._KONFIG_DATEINAME + ".tmp"
        try:
            with open(temp_datei, "w", encoding="utf-8") as datei:
                json.dump(normalisiert, datei)
            os.replace(temp_datei, self._KONFIG_DATEINAME)
            self._letzte_gespeicherte_konfiguration = dict(normalisiert)
        except OSError:
            self._persistenz_daten["letzter_status_ok"] = False
            self._persistenz_daten["letzter_status_text"] = "Persistenzfehler"
            try:
                os.remove(temp_datei)
            except OSError:
                pass

        return None

    def wende_konfiguration_an(self, daten):
        """Uebertraegt geladene Konfigurationswerte deterministisch in den Laufzeitzustand."""
        try:
            normalisiert = self._normalisiere_konfiguration(daten)
        except (ValueError, TypeError):
            normalisiert = dict(self._persistenz_defaults)
            normalisiert["letzter_status_ok"] = False
            normalisiert["letzter_status_text"] = "Konfiguration ungueltig"

        self._persistenz_daten = dict(normalisiert)
        self.setze_ntc_code(normalisiert["letzter_ntc_code"])
        self.setze_pwm_duty(normalisiert["letztes_pwm_duty"])

    def setze_ntc_code(self, ntc_code):
        """Setzt den NTC-Code mit strikt integerbasierter Validierung."""
        if isinstance(ntc_code, bool) or not isinstance(ntc_code, int):
            raise ValueError("ntc_code muss int sein")
        if ntc_code < 0 or ntc_code > 255:
            raise ValueError("ntc_code muss im Bereich 0 bis 255 liegen")

        self.write_ntc_code(ntc_code)
        self._persistenz_daten["letzter_ntc_code"] = ntc_code
        self._persistenz_daten["letzter_status_ok"] = True
        self._persistenz_daten["letzter_status_text"] = "OK"
        self.speichere_konfiguration(self._persistenz_daten)

    def write_digipot(self, channel, code):
        """Schreibt den Digipot-Code auf einen MCP4161-Kanal."""
        if channel not in (1, 2):
            raise ValueError("channel muss 1 oder 2 sein")
        if isinstance(code, bool) or not isinstance(code, int):
            raise ValueError("code muss int sein")
        if code < 0:
            code = 0
        elif code > 255:
            code = 255
        self._backend.write_digipot(channel, code)
        self._persistenz_daten["letzter_ntc_code"] = code

    def write_ntc_code(self, code):
        """Schreibt denselben Code auf beide MCP4161-Digipots."""
        if isinstance(code, bool) or not isinstance(code, int):
            raise ValueError("code muss int sein")
        if code < 0:
            code = 0
        elif code > 255:
            code = 255
        self._backend.write_ntc_code(code)

    def setze_pwm_duty(self, duty):
        """Setzt den normierten PWM-Duty-Wert als float."""
        if isinstance(duty, bool) or not isinstance(duty, float):
            raise ValueError("duty muss float sein")
        if duty < 0.0 or duty > 1.0:
            raise ValueError("duty muss im Bereich 0.0 bis 1.0 liegen")

        self._backend.setze_pwm_duty(duty)
        self._persistenz_daten["letztes_pwm_duty"] = duty
        self._persistenz_daten["letzter_status_ok"] = True
        self._persistenz_daten["letzter_status_text"] = "OK"
        self.speichere_konfiguration(self._persistenz_daten)

    def lese_status(self):
        """Liefert den diagnostischen Hardwarestatus ohne zusaetzliche I/O."""
        return {
            "backend": self._backend_name,
            "letzter_ntc_code": self._backend.letzter_ntc_code,
            "letztes_pwm_duty": self._backend.letztes_pwm_duty,
            "letzte_temperatur_c": self._persistenz_daten["letzte_temperatur_c"],
            "letzter_druck_pa": self._persistenz_daten["letzter_druck_pa"],
            "letzter_status_ok": self._persistenz_daten["letzter_status_ok"],
            "letzter_status_text": self._persistenz_daten["letzter_status_text"],
        }

    def setze_sicheren_zustand(self):
        """Setzt die Ausgaenge deterministisch auf einen sicheren Zustand."""
        self.setze_ntc_code(0)
        self.setze_pwm_duty(0.0)

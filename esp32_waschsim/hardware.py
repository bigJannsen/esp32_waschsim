# hardware.py
# Hardware-Abstraktionsschicht für GPIO, PWM und I2C.
# Alle direkten Hardwarezugriffe (Pins setzen, PWM initialisieren, I2C starten)
# werden ausschließlich hier umgesetzt. Keine fachliche Logik in diesem Modul.

"""Hardware-nahe Abstraktionsschicht fuer die produktive Laufzeit."""

import json
import os

try:
    from ssd1306 import SSD1306_I2C
except ImportError:
    SSD1306_I2C = None


class _RealBackend:
    """Hardware-Backend für Peripherie und E/A."""

    # NTC-Emulations-Pins für DigiPoti
    DIGIPOT_CS_1 = 5  # NTC1 Chip Select                     MCP4161 - Pin 1
    DIGIPOT_CS_2 = 18  # NTC2 Chip Select - Gelb             MCP4161 - Pin 1 NTC2
    DIGIPOT_SPI_ID = 1  # SPI Bus 1, nur für Software
    DIGIPOT_SPI_BAUDRATE = 1_000_000
    DIGIPOT_SPI_SCK = 19  # Gruen, Clock                     MCP4161 - Pin 2
    DIGIPOT_SPI_MOSI = 23  # Lila - Data zu Digipoti         MCP4161 - Pin 3
    DIGIPOT_SPI_MISO = 12  # Data von Digipoti, nicht benötigt
    DIGIPOT_CMD_WRITE_WIPER_0 = 0x00

    # "Taster"-Eingang für Heizung
    # Noch kein sicher dokumentierter Anwendungspin vorhanden.
    HEIZUNG_GPIO = None

    # PWM-Pins
    PWM_PIN = 25
    PWM_FREQ = 1000

    # Display-Pins
    DISPLAY_I2C_ID = 0
    DISPLAY_SDA = 21
    DISPLAY_SCL = 22
    DISPLAY_WIDTH = 128
    DISPLAY_HEIGHT = 64
    DISPLAY_FREQ = 400_000

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
        self._pwm = None
        self._heizung_pin = None
        self._display_i2c = None
        self._display = None

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

            self._pwm = machine.PWM(machine.Pin(self.PWM_PIN))
            self._pwm.freq(self.PWM_FREQ)
            self._pwm.duty_u16(0)

            # Heizungskontakt initialisieren
            if self.HEIZUNG_GPIO is not None:
                self._heizung_pin = machine.Pin(
                    self.HEIZUNG_GPIO, machine.Pin.IN, machine.Pin.PULL_UP
                )

            try:
                if SSD1306_I2C is None:
                    raise ImportError("ssd1306 nicht verfuegbar")
                self._display_i2c = machine.I2C(
                    self.DISPLAY_I2C_ID,
                    scl=machine.Pin(self.DISPLAY_SCL),
                    sda=machine.Pin(self.DISPLAY_SDA),
                    freq=self.DISPLAY_FREQ,
                )
                self._display = SSD1306_I2C(
                    self.DISPLAY_WIDTH,
                    self.DISPLAY_HEIGHT,
                    self._display_i2c,
                )
            except Exception:
                # Display ist optional; das System soll auch ohne OLED starten können.
                self._display_i2c = None
                self._display = None

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
            self._spi.write(bytes((self.DIGIPOT_CMD_WRITE_WIPER_0, code)))
            cs_pin.value(1)

    def _write_code_auf_beide_digipots(self, code):
        """Schreibt denselben NTC-Code auf beide MCP4161-Digipots."""
        self.write_digipot(1, code)
        self.write_digipot(2, code)
        self.letzter_ntc_code = code

    def write_ntc_code(self, ntc_code):
        """Schreibt denselben NTC-Code auf beide MCP4161-Digipots."""
        code = self._clamp_code(int(ntc_code))
        if self._ntc_code_setzer is not None:
            self._ntc_code_setzer(code)
        self._write_code_auf_beide_digipots(code)

    def setze_pwm_duty(self, duty):
        """Delegiert den PWM-Duty an die konfigurierte reale Ausgabe."""
        if self._pwm_setzer is not None:
            self._pwm_setzer(duty)

        if self._pwm is not None:
            duty_u16 = int(duty * 65535)
            self._pwm.duty_u16(duty_u16)

        self.letztes_pwm_duty = duty

    def ist_heizung_aktiv(self):
        """Liest den Heizungskontakt ein."""
        if self._heizung_pin is None:
            return False

        return self._heizung_pin.value() == 0

    def hole_display(self):
        """Liefert die initialisierte Displayinstanz."""
        return self._display


class HardwareAbstraktion:
    """Hardware-nahe Abstraktion fuer Aktor-Ausgaben."""

    _KONFIG_DATEINAME = "config.json"

    def __init__(self, backend="real", **konfiguration):
        """Erzeugt die HardwareAbstraktion fuer die produktive Laufzeit."""
        if backend != "real":
            raise ValueError("backend muss 'real' sein")

        self._backend = _RealBackend(**konfiguration)
        self._backend_name = backend
        self._persistenz_defaults = {
            "temperature_1_c": 0.0,
            "temperature_2_c": 0.0,
            "ntc_code_1": 0,
            "ntc_code_2": 0,
            "pressure_pa": 0.0,
            "pwm_duty": 0.0,
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
        """Liefert die Displayinstanz oder None, falls kein OLED verfuegbar ist."""
        return self._backend.hole_display()

    def _normalisiere_konfiguration(self, daten):
        """Validiert und normalisiert persistierte Konfigurationsdaten."""
        if not isinstance(daten, dict):
            raise ValueError("konfiguration muss ein dict sein")

        normalisiert = dict(self._persistenz_defaults)

        # Alte Ein-Kanal-Dateien werden kompatibel auf beide Kanaele abgebildet.
        legacy_temp = daten.get("letzte_temperatur_c")
        legacy_code = daten.get("letzter_ntc_code")
        aliases = {
            "temperature_1_c": legacy_temp,
            "temperature_2_c": legacy_temp,
            "ntc_code_1": legacy_code,
            "ntc_code_2": legacy_code,
            "pressure_pa": daten.get("letzter_druck_pa"),
            "pwm_duty": daten.get("letztes_pwm_duty"),
        }
        for name, legacy_wert in aliases.items():
            wert = daten.get(name, legacy_wert)
            if wert is None:
                continue
            if isinstance(wert, bool) or not isinstance(wert, (int, float)):
                raise ValueError("{} muss numerisch sein".format(name))
            normalisiert[name] = int(wert) if name.startswith("ntc_code_") else float(wert)

        if "letzter_status_ok" in daten:
            if not isinstance(daten["letzter_status_ok"], bool):
                raise ValueError("letzter_status_ok muss bool sein")
            normalisiert["letzter_status_ok"] = daten["letzter_status_ok"]

        if "letzter_status_text" in daten:
            if not isinstance(daten["letzter_status_text"], str):
                raise ValueError("letzter_status_text muss str sein")
            normalisiert["letzter_status_text"] = daten["letzter_status_text"]

        for name in ("ntc_code_1", "ntc_code_2"):
            if normalisiert[name] < 0 or normalisiert[name] > 255:
                raise ValueError("{} muss im Bereich 0 bis 255 liegen".format(name))
        for name in ("temperature_1_c", "temperature_2_c"):
            if normalisiert[name] < 0.0 or normalisiert[name] > 100.0:
                raise ValueError("{} muss im Bereich 0.0 bis 100.0 liegen".format(name))
        if normalisiert["pressure_pa"] < 0.0 or normalisiert["pressure_pa"] > 2452.0:
            raise ValueError("pressure_pa muss im Bereich 0.0 bis 2452.0 liegen")
        if normalisiert["pwm_duty"] < 0.0 or normalisiert["pwm_duty"] > 1.0:
            raise ValueError("pwm_duty muss im Bereich 0.0 bis 1.0 liegen")

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
            try:
                os.remove(self._KONFIG_DATEINAME)
            except OSError:
                pass
            os.rename(temp_datei, self._KONFIG_DATEINAME)
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

    def setze_ntc_code(self, ntc_code):
        """Schreibt kompatibilitaetshalber einen Code, ohne Fachdaten zu aendern."""
        if isinstance(ntc_code, bool) or not isinstance(ntc_code, int):
            raise ValueError("ntc_code muss int sein")
        if ntc_code < 0 or ntc_code > 255:
            raise ValueError("ntc_code muss im Bereich 0 bis 255 liegen")

        self._write_ntc_hardware(ntc_code)

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

    def setze_ntc_zustand(self, channel, temperatur_c, code):
        """Aktualisiert Hardware und persistierten fachlichen NTC-Zustand atomar."""
        channels = (1, 2) if channel is None else (channel,)
        if any(kanal not in (1, 2) for kanal in channels):
            raise ValueError("channel muss 1 oder 2 sein")
        if isinstance(temperatur_c, bool) or not isinstance(temperatur_c, (int, float)):
            raise ValueError("temperatur_c muss numerisch sein")
        if temperatur_c < 0.0 or temperatur_c > 100.0:
            raise ValueError("temperatur_c muss im Bereich 0.0 bis 100.0 liegen")
        if isinstance(code, bool) or not isinstance(code, int) or code < 0 or code > 255:
            raise ValueError("code muss int im Bereich 0 bis 255 sein")
        for kanal in channels:
            self.write_digipot(kanal, code)
            self._persistenz_daten["temperature_{}_c".format(kanal)] = float(temperatur_c)
            self._persistenz_daten["ntc_code_{}".format(kanal)] = int(code)
        self._backend.letzter_ntc_code = int(code)
        self._markiere_erfolgreich_und_speichere()

    def setze_druck_zustand(self, pressure_pa, duty):
        """Aktualisiert PWM-Hardware und persistierten fachlichen Druckzustand atomar."""
        if isinstance(pressure_pa, bool) or not isinstance(pressure_pa, (int, float)):
            raise ValueError("pressure_pa muss numerisch sein")
        if pressure_pa < 0.0 or pressure_pa > 2452.0:
            raise ValueError("pressure_pa muss im Bereich 0.0 bis 2452.0 liegen")
        if isinstance(duty, bool) or not isinstance(duty, (int, float)):
            raise ValueError("duty muss numerisch sein")
        if duty < 0.0 or duty > 1.0:
            raise ValueError("duty muss im Bereich 0.0 bis 1.0 liegen")
        self._write_pwm_hardware(duty)
        self._persistenz_daten["pressure_pa"] = float(pressure_pa)
        self._persistenz_daten["pwm_duty"] = float(duty)
        self._markiere_erfolgreich_und_speichere()

    def _markiere_erfolgreich_und_speichere(self):
        self._persistenz_daten["letzter_status_ok"] = True
        self._persistenz_daten["letzter_status_text"] = "OK"
        self.speichere_konfiguration(self._persistenz_daten)

    def _write_ntc_hardware(self, code):
        self._backend.write_ntc_code(code)

    def _write_pwm_hardware(self, duty):
        self._backend.setze_pwm_duty(duty)

    def setze_pwm_duty(self, duty):
        """Schreibt kompatibilitaetshalber den Duty, ohne Fachdaten zu aendern."""
        if isinstance(duty, bool) or not isinstance(duty, float):
            raise ValueError("duty muss float sein")
        if duty < 0.0 or duty > 1.0:
            raise ValueError("duty muss im Bereich 0.0 bis 1.0 liegen")

        self._write_pwm_hardware(duty)

    def ist_heizung_aktiv(self):
        """Gibt den Zustand des Heizungsrelais zurück."""
        return self._backend.ist_heizung_aktiv()

    def lese_status(self):
        """Liefert den diagnostischen Hardwarestatus ohne zusaetzliche I/O."""
        return {
            "backend": self._backend_name,
            "heizung_aktiv": self.ist_heizung_aktiv(),
            "temperature_1_c": self._persistenz_daten["temperature_1_c"],
            "temperature_2_c": self._persistenz_daten["temperature_2_c"],
            "ntc_code_1": self._persistenz_daten["ntc_code_1"],
            "ntc_code_2": self._persistenz_daten["ntc_code_2"],
            "pressure_pa": self._persistenz_daten["pressure_pa"],
            "pwm_duty": self._persistenz_daten["pwm_duty"],
            "letzter_status_ok": self._persistenz_daten["letzter_status_ok"],
            "letzter_status_text": self._persistenz_daten["letzter_status_text"],
        }

    def hole_display(self):
        """Liefert die Displayinstanz aus dem Backend."""
        return self._backend.hole_display()

    def setze_sicheren_zustand(self):
        """Setzt die Ausgaenge deterministisch auf einen sicheren Zustand."""
        self._write_ntc_hardware(0)
        self._write_pwm_hardware(0.0)

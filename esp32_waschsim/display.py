# display.py

# OLED-Displaymanager für den ESP32

# Dieses Modul enthält ausschließlich die komplette Darstellungslogik des SSD1306-Displays

# Das Display erhält bereits ein initialisiertes SSD1306_I2C-Objekt und besitzt keinerlei Kenntnis
# über Pins, I2C oder GPIOs

"""
Verantwortlichkeiten
--------------------
* Verwaltung aller Displayzustände
* Automatischer Rücksprung zur Basisanzeige
* Zeichnen aller Displayseiten
* Kapselung der SSD1306-Ausgabe
"""

try:
    import utime as time
except ImportError:
    import time


DISPLAY_BREITE = 128
DISPLAY_HOEHE = 64


class DisplayHelper:
    """
    Hilfsfunktionen für SSD1306-Texte

    SSD1306.text() verwendet standardmäßig ein 8x8-Pixel-Zeichenraster
    Bei 128 Pixel Breite passen somit maximal 16 Zeichen pro Zeile
    """

    CHAR_WIDTH = 8
    DISPLAY_WIDTH = DISPLAY_BREITE

    @classmethod
    def max_chars(cls):
        return cls.DISPLAY_WIDTH // cls.CHAR_WIDTH

    @classmethod
    def fit(cls, text):
        """
        Kürzt Text automatisch auf die maximal sichtbare Zeichenanzahl
        """

        return str(text)[: cls.max_chars()]

    @classmethod
    def split_lines(cls, text, max_lines=2):
        """
        Zerlegt langen Text automatisch in mehrere Displayzeilen
        """

        text = str(text)

        breite = cls.max_chars()

        zeilen = []

        while text and len(zeilen) < max_lines:
            zeilen.append(text[:breite])
            text = text[breite:]

        return zeilen

class DisplayManager:
    """
    Verwaltung der kompletten OLED-Oberfläche.

    Die Klasse besitzt einen internen Zustandsautomaten. Öffentliche Methoden setzen ausschließlich den Zustand und speichern Anzeigedaten,
    Das eigentliche Zeichnen erfolgt über private _draw_xxx()-Methoden.
    """

    # Displayzustände
    BOOT = 0
    WLAN = 1
    ACCESS_POINT = 2
    BASIS = 3
    NTC_UPDATE = 4
    DRUCK_UPDATE = 5
    STATUS = 6

    # Zeitkonstanten
    UPDATE_TIMEOUT = 10
    STATUS_TIMEOUT = 15

    # Displaygröße
    DISPLAY_BREITE = DISPLAY_BREITE
    DISPLAY_HOEHE = DISPLAY_HOEHE


    def __init__(self, display):
        """
        Initialisiert den Displaymanager
        """

        if display is None:
            raise ValueError("display darf nicht None sein")

        self._display = display

        self._zustand = self.BOOT
        self._timeout = None

        self._temperatur_1 = 0.0
        self._temperatur_2 = 0.0

        self._druck_pa = 0.0
        self._druck_mmws = 0.0

        self._heizung = False

        self._ssid = ""
        self._ip = ""

        self._status_ok = True
        self._status_text = "OK"

        self._draw_boot()


    # Interne Hilfsmethoden
    def _zeit(self):
        """ Liefert die aktuelle Laufzeit in Sekunden """
        try:
            return time.time()
        except AttributeError:
            return time.ticks_ms() // 1000

    def _starte_timeout(self, sekunden):
        """
        Startet einen Rücksprungtimer
        """

        self._timeout = self._zeit() + sekunden

    def _timeout_abgelaufen(self):
        """
        Prüft, ob ein Rücksprung erfolgen muss
        """

        if self._timeout is None:
            return False

        return self._zeit() >= self._timeout

    # Zyklische Aktualisierung
    def update(self):
        """
        Wird zyklisch aus main.py aufgerufen

        Nach Ablauf eines Timers erfolgt automatisch
        der Rücksprung zur Basisanzeige
        """

        if self._zustand == self.BASIS:
            return

        if not self._timeout_abgelaufen():
            return

        self.basisanzeige(
            self._temperatur_1,
            self._temperatur_2,
            self._druck_pa,
            self._druck_mmws,
            self._heizung,
        )


    def bootscreen(self):
        """Aktiviert den Bootscreen"""

        self._zustand = self.BOOT
        self._draw_boot()


    def wlan_verbindung(self, ssid, ip):
        """
        Zeigt eine erfolgreiche WLAN-Verbindung an
        """

        self._zustand = self.WLAN

        self._ssid = str(ssid)
        self._ip = str(ip)

        self._starte_timeout(self.UPDATE_TIMEOUT)

        self._draw_wlan()

    # -------------------------------------------------
    # Access Point
    # -------------------------------------------------

    def access_point(self, ssid, ip):
        """
        Zeigt den Access-Point-Modus
        """

        self._zustand = self.ACCESS_POINT

        self._ssid = str(ssid)
        self._ip = str(ip)

        self._starte_timeout(self.UPDATE_TIMEOUT)

        self._draw_ap()


    def basisanzeige(
        self,
        temperatur_1,
        temperatur_2,
        druck_pa,
        druck_mmws,
        heizung,
    ):
        """
        Aktualisiert die permanente Hauptanzeige. Es werden ausschließlich Daten gespeichert.
        Das Zeichnen erfolgt anschließend über _draw_basis()
        """

        self._zustand = self.BASIS
        self._timeout = None

        self._temperatur_1 = float(temperatur_1)
        self._temperatur_2 = float(temperatur_2)

        self._druck_pa = float(druck_pa)
        self._druck_mmws = float(druck_mmws)

        self._heizung = bool(heizung)

        self._draw_basis()

   
    # Temperaturupdate

    def ntc_update(self, kanal, temperatur):
        """
        Zeigt eine Aktualisierung eines einzelnen NTC-Kanals an;
        Nach Ablauf des Timeouts erfolgt automatisch die Rückkehr zur Basisanzeige.
        """

        self._zustand = self.NTC_UPDATE

        temperatur = float(temperatur)

        if kanal == 1:
            self._temperatur_1 = temperatur
        elif kanal == 2:
            self._temperatur_2 = temperatur
        else:
            raise ValueError("kanal muss 1 oder 2 sein")

        self._starte_timeout(self.UPDATE_TIMEOUT)

        self._draw_ntc()


    # Temperaturupdate beide Kanäle

    def ntc_update_gemeinsam(self, temperatur):
        """
        Aktualisiert beide Temperaturkanäle gleichzeitig
        """

        self._zustand = self.NTC_UPDATE

        temperatur = float(temperatur)

        self._temperatur_1 = temperatur
        self._temperatur_2 = temperatur

        self._starte_timeout(self.UPDATE_TIMEOUT)

        self._draw_ntc()


    # Druckupdate
    def druck_update(self, druck_pa, druck_mmws):
        """
        Zeigt Druckänderung.
        """

        self._zustand = self.DRUCK_UPDATE

        self._druck_pa = float(druck_pa)
        self._druck_mmws = float(druck_mmws)

        self._starte_timeout(self.UPDATE_TIMEOUT)

        self._draw_druck()



    def statusanzeige(self, status_ok, status_text):
        """
        Zeigt allgemeinen Systemstatus
        """

        self._zustand = self.STATUS

        self._status_ok = bool(status_ok)
        self._status_text = str(status_text)

        self._starte_timeout(self.STATUS_TIMEOUT)

        self._draw_status()

# Zeichnungsmethodiken 

    def _draw_boot(self):
        """Zeichnet Bootscreen"""

        d = self._display

        d.fill(0)

        d.text("Miele", 38, 8)
        d.text("Sensor Emulator", 12, 24)
        d.text("ESP32", 42, 40)

        d.show()

    def _draw_wlan(self):
        """Zeichnet die WLAN-Seite"""

        d = self._display

        d.fill(0)

        d.text("WLAN verbunden", 0, 0)
        d.text(
            DisplayHelper.fit(self._ssid),
            0,
            18
        )

        d.text(
            DisplayHelper.fit(self._ip),
            0,
            34
        )

        d.show()

    def _draw_ap(self):
        """Zeichnet den Access-Point-Modus"""

        d = self._display

        d.fill(0)

        d.text("Access Point", 0, 0)
        d.text(
            DisplayHelper.fit(self._ssid),
            0,
            18
        )

        d.text(
            DisplayHelper.fit(self._ip),
            0,
            34
        )

        d.show()

    def _draw_basis(self):
        """Zeichnet die permanente Hauptansicht"""

        d = self._display

        d.fill(0)

        d.text(
            "T1:{:>5.1f}C".format(self._temperatur_1),
            0,
            0,
        )

        d.text(
            "T2:{:>5.1f}C".format(self._temperatur_2),
            0,
            12,
        )

        d.text(
            "P:{:>5.0f}Pa".format(self._druck_pa),
            0,
            28,
        )

        d.text(
            "{:>5.1f}mm".format(self._druck_mmws),
            0,
            40,
        )

        heizung = (
            "HEIZUNG EIN"
            if self._heizung
            else "HEIZUNG AUS"
        )

        d.text(heizung, 0, 56)

        d.show()

    def _draw_ntc(self):
        """
        Zeichnet die Anzeige während Temperaturupdates
        """

        d = self._display

        d.fill(0)

        d.text("NTC Update", 20, 0)

        d.text(
            "T1 {:5.1f}C".format(self._temperatur_1),
            0,
            20,
        )

        d.text(
            "T2 {:5.1f}C".format(self._temperatur_2),
            0,
            36,
        )

        d.show()

    def _draw_druck(self):
        """ Zeichnet die Druck-Aktualisierungsseite. """

        d = self._display

        d.fill(0)

        d.text("Druck Update", 16, 0)

        d.text(
            "{:.0f} Pa".format(self._druck_pa),
            0,
            22,
        )

        d.text(
            "{:.1f} mmWS".format(self._druck_mmws),
            0,
            38,
        )

        d.show()

    def _draw_status(self):
        """Zeichnet die Statusanzeige."""

        d = self._display

        d.fill(0)

        d.text("Systemstatus", 10, 0)

        status = "OK" if self._status_ok else "FEHLER"

        d.text(status, 0, 22)

        zeilen = DisplayHelper.split_lines(
            self._status_text,
            max_lines=2
        )

        if len(zeilen) > 0:
            d.text(
                zeilen[0],
                0,
                36
            )

        if len(zeilen) > 1:
            d.text(
                zeilen[1],
                0,
                48
            )

        d.show()


    # Öffentliche Hilfsmethoden

    def hole_zustand(self):
        """
        Liefert den aktuell aktiven Displayzustand.
        """

        return self._zustand

    def ist_basisanzeige(self):
        """
        Prüft, ob sich das Display aktuell
        in der Basisanzeige befindet.
        """

        return self._zustand == self.BASIS

    def display_leeren(self):
        """
        Löscht das komplette OLED-Display.
        """

        self._display.fill(0)
        self._display.show()

    def ausschalten(self):
        """
        Schaltet den Displayinhalt aus.
        """

        self.display_leeren()

    def einschalten(self):
        """
        Erzwingt ein erneutes Zeichnen
        des aktuell gespeicherten Zustands.
        """

        if self._zustand == self.BOOT:
            self._draw_boot()
        elif self._zustand == self.WLAN:
            self._draw_wlan()
        elif self._zustand == self.ACCESS_POINT:
            self._draw_ap()
        elif self._zustand == self.BASIS:
            self._draw_basis()
        elif self._zustand == self.NTC_UPDATE:
            self._draw_ntc()
        elif self._zustand == self.DRUCK_UPDATE:
            self._draw_druck()
        elif self._zustand == self.STATUS:
            self._draw_status()


    # Diagnosefunktionen

    def hole_statusdaten(self):
        """
        Liefert den kompletten internen
        Anzeigezustand als Dictionary.

        Kann später für REST-Diagnose
        oder Debugging verwendet werden.
        """

        return {
            "zustand": self._zustand,
            "temperatur_1": self._temperatur_1,
            "temperatur_2": self._temperatur_2,
            "druck_pa": self._druck_pa,
            "druck_mmws": self._druck_mmws,
            "heizung": self._heizung,
            "ssid": self._ssid,
            "ip": self._ip,
            "status_ok": self._status_ok,
            "status_text": self._status_text,
            "timeout": self._timeout,
        }

    def aktualisieren(self):
        """
        Alias für update().
        """

        self.update()

    def neu_zeichnen(self):
        """
        Erzwingt ein komplettes Neuzeichnen
        der aktuellen Displayseite.
        """

        self.einschalten()

    def reset(self):
        """
        Setzt den kompletten Displaymanager
        auf den Initialzustand zurück.
        """

        self._zustand = self.BOOT

        self._timeout = None

        self._temperatur_1 = 0.0
        self._temperatur_2 = 0.0

        self._druck_pa = 0.0
        self._druck_mmws = 0.0

        self._heizung = False

        self._ssid = ""
        self._ip = ""

        self._status_ok = True
        self._status_text = "OK"

        self._draw_boot()

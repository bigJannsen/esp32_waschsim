"""Zustandsbasierte, rein darstellende OLED-Benutzeroberflaeche."""

try:
    import time as _time
except ImportError:  # pragma: no cover
    _time = None


DISPLAY_BREITE = 128
DISPLAY_HOEHE = 64
BOOT_TIMEOUT_MS = 5_000
NTC_UPDATE_TIMEOUT_MS = 10_000
DRUCK_UPDATE_TIMEOUT_MS = 10_000
STATUS_TIMEOUT_MS = 15_000
NETWORK_NOTICE_TIMEOUT_MS = 5_000


class DisplayHelper:
    CHAR_WIDTH = 8
    DISPLAY_WIDTH = DISPLAY_BREITE

    @classmethod
    def max_chars(cls):
        return cls.DISPLAY_WIDTH // cls.CHAR_WIDTH

    @classmethod
    def fit(cls, text):
        return str(text)[: cls.max_chars()]


class _SystemTicks:
    def ticks_ms(self):
        if hasattr(_time, "ticks_ms"):
            return _time.ticks_ms()
        return int(_time.monotonic() * 1000)

    def ticks_diff(self, newer, older):
        if hasattr(_time, "ticks_diff"):
            return _time.ticks_diff(newer, older)
        return newer - older


class DisplayManager:
    BOOT = 0
    WLAN_CONNECTING = 1
    ACCESS_POINT = 2
    BASIS = 3
    NTC_UPDATE = 4
    DRUCK_UPDATE = 5
    STATUS = 6

    BOOT_TIMEOUT_MS = BOOT_TIMEOUT_MS
    NTC_UPDATE_TIMEOUT_MS = NTC_UPDATE_TIMEOUT_MS
    DRUCK_UPDATE_TIMEOUT_MS = DRUCK_UPDATE_TIMEOUT_MS
    STATUS_TIMEOUT_MS = STATUS_TIMEOUT_MS

    def __init__(self, display, clock=None):
        if display is None:
            raise ValueError("display darf nicht None sein")
        self._display = display
        self._clock = clock or _SystemTicks()
        self._zustand = self.BOOT
        self._started_at = self._clock.ticks_ms()
        self._timeout_ms = BOOT_TIMEOUT_MS
        self._dirty = True
        self._next_network_state = None
        self._temperature_1_c = 0.0
        self._temperature_2_c = 0.0
        self._pressure_pa = 0.0
        self._pressure_mmws = 0.0
        self._heizung_aktiv = None
        self._status = {}
        self.update()

    def _set_state(self, state, timeout_ms=None):
        self._zustand = state
        self._started_at = self._clock.ticks_ms()
        self._timeout_ms = timeout_ms
        self._dirty = True
        self.update()

    def _expired(self):
        return self._timeout_ms is not None and self._clock.ticks_diff(
            self._clock.ticks_ms(), self._started_at
        ) >= self._timeout_ms

    def update(self):
        if self._expired():
            if self._zustand == self.BOOT and self._next_network_state is not None:
                state = self._next_network_state
                self._next_network_state = None
                self._set_state(state, NETWORK_NOTICE_TIMEOUT_MS if state == self.ACCESS_POINT else None)
                return
            self._zustand = self.BASIS
            self._timeout_ms = None
            self._dirty = True
        if self._dirty:
            self._render()
            self._dirty = False

    def bootscreen(self):
        self._next_network_state = None
        self._set_state(self.BOOT, BOOT_TIMEOUT_MS)

    def wlan_connecting(self):
        if self._zustand == self.BOOT and not self._expired():
            self._next_network_state = self.WLAN_CONNECTING
            return
        self._set_state(self.WLAN_CONNECTING)

    def wlan_verbindung(self, ssid=None, ip=None):
        _ = (ssid, ip)
        self.wlan_connecting()

    def access_point(self, ssid=None, ip=None):
        _ = (ssid, ip)
        if self._zustand == self.BOOT and not self._expired():
            self._next_network_state = self.ACCESS_POINT
            return
        self._set_state(self.ACCESS_POINT, NETWORK_NOTICE_TIMEOUT_MS)

    def netzwerk_bereit(self, access_point=False):
        """Merkt das echte Netzwerkergebnis bis zum Ende des Bootscreens vor."""
        state = self.ACCESS_POINT if access_point else self.BASIS
        if self._zustand == self.BOOT and not self._expired():
            self._next_network_state = state
            return
        self._set_state(state, NETWORK_NOTICE_TIMEOUT_MS if access_point else None)

    def basisanzeige(self, temperature_1_c, temperature_2_c, pressure_pa,
                     pressure_mmws, heizung_aktiv=None):
        self._set_basiswerte(temperature_1_c, temperature_2_c, pressure_pa,
                             pressure_mmws, heizung_aktiv)
        self._set_state(self.BASIS)

    def _set_basiswerte(self, t1, t2, pa, mmws, heizung):
        values = (t1, t2, pa, mmws, heizung)
        old = (self._temperature_1_c, self._temperature_2_c,
               self._pressure_pa, self._pressure_mmws, self._heizung_aktiv)
        self._temperature_1_c, self._temperature_2_c = t1, t2
        self._pressure_pa, self._pressure_mmws = pa, mmws
        self._heizung_aktiv = heizung
        if values != old and self._zustand == self.BASIS:
            self._dirty = True

    def aktualisiere_basiswerte(self, temperature_1_c, temperature_2_c,
                                pressure_pa, pressure_mmws, heizung_aktiv=None):
        self._set_basiswerte(temperature_1_c, temperature_2_c, pressure_pa,
                             pressure_mmws, heizung_aktiv)

    def ntc_update(self, payload_or_channel, temperatur=None):
        if isinstance(payload_or_channel, dict):
            payload = payload_or_channel
            self._temperature_1_c = payload["temperature_1_c"]
            self._temperature_2_c = payload["temperature_2_c"]
        else:  # Kompatibilitaet zur bisherigen Display-API
            if payload_or_channel == 1:
                self._temperature_1_c = temperatur
            elif payload_or_channel == 2:
                self._temperature_2_c = temperatur
            else:
                raise ValueError("kanal muss 1 oder 2 sein")
        self._set_state(self.NTC_UPDATE, NTC_UPDATE_TIMEOUT_MS)

    def ntc_update_gemeinsam(self, temperatur):
        self.ntc_update({"temperature_1_c": temperatur, "temperature_2_c": temperatur})

    def druck_update(self, pressure_pa, pressure_mmws=None):
        if isinstance(pressure_pa, dict):
            payload = pressure_pa
            pressure_pa = payload["pressure_pa"]
            pressure_mmws = payload["pressure_mmws"]
        self._pressure_pa = pressure_pa
        self._pressure_mmws = pressure_mmws
        self._set_state(self.DRUCK_UPDATE, DRUCK_UPDATE_TIMEOUT_MS)

    def statusanzeige(self, status, status_text=None):
        if isinstance(status, dict):
            self._status = status
        else:  # Kompatibilitaet zur bisherigen API
            self._status = {"ok": bool(status), "message": status_text}
        self._set_state(self.STATUS, STATUS_TIMEOUT_MS)

    def hole_zustand(self):
        return self._zustand

    def ist_basisanzeige(self):
        return self._zustand == self.BASIS

    def neu_zeichnen(self):
        self._dirty = True
        self.update()

    aktualisieren = update

    def _line(self, text, row):
        self._display.text(DisplayHelper.fit(text), 0, row * 10)

    def _render(self):
        self._display.fill(0)
        if self._zustand == self.BOOT:
            self._line("Miele & Cie.KG", 0); self._line("ESP-Waschsim", 2); self._line("GTG/RD", 5)
        elif self._zustand == self.WLAN_CONNECTING:
            self._title(); self._line("WLAN", 2); self._line("verbindet...", 3)
        elif self._zustand == self.ACCESS_POINT:
            self._title(); self._line("Access Point", 2); self._line("aktiv. Bitte", 3); self._line("verbinden!", 4)
        elif self._zustand == self.BASIS:
            self._title(); self._line("Heizung: " + self._heat_text(), 1)
            self._line("T1: {} Grad".format(self._fmt(self._temperature_1_c)), 2)
            self._line("T2: {} Grad".format(self._fmt(self._temperature_2_c)), 3)
            self._line("Druck: {} Pa".format(self._fmt(self._pressure_pa)), 4)
            self._line("{} mmWS".format(self._fmt(self._pressure_mmws)), 5)
        elif self._zustand == self.NTC_UPDATE:
            self._title(); self._line("Neue Temperat.:", 2)
            self._line("NTC1: {} Grad".format(self._fmt(self._temperature_1_c)), 3)
            self._line("NTC2: {} Grad".format(self._fmt(self._temperature_2_c)), 4)
        elif self._zustand == self.DRUCK_UPDATE:
            self._title(); self._line("Neuer Druck:", 2)
            self._line("{} Pa".format(self._fmt(self._pressure_pa)), 3)
            self._line("{} mmWS".format(self._fmt(self._pressure_mmws)), 4)
        else:
            self._render_status()
        self._display.show()

    def _title(self):
        self._line("Miele Waschsim", 0)

    @staticmethod
    def _fmt(value):
        if value is None:
            return "--"
        return "{:.1f}".format(value)

    def _heat_text(self):
        if self._heizung_aktiv is None:
            return "--"
        return "AN" if self._heizung_aktiv else "AUS"

    def _render_status(self):
        data = self._status
        hardware = data.get("hardware", data)
        self._line("Status: " + ("ok" if data.get("ok") else "Fehler"), 0)
        self._line("T1 {} Grd".format(self._fmt(hardware.get("temperature_1_c"))), 1)
        self._line("T2 {} Grd".format(self._fmt(hardware.get("temperature_2_c"))), 2)
        self._line("{} Pa".format(self._fmt(hardware.get("pressure_pa"))), 3)
        self._line("{} mmWS".format(self._fmt(data.get("pressure_mmws"))), 4)
        self._line("{} API:{}".format(data.get("backend", "real"), data.get("api_version", "v1")), 5)

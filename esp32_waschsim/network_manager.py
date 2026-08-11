"""WLAN-Verwaltung fuer STA-Betrieb und den bewaehrten AP-Fallback."""

try:
    import network as _network
except ImportError:  # Lokale Tests uebergeben das Backend per Dependency Injection.
    _network = None

try:
    import uasyncio as _asyncio
except ImportError:  # pragma: no cover - auf CPython nur als Laufzeit-Fallback.
    import asyncio as _asyncio


# Zentraler, bewusst konservativer Entwicklungsstand
NETWORK_MODE = "legacy_ap"  # "auto" -> WLAN-Connection
STA_SSID = ""               # SSID für WLAN
STA_PASSWORT = ""           # Passwort für WLAN
AP_SSID = "miele"           # AP-Teil nicht ändern wenn WLAN aktiv!
AP_PASSWORT = "10000000"
WLAN_TIMEOUT_S = 20
WLAN_POLL_MS = 100


class NetworkManager:
    """Steuert exklusiv die WLAN-Interfaces und liefert strukturierte Statuswerte."""

    def __init__(
        self,
        sta_ssid=STA_SSID,
        sta_passwort=STA_PASSWORT,
        ap_ssid=AP_SSID,
        ap_passwort=AP_PASSWORT,
        wlan_timeout_s=WLAN_TIMEOUT_S,
        network_backend=None,
        asyncio_backend=None,
        poll_ms=WLAN_POLL_MS,
    ):
        self.sta_ssid = sta_ssid
        self.sta_passwort = sta_passwort
        self.ap_ssid = ap_ssid
        self.ap_passwort = ap_passwort
        self.wlan_timeout_s = wlan_timeout_s
        self.network = network_backend if network_backend is not None else _network
        self.asyncio = asyncio_backend if asyncio_backend is not None else _asyncio
        self.poll_ms = poll_ms
        if self.network is None:
            raise RuntimeError("Kein network-Backend verfuegbar")

    @staticmethod
    def _ip_aus_ifconfig(interface):
        konfiguration = interface.ifconfig()
        if not isinstance(konfiguration, (tuple, list)) or not konfiguration:
            raise RuntimeError("ifconfig lieferte keine gueltige Konfiguration")
        ip = konfiguration[0]
        if not isinstance(ip, str) or not ip or ip == "0.0.0.0":
            raise RuntimeError("ifconfig lieferte keine gueltige IP")
        return ip

    def _ermittle_ap_authmode(self):
        # Reihenfolge entspricht dem bereits auf ESP32-Hardware bewaehrten AP-Code.
        if hasattr(self.network, "AUTH_WPA2_PSK"):
            return self.network.AUTH_WPA2_PSK
        if hasattr(self.network, "AUTH_WPA_WPA2_PSK"):
            return self.network.AUTH_WPA_WPA2_PSK
        return None

    async def _sleep_ms(self, dauer_ms):
        if hasattr(self.asyncio, "sleep_ms"):
            await self.asyncio.sleep_ms(dauer_ms)
        else:
            await self.asyncio.sleep(dauer_ms / 1000.0)

    @staticmethod
    def _fehler(mode, code, meldung):
        return {"ok": False, "mode": mode, "error": code, "message": meldung}

    def _deaktiviere_sta(self, sta):
        try:
            if hasattr(sta, "disconnect"):
                sta.disconnect()
        except Exception as exc:
            print("STA disconnect fehlgeschlagen: {}".format(exc))
        try:
            sta.active(False)
        except Exception as exc:
            print("STA deaktivieren fehlgeschlagen: {}".format(exc))

    async def verbinde_wlan(self):
        """Versucht STA zeitlich begrenzt zu verbinden; blockiert nie endlos."""
        if not self.sta_ssid:
            return self._fehler("station", "STA_NOT_CONFIGURED", "Keine STA-SSID konfiguriert")

        try:
            ap = self.network.WLAN(self.network.AP_IF)
            if ap.active():
                ap.active(False)
            sta = self.network.WLAN(self.network.STA_IF)
            sta.active(True)
        except Exception as exc:
            return self._fehler("station", "STA_CONNECT_ERROR", str(exc))

        try:
            if sta.isconnected():
                ip = self._ip_aus_ifconfig(sta)
                return {"ok": True, "mode": "station", "ssid": self.sta_ssid, "ip": ip}
        except Exception as exc:
            self._deaktiviere_sta(sta)
            return self._fehler("station", "STA_STATUS_ERROR", str(exc))

        try:
            try:
                sta.disconnect()
            except Exception:
                pass
            sta.connect(self.sta_ssid, self.sta_passwort)
        except Exception as exc:
            self._deaktiviere_sta(sta)
            return self._fehler("station", "STA_CONNECT_ERROR", str(exc))

        poll_ms = max(1, int(self.poll_ms))
        timeout_ms = max(0, int(float(self.wlan_timeout_s) * 1000))
        anzahl_polls = (timeout_ms + poll_ms - 1) // poll_ms
        for poll_index in range(anzahl_polls + 1):
            try:
                if sta.isconnected():
                    ip = self._ip_aus_ifconfig(sta)
                    return {"ok": True, "mode": "station", "ssid": self.sta_ssid, "ip": ip}
            except Exception as exc:
                self._deaktiviere_sta(sta)
                return self._fehler("station", "STA_STATUS_ERROR", str(exc))
            if poll_index < anzahl_polls:
                await self._sleep_ms(poll_ms)

        self._deaktiviere_sta(sta)
        return self._fehler("station", "STA_TIMEOUT", "STA-Verbindung nach Timeout nicht hergestellt")

    async def starte_access_point(self):
        """Startet den AP entlang des bewaehrten active/config/active/ifconfig-Wegs."""
        ap = None
        try:
            ap = self.network.WLAN(self.network.AP_IF)
            ap.active(True)

            authmode = self._ermittle_ap_authmode()
            if authmode is None:
                ap.config(essid=self.ap_ssid, password=self.ap_passwort)
            else:
                ap.config(essid=self.ap_ssid, password=self.ap_passwort, authmode=authmode)

            for _ in range(20):
                if ap.active():
                    break
                await self._sleep_ms(50)

            if not ap.active():
                raise RuntimeError("AP wurde nicht aktiv")

            ap_ip = self._ip_aus_ifconfig(ap)
            print("WLAN AP aktiv auf {}".format(ap_ip))
            return {"ok": True, "mode": "access_point", "ssid": self.ap_ssid, "ip": ap_ip}
        except Exception as exc:
            if ap is not None:
                try:
                    ap.active(False)
                except Exception as cleanup_exc:
                    print("AP-Aufraeumen fehlgeschlagen: {}".format(cleanup_exc))
            return self._fehler("access_point", "AP_START_ERROR", str(exc))

    async def verbinde_oder_starte_ap(self):
        """Versucht STA und behandelt jeden Fehlschlag durch regulaeren AP-Fallback."""
        sta_status = await self.verbinde_wlan()
        if sta_status["ok"]:
            return sta_status

        print("STA nicht verfuegbar: {}".format(sta_status.get("message")))
        try:
            sta = self.network.WLAN(self.network.STA_IF)
            self._deaktiviere_sta(sta)
        except Exception as exc:
            print("STA-Aufraeumen vor AP fehlgeschlagen: {}".format(exc))

        ap_status = await self.starte_access_point()
        if ap_status["ok"]:
            ap_status["sta_error"] = sta_status
            return ap_status
        return {
            "ok": False,
            "mode": None,
            "error": "NETWORK_UNAVAILABLE",
            "message": "STA und AP konnten nicht gestartet werden",
            "sta_error": sta_status,
            "ap_error": ap_status,
        }

    async def starte(self, mode=NETWORK_MODE):
        """Startet den sicheren Legacy-AP oder die noch zu validierende Automatik."""
        if mode == "legacy_ap":
            return await self.starte_access_point()
        if mode == "auto":
            return await self.verbinde_oder_starte_ap()
        return self._fehler(None, "INVALID_NETWORK_MODE", "Unbekannter Netzwerkmodus: {}".format(mode))

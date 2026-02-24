"""REST-Kommunikationsschicht der ESP32-Firmware."""

import json

try:
    import uasyncio as asyncio
except ImportError:  # pragma: no cover - CPython-Fallback fuer lokale Tests.
    import asyncio


class RestServer:
    """Stellt eine schlanke HTTP-API fuer Sensor- und Statusrouten bereit."""

    API_BASIS = "/api/v1"
    TEMPERATUR_MIN_C = 0.0
    TEMPERATUR_MAX_C = 100.0

    def __init__(self, ntc_sensor, pressure_sensor, output_driver, hardware, host="0.0.0.0", port=8080):
        """Initialisiert den REST-Server mit allen benoetigten Abhaengigkeiten.

        Args:
            ntc_sensor: Sensorlogik fuer Temperaturverarbeitung.
            pressure_sensor: Sensorlogik fuer Druckverarbeitung.
            output_driver: Ausgabeschicht fuer NTC-Code und PWM-Duty.
            hardware: HardwareAbstraktion fuer den Status-Endpunkt.
            host (str): Bind-Adresse des Servers.
            port (int): TCP-Port des Servers.
        """
        self.ntc_sensor = ntc_sensor
        self.pressure_sensor = pressure_sensor
        self.output_driver = output_driver
        self.hardware = hardware
        self.host = host
        self.port = port
        self._letzte_werte = {
            "channel": None,
            "temperature_c": None,
            "ntc_code": None,
            "pressure_pa": None,
            "pwm_duty": None,
        }

    def starte_server(self):
        """Startet den HTTP-Server mit einer nicht-blockierenden Ereignisschleife."""
        asyncio.run(self._starte_server_async())

    async def _starte_server_async(self):
        """Bindet den TCP-Server und verarbeitet Verbindungen asynchron."""
        server = await asyncio.start_server(self._behandle_client, self.host, self.port)
        await server.wait_closed()

    async def _behandle_client(self, reader, writer):
        """Liest eine HTTP-Anfrage ein, verarbeitet sie und sendet eine JSON-Antwort."""
        try:
            status_code, payload = await self._verarbeite_http_anfrage(reader)
        except Exception:
            status_code, payload = self._fehlerantwort(500, "INTERNAL_ERROR", "Interner Serverfehler")

        response = self._baue_http_antwort(status_code, payload)
        writer.write(response)

        try:
            await writer.drain()
        finally:
            writer.close()
            await writer.wait_closed()

    async def _verarbeite_http_anfrage(self, reader):
        """Parst Request-Line und Body und routet zur passenden Handler-Methode."""
        request_line_raw = await reader.readline()
        if not request_line_raw:
            return self._fehlerantwort(400, "BAD_REQUEST", "Leere Anfrage")

        request_line = request_line_raw.decode("utf-8").strip()
        teile = request_line.split(" ")
        if len(teile) != 3:
            return self._fehlerantwort(400, "BAD_REQUEST", "Ungueltige Request-Line")

        methode, pfad, _ = teile
        headers = await self._lese_headers(reader)

        try:
            content_length = self._parse_content_length(headers)
            body_raw = b""
            if content_length > 0:
                body_raw = await reader.readexactly(content_length)

            if methode == "PUT" and pfad == self.API_BASIS + "/sensors/temperature":
                return self._route_setze_temperatur(body_raw)
            if methode == "PUT" and pfad == self.API_BASIS + "/sensors/pressure":
                return self._route_setze_druck(body_raw)
        except ValueError as exc:
            return self._fehlerantwort(400, "BAD_REQUEST", str(exc))
        if methode == "GET" and pfad == self.API_BASIS + "/status":
            return self._route_status()
        if methode == "GET" and pfad == self.API_BASIS + "/health":
            return self._route_health()
        return self._fehlerantwort(404, "NOT_FOUND", "Route nicht gefunden")

    async def _lese_headers(self, reader):
        """Liest HTTP-Header bis zur Leerzeile in ein Dictionary ein."""
        headers = {}
        while True:
            line = await reader.readline()
            if not line or line == b"\r\n":
                break
            text = line.decode("utf-8").strip()
            if not text or ":" not in text:
                continue
            name, value = text.split(":", 1)
            headers[name.strip().lower()] = value.strip()
        return headers

    def _parse_content_length(self, headers):
        """Validiert und liefert den Content-Length-Header als Integer."""
        raw = headers.get("content-length")
        if raw is None:
            return 0
        try:
            laenge = int(raw)
        except ValueError:
            raise ValueError("content-length ungueltig")
        if laenge < 0:
            raise ValueError("content-length negativ")
        return laenge

    def _route_setze_temperatur(self, body_raw):
        """Verarbeitet PUT /sensors/temperature inklusive Validierung und Mapping."""
        try:
            daten = self._parse_json_body(body_raw)
            channel = self._hole_int_feld(daten, "channel")
            if channel not in (1, 2):
                return self._fehlerantwort(400, "BAD_REQUEST", "channel muss 1 oder 2 sein")

            temperatur_c = self._hole_float_feld(daten, "temperature_c")
            if temperatur_c < self.TEMPERATUR_MIN_C or temperatur_c > self.TEMPERATUR_MAX_C:
                return self._fehlerantwort(400, "BAD_REQUEST", "temperature_c ausserhalb 0.0 bis 100.0")

            ntc_code = self.ntc_sensor.verarbeite_temperatur(temperatur_c)
            self.output_driver.setze_ntc_code(ntc_code)
        except ValueError as exc:
            return self._fehlerantwort(400, "BAD_REQUEST", str(exc))

        self._letzte_werte["channel"] = channel
        self._letzte_werte["temperature_c"] = temperatur_c
        self._letzte_werte["ntc_code"] = ntc_code

        return self._ok_antwort(
            {
                "ok": True,
                "channel": channel,
                "temperature_c": temperatur_c,
                "ntc_code": ntc_code,
            }
        )

    def _route_setze_druck(self, body_raw):
        """Verarbeitet PUT /sensors/pressure inklusive Validierung und Mapping."""
        try:
            daten = self._parse_json_body(body_raw)
            pressure_pa = self._hole_float_feld(daten, "pressure_pa")
            if pressure_pa < 0.0 or pressure_pa > 2452.0:
                return self._fehlerantwort(400, "BAD_REQUEST", "pressure_pa ausserhalb 0.0 bis 2452.0")

            pwm_duty = self.pressure_sensor.verarbeite_druck_pa(pressure_pa)
            self.output_driver.setze_pwm_duty(pwm_duty)
        except ValueError as exc:
            return self._fehlerantwort(400, "BAD_REQUEST", str(exc))

        self._letzte_werte["pressure_pa"] = pressure_pa
        self._letzte_werte["pwm_duty"] = pwm_duty

        return self._ok_antwort(
            {
                "ok": True,
                "pressure_pa": pressure_pa,
                "pwm_duty": pwm_duty,
            }
        )

    def _route_status(self):
        """Liefert den Hardwarestatus inklusive zuletzt gesetzter API-Werte."""
        status = self.hardware.lese_status()
        status.update(self._letzte_werte)
        status["ok"] = True
        return self._ok_antwort(status)

    def _route_health(self):
        """Liefert einen statischen Health-Check fuer Monitoring und Smoke-Tests."""
        return self._ok_antwort({"ok": True, "service": "esp32_waschsim", "version": "v1"})

    def _parse_json_body(self, body_raw):
        """Dekodiert den Anfrage-Body als JSON-Objekt und validiert den Typ."""
        if not body_raw:
            raise ValueError("JSON-Body fehlt")
        try:
            daten = json.loads(body_raw.decode("utf-8"))
        except (ValueError, UnicodeError):
            raise ValueError("JSON ungueltig")
        if not isinstance(daten, dict):
            raise ValueError("JSON-Body muss ein Objekt sein")
        return daten

    def _hole_int_feld(self, daten, feldname):
        """Liefert ein Pflichtfeld als int oder wirft ValueError bei Typfehlern."""
        if feldname not in daten:
            raise ValueError("{} fehlt".format(feldname))
        wert = daten[feldname]
        if isinstance(wert, bool) or not isinstance(wert, int):
            raise ValueError("{} muss int sein".format(feldname))
        return wert

    def _hole_float_feld(self, daten, feldname):
        """Liefert ein Pflichtfeld als float oder wirft ValueError bei Typfehlern."""
        if feldname not in daten:
            raise ValueError("{} fehlt".format(feldname))
        wert = daten[feldname]
        if isinstance(wert, bool) or not isinstance(wert, float):
            raise ValueError("{} muss float sein".format(feldname))
        return wert

    def _ok_antwort(self, payload):
        """Erzeugt eine erfolgreiche JSON-Antwort mit Statuscode 200."""
        return 200, payload

    def _fehlerantwort(self, status_code, code, message):
        """Erzeugt eine standardisierte JSON-Fehlerantwort."""
        return status_code, {"ok": False, "error": {"code": code, "message": message}}

    def _baue_http_antwort(self, status_code, payload):
        """Serialisiert Statuszeile, Header und JSON-Body als HTTP/1.1-Bytes."""
        grund = {
            200: "OK",
            400: "Bad Request",
            404: "Not Found",
            500: "Internal Server Error",
        }.get(status_code, "OK")
        body = json.dumps(payload).encode("utf-8")
        header = (
            "HTTP/1.1 {} {}\r\n"
            "Content-Type: application/json\r\n"
            "Content-Length: {}\r\n"
            "Connection: close\r\n"
            "\r\n"
        ).format(status_code, grund, len(body)).encode("utf-8")
        return header + body

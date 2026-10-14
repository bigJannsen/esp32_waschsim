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

    def __init__(self, ntc_sensor, pressure_sensor, hardware, host="0.0.0.0", port=8080,
                 event_callback=None, before_sensor_write=None,
                 set_simulation_active=None, get_simulation_status=None):
        """Initialisiert den REST-Server mit allen benoetigten Abhaengigkeiten."""
        self.ntc_sensor = ntc_sensor
        self.pressure_sensor = pressure_sensor
        self.hardware = hardware
        self.host = host
        self.port = port
        self.event_callback = event_callback
        # Synchroner Koordinationshook nach Validierung, vor jedem manuellen PUT.
        # Fehler nicht verschlucken: ohne Steuerungsuebergabe keine Sensorausgabe.
        self.before_sensor_write = before_sensor_write
        # Synchrone System-Callbacks: REST kennt weder Task noch Simulationskern.
        self.set_simulation_active = set_simulation_active
        self.get_simulation_status = get_simulation_status
        hardware_status = self.hardware.lese_status()
        self._letzte_werte = {
            "temperature": {
                "mode": None,
                "channels": {
                    "1": {
                        "temperature_c": hardware_status.get("temperature_1_c", 0.0),
                        "ntc_code": hardware_status.get("ntc_code_1", 0),
                    },
                    "2": {
                        "temperature_c": hardware_status.get("temperature_2_c", 0.0),
                        "ntc_code": hardware_status.get("ntc_code_2", 0),
                    },
                },
            },
            "pressure": {
                "pressure_pa": hardware_status.get("pressure_pa", 0.0),
                "pwm_duty": hardware_status.get("pwm_duty", 0.0),
            },
            "last_command": None,
        }

    def _melde_event(self, event_type, payload):
        """Meldet optionale UI-Ereignisse, ohne REST-Erfolge zu gefaehrden."""
        if self.event_callback is None:
            return
        try:
            self.event_callback(event_type, payload)
        except Exception as exc:
            print("Optionaler Event-Callback fehlgeschlagen: {}".format(exc))

    def _temperatur_event(self, mode, channel=None):
        channels = self._letzte_werte["temperature"]["channels"]
        payload = {
            "temperature_1_c": channels["1"]["temperature_c"],
            "temperature_2_c": channels["2"]["temperature_c"],
            "mode": mode,
        }
        if channel is not None:
            payload["channel"] = channel
        self._melde_event("temperature_updated", payload)

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
            if methode == "PUT" and pfad == self.API_BASIS + "/simulation/mode":
                return self._route_setze_simulationsmodus(body_raw)
        except ValueError as exc:
            return self._fehlerantwort(400, "BAD_REQUEST", str(exc))

        if methode == "GET" and pfad == self.API_BASIS + "/status":
            return self._route_status()
        if methode == "GET" and pfad == self.API_BASIS + "/health":
            return self._route_health()
        if methode == "GET" and pfad == self.API_BASIS + "/simulation":
            return self._route_simulation()
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

            mode = daten.get("mode", None)
            if mode is not None:
                if not isinstance(mode, str):
                    return self._fehlerantwort(400, "BAD_REQUEST", "mode muss ein String sein")

                mode = mode.lower()
                if mode not in ("same", "separate"):
                    return self._fehlerantwort(400, "BAD_REQUEST", "mode muss 'same' oder 'separate' sein")

                if mode == "same":
                    temperatur_c = self._hole_float_feld(daten, "temperature_c")
                    self._pruefe_temperaturbereich(temperatur_c, "temperature_c")

                    if self.before_sensor_write is not None:
                        self.before_sensor_write()
                    ntc_code = self.ntc_sensor.verarbeite_temperatur(temperatur_c)

                    self._letzte_werte["temperature"] = {
                        "mode": "same",
                        "channels": {
                            "1": {
                                "temperature_c": temperatur_c,
                                "ntc_code": ntc_code,
                            },
                            "2": {
                                "temperature_c": temperatur_c,
                                "ntc_code": ntc_code,
                            },
                        },
                    }

                    self._letzte_werte["last_command"] = "set_temperature_same"

                    self._temperatur_event("same")

                    return self._ok_antwort(
                        {
                            "ok": True,
                            "type": "temperature",
                            "mode": "same",
                            "results": [
                                {
                                    "channel": 1,
                                    "temperature_c": temperatur_c,
                                    "ntc_code": ntc_code,
                                },
                                {
                                    "channel": 2,
                                    "temperature_c": temperatur_c,
                                    "ntc_code": ntc_code,
                                },
                            ],
                        }
                    )

                temperatur_1_c = self._hole_float_feld(daten, "temperature_1_c")
                temperatur_2_c = self._hole_float_feld(daten, "temperature_2_c")
                self._pruefe_temperaturbereich(temperatur_1_c, "temperature_1_c")
                self._pruefe_temperaturbereich(temperatur_2_c, "temperature_2_c")

                if self.before_sensor_write is not None:
                    self.before_sensor_write()
                ntc_code_1 = self.ntc_sensor.verarbeite_temperatur(temperatur_1_c, channel=1)
                ntc_code_2 = self.ntc_sensor.verarbeite_temperatur(temperatur_2_c, channel=2)

                self._letzte_werte["temperature"] = {
                    "mode": "separate",
                    "channels": {
                        "1": {
                            "temperature_c": temperatur_1_c,
                            "ntc_code": ntc_code_1,
                        },
                        "2": {
                            "temperature_c": temperatur_2_c,
                            "ntc_code": ntc_code_2,
                        },
                    },
                }

                self._letzte_werte["last_command"] = "set_temperature_separate"

                self._temperatur_event("separate")

                return self._ok_antwort(
                    {
                        "ok": True,
                        "type": "temperature",
                        "mode": "separate",
                        "results": [
                            {
                                "channel": 1,
                                "temperature_c": temperatur_1_c,
                                "ntc_code": ntc_code_1,
                            },
                            {
                                "channel": 2,
                                "temperature_c": temperatur_2_c,
                                "ntc_code": ntc_code_2,
                            },
                        ],
                    }
                )

            if "channel" in daten:
                channel = self._hole_int_feld(daten, "channel")
                if channel not in (1, 2):
                    return self._fehlerantwort(400, "BAD_REQUEST", "channel muss 1 oder 2 sein")

                temperatur_c = self._hole_float_feld(daten, "temperature_c")
                self._pruefe_temperaturbereich(temperatur_c, "temperature_c")

                if self.before_sensor_write is not None:
                    self.before_sensor_write()
                ntc_code = self.ntc_sensor.verarbeite_temperatur(temperatur_c, channel=channel)

                self._letzte_werte["temperature"]["mode"] = "single"
                self._letzte_werte["temperature"]["channels"][str(channel)] = {
                    "temperature_c": temperatur_c,
                    "ntc_code": ntc_code,
                }
                self._letzte_werte["last_command"] = "set_temperature_single"

                self._temperatur_event("single", channel)

                return self._ok_antwort(
                    {
                        "ok": True,
                        "type": "temperature",
                        "channel": channel,
                        "temperature_c": temperatur_c,
                        "ntc_code": ntc_code,
                    }
                )

            return self._fehlerantwort(400, "BAD_REQUEST", "mode oder channel fehlt")

        except ValueError as exc:
            return self._fehlerantwort(400, "BAD_REQUEST", str(exc))

    def _route_setze_druck(self, body_raw):
        """Verarbeitet PUT /sensors/pressure inklusive Validierung und Mapping."""
        try:
            daten = self._parse_json_body(body_raw)
            pressure_pa = self._hole_float_feld(daten, "pressure_pa")
            self._pruefe_druckbereich(pressure_pa, "pressure_pa")

            if self.before_sensor_write is not None:
                self.before_sensor_write()
            pwm_duty = self.pressure_sensor.verarbeite_druck_pa(pressure_pa)

        except ValueError as exc:
            return self._fehlerantwort(400, "BAD_REQUEST", str(exc))

        self._letzte_werte["pressure"] = {
            "pressure_pa": pressure_pa,
            "pwm_duty": pwm_duty,
        }
        self._letzte_werte["last_command"] = "set_pressure"

        pressure_mmws = self.pressure_sensor.berechne_druck_mmws(pressure_pa)
        self._melde_event("pressure_updated", {
            "pressure_pa": pressure_pa,
            "pressure_mmws": pressure_mmws,
        })

        return self._ok_antwort(
            {
                "ok": True,
                "type": "pressure",
                "pressure_pa": pressure_pa,
                "pwm_duty": pwm_duty,
            }
        )

    def _route_simulation(self):
        """Liefert den unveraenderten System-Snapshot ohne Steuerungsuebergabe."""
        if self.get_simulation_status is None:
            return self._fehlerantwort(503, "SIMULATION_UNAVAILABLE", "Simulation nicht angebunden")
        try:
            status = self.get_simulation_status()
            if not isinstance(status, dict):
                raise ValueError("Simulationsstatus muss ein Objekt sein")
        except Exception:
            return self._fehlerantwort(500, "SIMULATION_STATUS_ERROR", "Simulationsstatus nicht lesbar")
        return self._ok_antwort(status)

    def _route_setze_simulationsmodus(self, body_raw):
        """Validiert PUT /simulation/mode und bestaetigt den erreichten Zustand."""
        try:
            daten = self._parse_json_body(body_raw)
        except ValueError as exc:
            return self._fehlerantwort(400, "BAD_REQUEST", str(exc))

        if "mode" not in daten:
            return self._fehlerantwort(400, "BAD_REQUEST", "mode fehlt")
        if len(daten) != 1:
            return self._fehlerantwort(400, "BAD_REQUEST", "Nur mode ist erlaubt")
        mode = daten["mode"]
        if not isinstance(mode, str) or mode not in ("auto", "manual"):
            return self._fehlerantwort(400, "BAD_REQUEST", "mode muss 'auto' oder 'manual' sein")

        if self.set_simulation_active is None or self.get_simulation_status is None:
            return self._fehlerantwort(503, "SIMULATION_UNAVAILABLE", "Simulation nicht angebunden")
        aktiv = mode == "auto"
        try:
            # Kein await bis zum Snapshot: atomare Uebergabe im kooperativen Loop.
            self.set_simulation_active(aktiv)
        except RuntimeError as exc:
            if aktiv:
                return self._fehlerantwort(409, "SIMULATION_NOT_RUNNING", str(exc))
            return self._fehlerantwort(500, "SIMULATION_MODE_ERROR", "Simulation nicht deaktivierbar")
        except Exception:
            return self._fehlerantwort(500, "SIMULATION_MODE_ERROR", "Simulationsmodus nicht setzbar")

        status_code, status = self._route_simulation()
        if status_code != 200:
            # Kein Rollback: eine bereits erfolgte Uebergabe bleibt erhalten.
            return status_code, status
        if status.get("aktiv") is not aktiv:
            return self._fehlerantwort(500, "SIMULATION_MODE_ERROR", "Simulationsmodus nicht erreicht")
        if aktiv and (status.get("task_zustand") != "laeuft"
                      or status.get("task_laeuft") is not True):
            return self._fehlerantwort(409, "SIMULATION_NOT_RUNNING", "Simulationstask laeuft nicht")

        erreichter_modus = "auto" if status["aktiv"] else "manual"
        return self._ok_antwort({"ok": True, "mode": erreichter_modus, "simulation": status})

    def _route_status(self):
        """Liefert den Hardwarestatus sauber geschachtelt zurueck."""
        hardware_status = self.hardware.lese_status()

        status = {
            "ok": bool(hardware_status.get("letzter_status_ok", False)),
            "service": "esp32_waschsim",
            "api_version": "v1",
            "hardware": hardware_status,
            "last_values": dict(self._letzte_werte),
        }

        status["pressure_mmws"] = self.pressure_sensor.berechne_druck_mmws(
            hardware_status.get("pressure_pa", 0.0)
        )
        status["backend"] = hardware_status.get("backend", "real")
        self._melde_event("status_requested", status)

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
        if isinstance(wert, bool) or not isinstance(wert, (int, float)):
            raise ValueError("{} muss float sein".format(feldname))
        return float(wert)

    def _pruefe_temperaturbereich(self, temperatur_c, feldname):
        """Prueft den Temperaturbereich."""
        if not self.TEMPERATUR_MIN_C <= temperatur_c <= self.TEMPERATUR_MAX_C:
            raise ValueError("{} ausserhalb 0.0 bis 100.0".format(feldname))

    def _pruefe_druckbereich(self, pressure_pa, feldname):
        """Prueft den Druckbereich."""
        if not 0.0 <= pressure_pa <= 2452.0:
            raise ValueError("{} ausserhalb 0.0 bis 2452.0".format(feldname))

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
            409: "Conflict",
            500: "Internal Server Error",
            503: "Service Unavailable",
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

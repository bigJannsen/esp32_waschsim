"""Orchestrierung der ESP-Waschsim-Firmware."""

try:
    import uasyncio as asyncio
except ImportError:  # pragma: no cover - lokaler CPython-Kompatibilitaetspfad
    import asyncio

try:
    from time import ticks_ms, ticks_diff
except ImportError:  # Wie im Hardwaremodul: nur CPython-Kompatibilitaet.
    from time import monotonic

    def ticks_ms():
        return int(monotonic() * 1000)

    def ticks_diff(neuer, aelter):
        return neuer - aelter

from display import DisplayManager
from hardware import EINGANG_ABTASTINTERVALL_MS, HardwareAbstraktion
from network_manager import NETWORK_MODE, NetworkManager
from rest import RestServer
from sensors import NtcSensor, PressureSensor
from simulation import SimulationManager


SYSTEM_TASK_INTERVAL_MS = 200
SIMULATION_TASK_INTERVAL_MS = 100
# Taskbudget, kein Maschinenparameter: laengere Pausen vollstaendig verwerfen.
SIMULATION_MAX_INTERVALL_MS = 500

# Vorbereitete Werte: im Taskfehlerpfad kein format(), str(exc) oder Dict-Aufbau.
ABTASTFEHLER = "ABTASTFEHLER"
ABTAST_SPEICHERFEHLER = "ABTAST_SPEICHERFEHLER"
ABTAST_INVALIDIERUNGSFEHLER = "ABTAST_INVALIDIERUNGSFEHLER"
ABTAST_DIAGNOSEFEHLER = "ABTAST_DIAGNOSEFEHLER"
ABTAST_WARTEFEHLER = "ABTAST_WARTEFEHLER"
ABTASTTASK_BEENDET = "ABTASTTASK_BEENDET"
ABTASTUNG_WIEDERHERGESTELLT = "Digitale Abtastung wiederhergestellt"


class SystemAnwendung:
    """Erzeugt und verbindet die voneinander getrennten Firmware-Schichten."""

    def __init__(self, hardware=None, network_manager=None):
        self.hardware = hardware or HardwareAbstraktion()
        self.ntc_sensor = NtcSensor(hardware=self.hardware)
        self.druck_sensor = PressureSensor(hardware=self.hardware)
        self.simulation_manager = SimulationManager()
        self._simulation_aktiv = False
        self._simulation_zeit_ms = None
        self._simulation_intervall_ms = None
        self._simulation_zustand = {}
        self._simulation_fehlerphase = "SIMULATION_ZEITFEHLER"
        self.simulation_fehler = None
        self.simulation_fehlerdetail = None
        self.simulation_letzter_fehler = None
        self.simulation_ausgabe_ok = False
        self.display_manager = None
        self.network_manager = network_manager or NetworkManager()
        self.rest_server = RestServer(
            ntc_sensor=self.ntc_sensor,
            pressure_sensor=self.druck_sensor,
            hardware=self.hardware,
            event_callback=self._ui_event,
            before_sensor_write=self._uebernehme_manuelle_sensorsteuerung,
        )

    def setze_simulation_aktiv(self, aktiv):
        """Fluechtige Steuerungsuebergabe; kein Reset und keine Sensorausgabe.

        Spaetere REST-Aktivierung ruft diese Methode im selben asyncio-Loop auf.
        Manuelle PUTs uebernehmen vor dem Schreiben ueber den Callback die
        Steuerung zurueck. Uebergabe und Sensorzugriffe enthalten kein await;
        Threads/IRQs duerfen diesen Laufzeitschalter nicht bedienen.
        """
        if not isinstance(aktiv, bool):
            raise ValueError("aktiv muss bool sein")
        if aktiv != self._simulation_aktiv:
            self._simulation_zeit_ms = None
        self._simulation_aktiv = aktiv

    def _uebernehme_manuelle_sensorsteuerung(self):
        self.setze_simulation_aktiv(False)

    def lese_simulationsstatus(self):
        """RAM-Diagnose fuer die spaetere REST-Schicht, inklusive echtem Druck.

        ausgabe_ok beschreibt den letzten Zyklus, keine Hardware-Rueckmessung.
        Eingangsdetails bleiben in hardware.lese_status()['eingangs_fehler'].
        """
        status = self.simulation_manager.lese_zustand()
        status["aktiv"] = self._simulation_aktiv
        status["steuerung"] = "simulation" if self._simulation_aktiv else "manuell"
        status["task_fehler"] = self.simulation_fehler
        status["task_fehlerdetail"] = self.simulation_fehlerdetail
        status["letzter_task_fehler"] = self.simulation_letzter_fehler
        status["intervall_ms"] = self._simulation_intervall_ms
        status["ausgabe_ok"] = self.simulation_ausgabe_ok
        return status

    def _melde_simulationsfehler(self, meldung, exc=None):
        # Zuerst Zeitbasis sperren: keine Fehler-/Wartezeit nachholen.
        self._simulation_zeit_ms = None
        self.simulation_ausgabe_ok = False
        vorher = self.simulation_fehler
        self.simulation_fehler = meldung
        self.simulation_letzter_fehler = meldung
        self.simulation_fehlerdetail = None
        try:
            if exc is not None:
                self.simulation_fehlerdetail = str(exc)
            if meldung != vorher:
                print("Simulation:", meldung, self.simulation_fehlerdetail)
        except Exception:
            # Auch Diagnose-/Speicherfehler duerfen andere Tasks nicht beenden.
            pass

    def _simulationszyklus(self):
        """Verknuepft bestaetigte Eingaenge, Physik und Sensorfachlogik ohne await."""
        self._simulation_fehlerphase = "SIMULATION_ZEITFEHLER"
        jetzt = ticks_ms()
        vorher = self._simulation_zeit_ms
        self._simulation_zeit_ms = jetzt
        self._simulation_fehlerphase = "SIMULATION_EINGANGSFEHLER"
        ventil = self.hardware.ist_friwa_aktiv()
        heizung = self.hardware.ist_heizung_aktiv()
        pumpe = self.hardware.ist_abwasserpumpe_aktiv()
        if ventil is None or heizung is None or pumpe is None:
            self._melde_simulationsfehler("SIMULATION_EINGANG_UNBEKANNT")
            return
        # Erster bestaetigter Snapshot nach Aktivierung/Fehler ist nur Zeitbasis.
        if vorher is None:
            return
        self._simulation_fehlerphase = "SIMULATION_ZEITFEHLER"
        dt_ms = ticks_diff(jetzt, vorher)
        self._simulation_intervall_ms = dt_ms
        if not 0 < dt_ms <= SIMULATION_MAX_INTERVALL_MS:
            self._melde_simulationsfehler("SIMULATION_ZEITSCHRITT_UNGUELTIG")
            return

        self.simulation_ausgabe_ok = False
        self._simulation_fehlerphase = "SIMULATION_BERECHNUNGSFEHLER"
        ok = self.simulation_manager.aktualisieren(dt_ms / 1000.0, ventil, heizung, pumpe)
        self._simulation_fehlerphase = "SIMULATION_ZUSTANDSFEHLER"
        zustand = self.simulation_manager.lese_zustand(self._simulation_zustand)
        if not ok:
            self._melde_simulationsfehler(zustand["fehler"])
            return
        self._simulation_fehlerphase = "SIMULATION_NTC_FEHLER"
        self.ntc_sensor.verarbeite_temperatur(zustand["temperatur_c"], persistieren=False)
        self._simulation_fehlerphase = "SIMULATION_DRUCK_FEHLER"
        self.druck_sensor.verarbeite_druck_pa(zustand["druck_sensor_pa"], persistieren=False)
        self.simulation_ausgabe_ok = True
        self.simulation_fehler = None
        self.simulation_fehlerdetail = None

    async def simulation_task(self):
        """Eigene 100-ms-Task; Fehler isolieren, ausgefallene Zeit verwerfen."""
        try:
            while True:
                try:
                    if self._simulation_aktiv:
                        self._simulationszyklus()
                    else:
                        self._simulation_zeit_ms = None
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    self._melde_simulationsfehler(self._simulation_fehlerphase, exc)
                try:
                    if hasattr(asyncio, "sleep_ms"):
                        await asyncio.sleep_ms(SIMULATION_TASK_INTERVAL_MS)
                    else:
                        await asyncio.sleep(SIMULATION_TASK_INTERVAL_MS / 1000.0)
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    # Ohne funktionierendes Warten keine blockierende Fehler-Schleife.
                    self._melde_simulationsfehler("SIMULATION_WARTEFEHLER", exc)
                    return
        except asyncio.CancelledError:
            self._melde_simulationsfehler("SIMULATION_TASK_BEENDET")
            raise
        finally:
            self.setze_simulation_aktiv(False)
            self._simulation_zeit_ms = None

    def initialisiere_hardware(self):
        self.hardware.initialisiere_hardware()
        self.hardware.setze_sicheren_zustand()
        try:
            display = self.hardware.initialisiere_display()
            if display is not None:
                self.display_manager = DisplayManager(display)
        except Exception as exc:
            self.display_manager = None
            print("Optionales Display nicht verfuegbar: {}".format(exc))

    def _ui_event(self, event_type, payload):
        if self.display_manager is None:
            return
        if event_type == "temperature_updated":
            self.display_manager.ntc_update(payload)
        elif event_type == "pressure_updated":
            self.display_manager.druck_update(payload)
        elif event_type == "status_requested":
            self.display_manager.statusanzeige(payload)

    def _aktualisiere_basisdaten(self):
        if self.display_manager is None:
            return
        status = self.hardware.lese_status()
        heizung = None
        if self.hardware.hat_heizungseingang():
            heizung = status.get("heizung_aktiv")
        friwa = None
        if self.hardware.hat_friwa_eingang():
            friwa = status.get("friwa_aktiv")
        pressure_pa = status.get("pressure_pa", 0.0)
        self.display_manager.aktualisiere_basiswerte(
            status.get("temperature_1_c", 0.0),
            status.get("temperature_2_c", 0.0),
            pressure_pa,
            self.druck_sensor.berechne_druck_mmws(pressure_pa),
            heizung,
            friwa,
        )
        self.display_manager.update()

    async def system_task(self):
        while True:
            try:
                self._aktualisiere_basisdaten()
            except Exception as exc:
                print("Optionaler Display-Systemtask fehlgeschlagen: {}".format(exc))
            if hasattr(asyncio, "sleep_ms"):
                await asyncio.sleep_ms(SYSTEM_TASK_INTERVAL_MS)
            else:
                await asyncio.sleep(SYSTEM_TASK_INTERVAL_MS / 1000.0)

    async def digitale_eingaenge_task(self):
        """Beobachtet Relaiskontakte unabhaengig von Display und HTTP-Anfragen."""
        letzter_fehler = None
        fehlerphase = ABTASTFEHLER
        try:
            while True:
                fehlerphase = ABTASTFEHLER
                try:
                    self.hardware.aktualisiere_digitale_eingaenge()
                except asyncio.CancelledError:
                    raise
                except MemoryError:
                    meldung = ABTAST_SPEICHERFEHLER
                except Exception:
                    meldung = ABTASTFEHLER
                else:
                    meldung = None

                if meldung is not None:
                    # Bestehenden Slot sperren, bevor auch der Fehlerpfad scheitern kann.
                    self.hardware.eingangs_abtastfehler = meldung
                    fehlerphase = ABTAST_INVALIDIERUNGSFEHLER
                    self.hardware.markiere_digitale_eingaenge_unbekannt(meldung)
                    fehlerphase = ABTAST_DIAGNOSEFEHLER
                    if meldung != letzter_fehler:
                        print(meldung)
                elif letzter_fehler is not None:
                    fehlerphase = ABTAST_DIAGNOSEFEHLER
                    print(ABTASTUNG_WIEDERHERGESTELLT)
                letzter_fehler = meldung
                fehlerphase = ABTAST_WARTEFEHLER
                if hasattr(asyncio, "sleep_ms"):
                    await asyncio.sleep_ms(EINGANG_ABTASTINTERVALL_MS)
                else:
                    await asyncio.sleep(EINGANG_ABTASTINTERVALL_MS / 1000.0)
        except asyncio.CancelledError:
            self.hardware.eingangs_abtastfehler = ABTASTTASK_BEENDET
            raise
        except BaseException:
            # Fehler im Fehlerpfad/Warten: gesperrt abbrechen, niemals still fortsetzen.
            self.hardware.eingangs_abtastfehler = fehlerphase
            raise

    async def _display_waehrend_netzwerkstart(self):
        """Laesst Boot-/WLAN-Anzeige laufen, ohne den Netzwerkstart zu blockieren."""
        while self._netzwerk_start_laeuft:
            if self.display_manager is not None:
                self.display_manager.update()
            if hasattr(asyncio, "sleep_ms"):
                await asyncio.sleep_ms(SYSTEM_TASK_INTERVAL_MS)
            else:
                await asyncio.sleep(SYSTEM_TASK_INTERVAL_MS / 1000.0)

    async def starte_system(self):
        # Auch Speicherfehler beim Erzeugen der Coroutine/Task lassen nichts gueltig.
        self.hardware.eingangs_abtastfehler = ABTASTTASK_BEENDET
        tasks = [asyncio.create_task(self.digitale_eingaenge_task())]
        try:
            if self.display_manager is not None and NETWORK_MODE == "auto":
                self.display_manager.wlan_connecting()

            self._netzwerk_start_laeuft = True
            if self.display_manager is not None:
                tasks.append(asyncio.create_task(self._display_waehrend_netzwerkstart()))

            try:
                netzwerk_status = await self.network_manager.starte(NETWORK_MODE)
            finally:
                self._netzwerk_start_laeuft = False
            if not netzwerk_status.get("ok"):
                self.hardware.setze_sicheren_zustand()
                raise RuntimeError("Kein REST-faehiger Netzwerkmodus")

            if self.display_manager is not None:
                self.display_manager.netzwerk_bereit(
                    netzwerk_status.get("mode") == "access_point"
                )

            tasks.append(asyncio.create_task(self.system_task()))
            tasks.append(asyncio.create_task(self.simulation_task()))
            await self.rest_server._starte_server_async()
        finally:
            # Gilt auch, wenn eine Task vor ihrer ersten Ausfuehrung abgebrochen wird.
            if self.hardware.eingangs_abtastfehler is None:
                self.hardware.eingangs_abtastfehler = ABTASTTASK_BEENDET
            for task in tasks:
                task.cancel()
            for task in tasks:
                try:
                    await task
                except asyncio.CancelledError:
                    pass


async def _main_async():
    anwendung = SystemAnwendung()
    anwendung.initialisiere_hardware()
    await anwendung.starte_system()


def main():
    asyncio.run(_main_async())


if __name__ == "__main__":
    main()

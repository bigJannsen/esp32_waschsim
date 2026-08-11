# ESP32 Waschsim – Sensor-Emulation für Waschautomaten

Firmware für ein ESP32-basiertes Sensor-Emulationssystem im Rahmen eines Technikerprojekts.

Das System emuliert ausgewählte Sensorsignale eines gewerblichen Waschautomaten und ermöglicht reproduzierbare Trockenlauftests ohne realen Wasser- oder Heizbetrieb.

Die Sensorwerte werden über eine REST-Schnittstelle vorgegeben und vom ESP32 in die entsprechenden elektrischen Ausgangssignale umgesetzt.

---

## Projektziel

Emuliert werden aktuell:

- zwei NTC-Temperaturfühler
- ein elektronischer Drucksensor
- Heizungsstatus als digitaler Eingang

Die Ansteuerung erfolgt über:

- 2 × MCP4161-503 Digitalpotentiometer für die NTC-Emulation
- PWM-Ausgang für die Drucksensor-Emulation
- GPIO-Eingang zur Erkennung des Heizungsrelais
- SSD1306 OLED zur lokalen Statusanzeige
- WLAN und REST-API zur externen Vorgabe der Sensorwerte

Der ESP32 übernimmt keine eigenständige Waschprogrammsteuerung.

Die zeitliche Vorgabe der Sensorwerte erfolgt durch einen externen Client.

---

# Systemarchitektur

Die Firmware ist modular aufgebaut.

```text
main.py
│
├── network_manager.py
├── rest.py
├── sensors.py
├── hardware.py
└── display.py
```

Die einzelnen Module haben klar getrennte Verantwortlichkeiten.

### `main.py`

Zentraler Einstiegspunkt der Firmware.

Aufgaben:

- Komponenten erzeugen
- Hardware initialisieren
- sicheren Ausgangszustand setzen
- Netzwerk starten
- OLED einbinden
- REST-Server starten
- zyklischen Systemtask ausführen

`main.py` enthält keine Sensorberechnungen und keine direkten GPIO-Zugriffe.

### `network_manager.py`

Verwaltet ausschließlich die Netzwerkkommunikation.

Unterstützte Betriebsarten:

```python
NETWORK_MODE = "legacy_ap"
```

oder

```python
NETWORK_MODE = "auto"
```

`legacy_ap` startet direkt den bekannten Access Point.

`auto` versucht zunächst eine Verbindung zu einem konfigurierten WLAN und startet bei einem Verbindungsfehler automatisch den Access Point.

### `rest.py`

Stellt die HTTP-/REST-Schnittstelle bereit.

Aufgaben:

- HTTP-Anfragen verarbeiten
- JSON-Daten prüfen
- Wertebereiche validieren
- gültige Werte an die Sensorlogik übergeben
- Statusinformationen bereitstellen
- semantische UI-Ereignisse erzeugen

REST und Display sind nicht direkt gekoppelt.

### `sensors.py`

Enthält die fachliche Sensorlogik.

Aufgaben:

- NTC-Kennlinie
- Temperatur → Widerstand
- Widerstand → Digitalpotentiometer-Code
- Druck → PWM-Duty-Cycle
- Druck Pa → mmWS
- Wertebereichsprüfung

### `hardware.py`

Einzige Schicht mit direkten Hardwarezugriffen.

Enthält:

- GPIO
- SPI
- PWM
- I²C
- Digitalpotentiometer
- SSD1306
- Heizungseingang
- Persistenz
- sicheren Hardwarezustand

### `display.py`

Verwaltet ausschließlich die OLED-Benutzeroberfläche.

Das Modul bekommt bereits fertig berechnete Werte und führt selbst keine Sensorberechnungen durch.

---

# Hardware

## ESP32

Zentrale Steuereinheit:

- ESP32-WROOM
- MicroPython

## Temperatur-Emulation

Die zwei NTC-Sensoren werden durch zwei Digitalpotentiometer vom Typ

```text
MCP4161-503
```

emuliert.

Nominaler Widerstand:

```text
50 kΩ
```

Die Temperatur wird anhand einer hinterlegten NTC-Kennlinie in einen entsprechenden Digitalpotentiometerwert umgerechnet.

Temperaturbereich:

```text
0 °C ... 100 °C
```

Die beiden NTC-Kanäle können gemeinsam oder unabhängig voneinander angesteuert werden.

---

## Drucksensor-Emulation

Der Drucksensor wird über ein PWM-Signal emuliert.

PWM-Frequenz:

```text
1000 Hz
```

Kennlinie:

```text
0 Pa       → 23,3 % Duty
2452 Pa    → 90,0 % Duty
```

Der Zusammenhang wird linear interpoliert.

Zusätzlich wird der Druck für die Anzeige in Millimeter Wassersäule umgerechnet:

```text
mmWS = Pa / 9,81
```

---

# Pinbelegung

## Bestehende Sensorhardware

| Funktion | ESP32 |
|---|---:|
| NTC1 DigiPoti CS | GPIO5 |
| NTC2 DigiPoti CS | GPIO18 |
| DigiPoti SPI SCK | GPIO19 |
| DigiPoti SPI MOSI / Data | GPIO23 |
| DigiPoti SPI MISO | GPIO12 |
| Drucksensor PWM | GPIO25 |

Die bestehende Sensorverdrahtung bleibt gegenüber dem bisherigen Hardwarestand unverändert.

---

# OLED-Display

Verwendet wird ein:

```text
SSD1306
128 × 64 Pixel
I²C
```

Verdrahtung:

| OLED | ESP32 |
|---|---|
| VCC | 3V3 |
| GND | GND |
| SDA | GPIO21 |
| SCL | GPIO22 |

Firmwarekonfiguration:

```python
DISPLAY_I2C_ID = 0
DISPLAY_SDA = 21
DISPLAY_SCL = 22
DISPLAY_WIDTH = 128
DISPLAY_HEIGHT = 64
DISPLAY_FREQ = 400_000
```

Das OLED ist optional.

Kann das Display nicht initialisiert werden, laufen Netzwerk, REST-API und Sensor-Emulation weiterhin.

---

# Heizungserkennung

Der Zustand der Maschinenheizung soll über einen potentialfreien Relaiskontakt eingelesen werden.

Vorgesehene Verdrahtung:

```text
GPIO32
  │
  └──── potentialfreier Relaiskontakt ──── GND
```

Der Eingang arbeitet mit internem Pull-up.

Logik:

```text
Kontakt offen
→ GPIO HIGH
→ Heizung AUS

Kontakt geschlossen
→ GPIO LOW
→ Heizung EIN
```

Der vorgesehene Eingang ist:

```text
GPIO32
```

Vor dem Hardwaretest muss in `hardware.py` entsprechend gesetzt werden:

```python
HEIZUNG_GPIO = 32
```

Im aktuellen Entwicklungsstand kann der Heizungseingang auch deaktiviert betrieben werden:

```python
HEIZUNG_GPIO = None
```

> Wichtig: Der GPIO darf ausschließlich über einen potentialfreien bzw. galvanisch getrennten Kontakt geschaltet werden. Netzspannung oder andere Fremdspannungen dürfen niemals direkt mit dem ESP32 verbunden werden.

---

# OLED-Benutzeroberfläche

Die Benutzeroberfläche arbeitet zustandsbasiert.

Unterstützte Zustände:

```text
BOOT
WLAN_CONNECTING
ACCESS_POINT
BASIS
NTC_UPDATE
DRUCK_UPDATE
STATUS
```

## Boot

Anzeige für ungefähr:

```text
5 Sekunden
```

## Basisanzeige

Enthält unter anderem:

```text
Heizung
NTC1
NTC2
Druck in Pa
Druck in mmWS
```

## Temperaturupdate

Nach einem neuen Temperaturkommando wird die Update-Seite ungefähr

```text
10 Sekunden
```

angezeigt.

Danach wird automatisch zur Basisansicht zurückgekehrt.

## Druckupdate

Nach einem Druckkommando:

```text
10 Sekunden
```

## Status

Nach:

```http
GET /api/v1/status
```

wird die Statusseite ungefähr

```text
15 Sekunden
```

angezeigt.

Das Display verwendet Dirty Rendering und wird nur neu gezeichnet, wenn sich sichtbare Daten oder der UI-Zustand ändern.

---

# WLAN

Die Netzwerkparameter befinden sich zentral in:

```text
network_manager.py
```

Aktueller sicherer Default:

```python
NETWORK_MODE = "legacy_ap"
```

## Legacy-AP

Der ESP32 startet direkt einen eigenen Access Point.

Standardkonfiguration:

```python
AP_SSID = "miele"
AP_PASSWORT = "10000000"
```

REST-Server:

```text
Port 8080
```

Typische AP-Adresse:

```text
192.168.4.1
```

Health-Check:

```text
http://192.168.4.1:8080/api/v1/health
```

---

## Automatischer WLAN-Modus

Für den automatischen Modus:

```python
NETWORK_MODE = "auto"

STA_SSID = "WLAN-NAME"
STA_PASSWORT = "WLAN-PASSWORT"
```

Ablauf:

```text
ESP32 startet
      │
      ▼
STA-WLAN verbinden
      │
      ├── erfolgreich
      │      │
      │      └── REST über Router-IP
      │
      └── Fehler / Timeout
             │
             ▼
       Access Point starten
             │
             ▼
       REST über AP
```

Standardtimeout:

```python
WLAN_TIMEOUT_S = 20
```

Der Auto-Modus wurde softwareseitig mit Mocktests geprüft.

Der reale Wechsel

```text
STA → Timeout → AP
```

muss zusätzlich auf der ESP32-Zielhardware validiert werden, bevor `auto` dauerhaft als Standard verwendet wird.

---

# REST-API

Basis:

```text
/api/v1
```

Port:

```text
8080
```

Unterstützte Endpunkte:

| Methode | Endpoint | Funktion |
|---|---|---|
| GET | `/api/v1/health` | Health-Check |
| GET | `/api/v1/status` | Systemstatus |
| PUT | `/api/v1/sensors/temperature` | NTC-Temperaturen setzen |
| PUT | `/api/v1/sensors/pressure` | Druck setzen |

---

# Temperatur setzen

## Beide NTCs auf gleiche Temperatur

```http
PUT /api/v1/sensors/temperature
Content-Type: application/json
```

```json
{
  "mode": "same",
  "temperature_c": 25.0
}
```

Ergebnis:

```text
NTC1 = 25 °C
NTC2 = 25 °C
```

---

## NTCs getrennt setzen

```json
{
  "mode": "separate",
  "temperature_1_c": 25.0,
  "temperature_2_c": 60.0
}
```

Ergebnis:

```text
NTC1 = 25 °C
NTC2 = 60 °C
```

---

## Einzelnen NTC setzen

NTC1:

```json
{
  "channel": 1,
  "temperature_c": 40.0
}
```

NTC2:

```json
{
  "channel": 2,
  "temperature_c": 40.0
}
```

Der jeweils andere Kanal behält seinen vorherigen Wert.

---

# Druck setzen

```http
PUT /api/v1/sensors/pressure
Content-Type: application/json
```

Beispiel:

```json
{
  "pressure_pa": 1200.0
}
```

Gültiger Bereich:

```text
0 ... 2452 Pa
```

---

# Status

```http
GET /api/v1/status
```

Die Antwort enthält unter anderem:

- API-Version
- Hardwarestatus
- NTC1-Temperatur
- NTC2-Temperatur
- Digitalpotentiometercodes
- Druck
- PWM-Duty
- Druck in mmWS
- zuletzt ausgeführten Sensorbefehl

---

# Health-Check

```http
GET /api/v1/health
```

Beispiel:

```json
{
  "ok": true,
  "service": "esp32_waschsim",
  "version": "v1"
}
```

---

# Persistenz

Der zuletzt bekannte fachliche Sensorzustand wird persistent gespeichert.

Gespeichert werden unter anderem:

```text
temperature_1_c
temperature_2_c
ntc_code_1
ntc_code_2
pressure_pa
pwm_duty
```

Der physische Safe-State beim Boot ist von der Persistenz getrennt.

Das bedeutet:

```text
Boot
 ↓
Hardware zunächst sicher
 ↓
gespeicherte Diagnose-/Sollwerte bleiben erhalten
```

Ein Safe-State überschreibt somit nicht automatisch die gespeicherten letzten Sensorwerte.

---

# Asynchrone Verarbeitung

Die Firmware verwendet:

```text
uasyncio
```

REST-Server und Systemtask laufen kooperativ im selben Eventloop.

Der Systemtask läuft aktuell ungefähr alle:

```text
200 ms
```

und übernimmt unter anderem:

- Displayaktualisierung
- Heizungsstatus
- UI-Timeouts
- Basisdaten

---

# Lokale Tests

Die Test-Suite wird mit:

```bash
pytest -q
```

ausgeführt.

Die Tests verwenden Fake-/Mock-Hardware und benötigen keinen ESP32.

Abgedeckt werden unter anderem:

- NTC-Berechnung
- Druckberechnung
- REST-API
- getrennte NTC-Kanäle
- Persistenz
- Safe-State
- NetworkManager
- STA-Timeout
- AP-Fallback
- OLED-Zustände
- UI-Timeouts
- REST-/Display-Ereignisse

Mocks befinden sich ausschließlich im Testcode.

Produktionsmodule importieren keine Mock- oder Fake-Hardware.

---

# Was kommt auf den ESP32?

Für die produktive Firmware werden grundsätzlich benötigt:

```text
main.py
hardware.py
sensors.py
rest.py
network_manager.py
display.py
ssd1306.py
```

Zusätzlich gegebenenfalls:

```text
config.json
```

Die Pytest-Dateien und Mockklassen werden nicht auf den ESP32 kopiert.

---

# Hardware-Inbetriebnahme

Empfohlene Reihenfolge:

1. ESP32 und OLED ohne Waschmaschine starten
2. OLED prüfen
3. Legacy-Access-Point prüfen
4. `/api/v1/health` prüfen
5. GPIO32 manuell gegen GND brücken und Heizungsanzeige prüfen
6. REST-Temperaturbefehle testen
7. REST-Druckbefehle testen
8. PWM-Ausgang mit Oszilloskop prüfen
9. NTC-Widerstände messen
10. potentialfreien Heizungsrelaiskontakt anschließen
11. Sensorleitungen mit der Maschinensteuerung verbinden
12. kontrollierten Trockenlauf durchführen
13. anschließend Auto-WLAN auf echter Hardware testen

---

# Netzwerk-Hardwaretest

Bevor

```python
NETWORK_MODE = "auto"
```

dauerhaft verwendet wird, müssen mindestens zwei Fälle getestet werden.

## STA erfolgreich

```text
gültige SSID
→ ESP verbindet sich
→ IP vom Router
→ /api/v1/health = HTTP 200
```

## AP-Fallback

Absichtlich ungültige SSID:

```text
ESP startet
→ STA-Verbindungsversuch
→ Timeout
→ AP "miele"
→ Verbindung zum AP
→ /api/v1/health = HTTP 200
```

Der Fallback sollte zusätzlich über mehrere ESP32-Neustarts überprüft werden.

---

# Aktueller Entwicklungsstand

| Bereich | Status |
|---|---|
| Modulare Firmwarearchitektur | ✅ |
| NTC1 / NTC2 getrennt | ✅ |
| MCP4161-Ansteuerung | ✅ |
| Drucksensor-PWM | ✅ |
| REST-API | ✅ |
| Persistenz | ✅ |
| Safe-State-Trennung | ✅ |
| OLED-UI | ✅ |
| UI-Ereignisse | ✅ |
| Legacy-Access-Point | ✅ hardwareerprobt |
| STA-Modus | ✅ implementiert |
| AP-Fallback | ✅ Mock-getestet |
| Auto-WLAN auf Zielhardware | 🧪 noch zu validieren |
| Heizungseingang GPIO32 | 🧪 Hardwaretest ausstehend |
| Gesamter Trockenlauf an Waschmaschine | 🧪 ausstehend |

---

# Offene Punkte

Für die nächsten Entwicklungs- und Testschritte stehen insbesondere noch an:

- Heizungseingang GPIO32 auf Hardware validieren
- OLED auf realer Hardware vollständig prüfen
- STA-WLAN auf ESP32 testen
- realen AP-Fallback prüfen
- NTC-Ausgangswiderstände vermessen
- PWM-Signal elektrisch vermessen
- Sensorwerte mit der Maschinensteuerung validieren
- MCP4161-Quantisierung bei Bedarf kalibrieren
- Dauerlauf-/Stabilitätstest durchführen

---

# Sicherheit

Das Projekt arbeitet teilweise in Verbindung mit einer Waschmaschinensteuerung und deren Leistungselektronik.

Der ESP32 darf ausschließlich mit geeigneten Kleinspannungs- und galvanisch getrennten Signalen verbunden werden.

Insbesondere:

- keine Netzspannung direkt an ESP32-GPIOs
- Heizungsstatus nur über potentialfreien oder galvanisch getrennten Kontakt
- gemeinsame Masse nur dort verwenden, wo dies schaltungstechnisch vorgesehen ist
- elektrische Ausgänge vor Anschluss an die Maschinensteuerung messen

---

# Projekt

Technikerprojekt – Sensoremulation eines Waschautomaten

Firmware:

```text
ESP32
MicroPython
REST
uasyncio
MCP4161
SSD1306
```

Ziel ist eine reproduzierbare und modular erweiterbare Emulation realer Sensorsignale für Trockenlauf- und Funktionstests.

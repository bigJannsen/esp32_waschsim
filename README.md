🔷 Stufe 9 – Erweiterung & Professionalisierung
Ziel

Nach erfolgreicher Implementierung von Stufe 1–8 wird das System technisch erweitert, strukturell professionalisiert und für reale Hardwarebedingungen optimiert.

1️⃣ WLAN-Modus erweiterbar machen (AP + STA)
Ziel:

Flexible Netzwerkanbindung.

Umsetzung:

Betriebsmodus konfigurierbar:

"AP"

"STA"

"AUTO" (erst STA versuchen, sonst AP)

WLAN-Konfiguration persistent speicherbar

Keine Architekturänderung in rest.py

Begründung:

Erhöht reale Einsatzfähigkeit.

2️⃣ Sensor-Vererbungshierarchie einführen
Ziel:

Reduktion redundanter Logik.

Strukturvorschlag:
class SensorBasis:
    - Validierung
    - Bereichsprüfung
    - Statusverwaltung

class AnalogerSensor(SensorBasis):
    - Normierungsmethoden

class TemperaturSensor(AnalogerSensor)

class NtcSensor(TemperaturSensor)

class PressureSensor(AnalogerSensor)
Nutzen:

Einheitliche Schnittstellen

Weniger Duplikate

Saubere Erweiterbarkeit

3️⃣ DAC-basierte NTC-Simulation evaluieren
Hintergrund:

Aktuell:

2x MCP4161 (50 kΩ)

Widerstandsquantisierung

Zukunft:

DAC mit Imax 2.5 mA

Direkte Spannungssteuerung

Ziel:

Genauere Simulation

Weniger Quantisierungsfehler

Vereinfachte Hardware

4️⃣ Rampen- und Zeitverhalten implementieren
Ziel:

Realistische Sensorverläufe.

Features:

Temperatur-Rampe

Zeitkonstante

Aufheiz- / Abkühlmodell

Periodische Aktualisierung

5️⃣ HTTPS-Unterstützung (optional)
Ziel:

Sichere REST-Kommunikation.

Umsetzung:

SSL-Kontext

Optional aktivierbar

Nur bei STA sinnvoll

6️⃣ Logging-Subsystem
Ziel:

Diagnosefähigkeit erhöhen.

Features:

Log-Level (INFO / WARN / ERROR)

Optional seriell ausgebbar

Keine Performance-Beeinträchtigung

7️⃣ Integrationstest-Automatisierung
Ziel:

Wiederholbare Tests.

Features:

Test-Suite für:

Temperaturpfad

Druckpfad

Persistenz

Fehlerfälle

Optional CI-kompatibel

8️⃣ Elektrische Validierung & Kalibrierung
Ziel:

Physikalische Genauigkeit erhöhen.

Maßnahmen:

Messung gegen reale NTC

Fehleranalyse (Quantisierung)

LSB-Optimierung

ggf. Nichtlinearitätskorrektur

9️⃣ Performance- und Speicheroptimierung
Ziel:

Stabilität im Dauerbetrieb.

Prüfung:

Heap-Nutzung

Event-Loop-Stabilität

Flash-Schreibzyklen

RAM-Leaks

🔷 Aktueller Stand
Bereich	Status
Architektur	✔
Async REST	✔
Persistenz	✔
Digipot-Integration	✔
End-to-End-Test	✔
Vererbung	🔜
WLAN-Fallback	🔜
DAC-Option	🔜
🔷 Langfristige Vision

ESP32 Waschsim als:

Modularer Sensoremulator

REST-basiertes Testgerät

Hardwareunabhängige Simulationsplattform

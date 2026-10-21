# Michi´s Steuerung

Stabile Version **V0.2 (0.2.0)** für Home Assistant. Eine lokale Steuerung für wassergekühlte Miner und 0–10-V-Lüfter über Loxone. V0.2 entspricht funktional dem vom Anwender bestätigten Beta3-Stand.

## Funktionen

- Miner-Grundwasserventil: höchste von 16 Chiptemperaturen aus vier Minern über MQTT regelt einen gemeinsamen 0–10-V-Stellwert.
- Bis zu 20 unabhängige, frei benennbare Lüfterregler: ESP32-DHT22-Temperatur und Feuchte über Modbus TCP, Stellwert über UDP an Loxone.
- Pro Regler einstellbare Temperaturgrenzen, Spannungsschritte, Wartezeit und Schnellreaktion bei plötzlichem Temperaturanstieg.
- Pro Lüfter einstellbare Mindest-/Höchstspannung und Verhalten bei Automatik aus: Mindestspannung, letzten Wert halten oder 0 V.
- Geräteanlage über **Einstellungen → Geräte & Dienste → Michi´s Steuerung → Gerät hinzufügen**.
- Eigene Bedienseite mit einklappbaren Geräten, breiten Diagrammen und offen sichtbaren Regler-Einstellungen. Verbindungen und Namen separat einklappbar.
- Diagrammzeiträume 15 Minuten, 1 Stunde, 6 Stunden und 24 Stunden. Verlauf im Arbeitsspeicher seit Start, maximal 24 Stunden; nach Neustart beginnt der Verlauf neu.
- Gewähltes M-Icon lokal im Integrationspaket enthalten.

## Voraussetzungen

Home Assistant Core **2026.10.1 oder neuer** und eine eingerichtete MQTT-Integration für den Miner-Regler. Der Miner-Regler muss zuerst eingerichtet und geladen sein, danach lassen sich zusätzliche Lüfter anlegen. Für die Lüfter Modbus in der ESP32-Firmware DHT22 Klima aktivieren. In Loxone werden passende virtuelle UDP-Eingänge für die einzelnen Ausgänge benötigt. Mehr Spannung bedeutet mehr Kühlung.

## Installation mit HACS

1. HACS → ⋮ → Benutzerdefinierte Repositories öffnen.
2. `https://github.com/Mib83/michis-steuerung` hinzufügen; Kategorie **Integration**.
3. **Michi´s Steuerung** herunterladen und Home Assistant vollständig neu starten.
4. **Einstellungen → Geräte & Dienste → Integration hinzufügen → Michi´s Steuerung** öffnen und den Miner-Regler einrichten.
5. Weitere Lüfter über **Gerät hinzufügen → 0-10V Lüftersteuerung Loxone** anlegen.

Für ein Update in HACS **Informationen aktualisieren → Erneut herunterladen** wählen und Version **v0.2.0** installieren. Home Assistant vollständig neu starten; bei Bedarf Browser mit **⌘+Umschalt+R** neu laden. Bestehende Integration und Geräte behalten. Nach dem Neustart die gewünschten Automatiken wieder einschalten.

Manuell: `custom_components/michis_steuerung` in das Home-Assistant-Konfigurationsverzeichnis kopieren und Home Assistant neu starten.

## Vorbereitete Reglerwerte

| Regler | Temperaturbereich | Schrittweite | Wartezeit | Stellbereich |
|---|---|---|---|---|
| Miner-Grundwasserventil | 43–44 °C | 0,2 V | 15 s | 0–10 V |
| Lüfter | 27–28 °C | 0,2 V | 120 s | 2–10 V, einstellbar |

Schnellreaktion standardmäßig ab 3 °C Anstieg mit 0,6 V Schritt, jeweils einstellbar. Unveränderte Stellwerte werden nicht periodisch erneut gesendet.

## MQTT und Modbus

Für jeden Miner einen Basispfad konfigurieren, z. B. `4A/Miner/M63S-1`. Darunter `ths/state` und `sm0/state` bis `sm3/state` mit numerischen Nutzlasten, z. B. `43.2`. Groß-/Kleinschreibung beachten, Messwerte mit `retain: false` senden. Alle 16 frischen Temperaturen sind für die Miner-Automatik erforderlich.

Lüfter-Temperaturquelle: ESP32 DHT22 Klima, standardmäßig TCP-Port 502, Geräteadresse 1, Funktion 3. Register 0: Temperatur signed int16 /100; Register 1: Feuchte /100; Register 2: Messwertgültigkeit (3 = beide gültig). Abfrage zusammen alle 5 Sekunden. Ungültige Werte oder Kommunikationsfehler halten den Stellwert und werden angezeigt.

UDP-Beispiele: `MinerGrundwasser:4.3` oder `Luefter:2.0`. Ziel-IP, Port und Befehlsname müssen zum jeweiligen virtuellen UDP-Eingang in Loxone passen. Pro Ausgang nur einen aktiven Regler verwenden.

## Betrieb und Übernahme

Einstellungen, Namen, Verbindungen und zuletzt gesendeter Stellwert bleiben bei Updates erhalten. Vorhandene Beta1-Lüfter werden automatisch in eigene Home-Assistant-Einträge übernommen; nicht erneut anlegen.

Beim Start sind alle Automatiken ausgeschaltet und es wird kein Stellwert gesendet. Fehlen frische gültige Messwerte, hält die Regelung den bisherigen Stellwert. UDP bestätigt keinen Empfang. Die angezeigte Spannung ist ein Stellsignal, keine gemessene Ausgangsspannung, Ventilposition oder Drehzahl. Beide Speichern-Schaltflächen beim Lüfter übernehmen sämtliche bearbeiteten Einstellungen dieses Lüfters.

Bei einer noch vorhandenen alten Domain `miner_ventiel_grundwasser_regler` die bisherige Integration vor der einmaligen Übernahme nicht löschen. Die neue Integration erkennt den alten Eintrag, bietet die Übernahme an und deaktiviert den früheren Regler. Erst nach Prüfung den alten Eintrag entfernen.

## Validierung und Entwicklung

Der Anwender hat Beta3 in seiner Installation als funktionierend bestätigt. Die Entwicklung umfasst 58 lokale Backend-Tests mit simulierten HA-Schnittstellen sowie UI-Verhaltenstests und Browser-Vorschauen mit simulierten Messwerten. Ein automatisierter vollständiger HA-Installationstest wurde nicht durchgeführt. V0.2 ändert gegenüber Beta3 keine Regelfunktion.

```sh
python3 tests/test_controller.py
node tests/test_ui.cjs
```

Fehler und Verbesserungen bitte unter [Issues](https://github.com/Mib83/michis-steuerung/issues) melden. Eine Open-Source-Lizenz ist noch nicht festgelegt.


## V0.3-Beta4 – Brauchwasser Regler

Die neue Version ist als Vorabversion V0.3-Beta4 verfügbar. Unter Gerät hinzufügen steht **Brauchwasser Regler** zur Verfügung. Die im Einrichtungsdialog vorbelegten PyLoxone-Entitäten müssen zur Anlage passen. Die zwei Temperatursensoren und Relaisrückmeldungen werden direkt aus Home Assistant gelesen. Schalten erfolgt über die vorhandenen `switch.turn_on`/`switch.turn_off`-Aktionen; zusätzlicher UDP-Transport ist nicht erforderlich.

Nur der obere Heizstab wird im Normalbetrieb und Legionellenprogramm geregelt. Der untere 7,5-kW-Heizstab kann separat über einen manuellen Timer eingeschaltet werden. Zieltemperatur oben, Wiedereinschalten ab und Sperrzeit sind zunächst leer und müssen vor dem Aktivieren gespeichert werden. Ausschalten erfolgt bei Erreichen der Zieltemperatur. Wiedereinschalten erfolgt bei oder unter der eingestellten Wiedereinschalttemperatur, sobald die Sperrzeit abgelaufen ist. Die Sperrzeit beginnt mit bestätigtem Ausschalten über die obere binäre Rückmeldung. Ist nach erstmaligem Start keine frühere Ausschaltzeit bekannt und das Relais aus, beginnt vorsichtshalber die konfigurierte Sperrzeit.

Im Legionellen-Zeitfenster gilt die gesonderte Zieltemperatur. Die normale Schaltdifferenz (Zieltemperatur minus Wiedereinschalttemperatur) wird auf diese Zieltemperatur übertragen. Die Sperrzeit wird auch dabei eingehalten. Dies ist eine Regelung des oberen Fühlers/Heizstabs; es erfolgt keine automatische Prüfung oder Bestätigung einer hygienischen Wirksamkeit für den gesamten Speicher oder Leitungen. Zieltemperatur und Zeitfenster haben keine vorgegebenen Werte. Bei gesetztem Pumpen-Häkchen läuft die Zirkulation während des gesamten Legionellen-Zeitfensters.

Jedes reguläre Zirkulations-Zeitfenster hat eigene Wochentage und Ein-/Aus-Zeiten. Überlappende Zeitfenster gelten gemeinsam. Bei Zeitfenstern über Mitternacht gehört der Anteil am Folgetag zum ausgewählten Starttag. Beginn zählt zum Zeitfenster, Endzeit nicht mehr. Außerhalb der Zeitfenster gilt die normale Heizregelung; verpasste Zeitfenster werden nicht nachgeholt.

Automatik aus schaltet oberen Heizstab und Zirkulationspumpe aus. Beim HA-Start wird nichts geschaltet und die Automatik bleibt aus. Ungültige obere Temperatur oder fehlende erforderliche Rückmeldung deaktivieren die Automatik und lösen Ausschaltversuche aus. Bleibt nach einem Schaltbefehl die Loxone-Rückmeldung länger als 15 Sekunden aus, wird ein Fehler angezeigt und die Automatik bleibt aus. Loxone-Rückmeldungen sind keine Strom- oder Kontaktmessung am externen Hager-Schütz. Bei gestörter Kommunikation kann Home Assistant das physische Abschalten nicht garantieren.

Einstellungen und letzte bestätigte Ausschaltzeit werden gespeichert. Das spätere Boilerbild ist noch nicht enthalten. Vorbereitet und mit simulierten HA-Schnittstellen geprüft; noch kein Test an der realen Heizungsanlage.

Das Speicherbild zeigt den oberen Heizstab und die Beschriftung 4 kW bei bestätigter Ein-Rückmeldung grün. Regler- und Zeitfelder sind platzsparend nebeneinander angeordnet.

### Timer Heizstab 7,5 kW (Beta4)

Stunden (0–23) und Minuten (0–59) wählen und Start drücken. Mindestens eine Minute, maximal 23 Stunden 59 Minuten. Der Timer läuft unabhängig vom oberen Automatikschalter; beide Heizstäbe dürfen gleichzeitig laufen. Keine Sperrzeit unten. Stopp oder Zeitablauf sendet AUS; die grüne Anzeige folgt ausschließlich der binären Rückmeldung. Die Laufzeit beginnt mit Start. Nach einem HA-Neustart wird ein unterbrochener Timer nicht fortgesetzt, sondern AUS gesendet und bis zur Rückmeldung wiederholt. Während HA ausgeschaltet oder Loxone nicht erreichbar ist, kann die Integration keinen Abschaltzeitpunkt garantieren.

Beta4: 82 Backend-Tests bestanden, Browser-Vorschau auf Desktop und schmalem Bildschirm geprüft. Kein Test mit realen Heizstäben und kein direkter Test in der Mac-App oder Firefox.

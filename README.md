# Michi´s Steuerung

Eine Home-Assistant-Integration mit eigener Bedienseite für die gemeinsame Grundwasserkühlung von vier wassergekühlten Minern.

## Funktionen

- Vier Miner mit je vier Temperaturen und einer Hashrate über MQTT.
- Regelung anhand der höchsten der 16 Temperaturen.
- Direkte UDP-Stellwertausgabe von 0–10 V an Loxone.
- Einstellbare Temperaturgrenzen, Spannungsschritte und Wartezeit.
- Einstellbare Schnellreaktion bei einem plötzlichen Temperaturanstieg.
- Frei wählbare Miner- und Temperaturnamen sowie MQTT-Basispfade.
- Ein- und ausklappbarer Regler mit kompakter Temperatur-, Stellwert- und Automatik-Anzeige.
- Verlauf für die letzten 60 Minuten seit Start der Integration.

## Voraussetzungen

Home Assistant Core 2026.10.1 oder neuer. Mit 2026.10.1 entwickelt; spätere Versionen sind noch nicht vollständig geprüft. Die MQTT-Integration muss bereits eingerichtet sein. Ein Loxone-UDP-Eingang muss den Zahlenwert aus der Nachricht übernehmen können.

## Installation

### Manuell

Den Ordner `custom_components/miner_ventiel_grundwasser_regler` in den Home-Assistant-Konfigurationsordner kopieren und Home Assistant neu starten. Anschließend unter **Einstellungen → Geräte & Dienste → Integration hinzufügen** nach **Michi´s Steuerung** suchen.

### Über HACS

1. In HACS oben rechts **⋮ → Benutzerdefinierte Repositories** öffnen.
2. `https://github.com/Mib83/michis-steuerung` hinzufügen; Kategorie **Integration**.
3. **Michi´s Steuerung** herunterladen und Home Assistant neu starten.
4. Unter **Einstellungen → Geräte & Dienste → Integration hinzufügen** nach **Michi´s Steuerung** suchen.

Bei einer bereits manuell installierten Version die bestehende Integration weiterverwenden; nicht löschen oder doppelt einrichten. Vor dem Überschreiben die Automatik ausschalten und danach wieder bewusst einschalten.

## MQTT-Format

Pro Miner wird ein Basispfad konfiguriert. Darunter werden `ths/state` und `sm0/state` bis `sm3/state` mit einer numerischen Nutzlast wie `43.2` erwartet. Miner-ID und Groß-/Kleinschreibung müssen mit dem Broker übereinstimmen. Messwerte werden mit `retain: false` veröffentlicht.

## Betrieb

Vor Einsatz dieser Integration andere Regler für denselben Ausgang deaktivieren. Den aktuell benötigten Stellwert zuerst im manuellen Modus senden und den Empfang in Loxone prüfen. Dann Automatik einschalten.

Vorbereitete Werte: Temperaturbereich 43–44 °C, normaler Schritt 0,2 V, Pause 15 Sekunden, Messwertgültigkeit 30 Sekunden. Schnellreaktion: 3 °C Anstieg und 0,6 V Schritt; sämtliche Werte sind einstellbar.

Nach einem Neustart startet die Automatik ausgeschaltet. Einstellungen, Messquellen und der zuletzt gesendete Stellwert werden gespeichert. Fehlt eine der 16 Temperaturen oder ist sie veraltet, bleibt der Stellwert unverändert. Das Einklappen der Anzeige verändert die Regelung nicht.

UDP besitzt keine Empfangsbestätigung. Die angezeigte Spannung ist das gesendete Stellsignal, keine gemessene Ausgangsspannung, Ventilposition oder Durchflussmenge. Eine Ersatzreaktion bei vollständigem Home-Assistant-Ausfall muss auf Loxone-Seite eingerichtet werden.

## Entwicklungsstand

Version 0.1.0 der Oberfläche **Michi´s Steuerung**, aufbauend auf dem bisherigen Miner-Regler. 34 lokale Controller-Tests und Tests der Bedienlogik mit einem simulierten DOM bestanden. Die Integration wird auf einer Testinstallation eingesetzt; ein automatisierter vollständiger HA-Installationstest und ein visueller Browsertest stehen noch aus.


## Fehler melden

Fehler und Verbesserungsvorschläge können unter [Issues](https://github.com/Mib83/michis-steuerung/issues) gemeldet werden.

## Lokale Tests

Die Tests verwenden simulierte Home-Assistant-Schnittstellen und abgefangene UDP-Datagramme. Sie senden keine Befehle an Geräte.

```sh
python3 tests/test_controller.py
node tests/test_ui.cjs
```

## Lizenz

Eine Open-Source-Lizenz ist noch nicht festgelegt.

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

Den Ordner `custom_components/michis_steuerung` in den Home-Assistant-Konfigurationsordner kopieren und Home Assistant neu starten. Anschließend unter **Einstellungen → Geräte & Dienste → Integration hinzufügen** nach **Michi´s Steuerung** suchen.

### Über HACS

1. In HACS oben rechts **⋮ → Benutzerdefinierte Repositories** öffnen.
2. `https://github.com/Mib83/michis-steuerung` hinzufügen; Kategorie **Integration**.
3. **Michi´s Steuerung** herunterladen und Home Assistant neu starten.
4. Unter **Einstellungen → Geräte & Dienste → Integration hinzufügen** nach **Michi´s Steuerung** suchen.

Beim Wechsel von der früheren Domain `miner_ventiel_grundwasser_regler` ist einmalig die unten beschriebene Übernahme erforderlich. Bei späteren Updates innerhalb `michis_steuerung` die bestehende Integration weiterverwenden.

## MQTT-Format

Pro Miner wird ein Basispfad konfiguriert. Darunter werden `ths/state` und `sm0/state` bis `sm3/state` mit einer numerischen Nutzlast wie `43.2` erwartet. Miner-ID und Groß-/Kleinschreibung müssen mit dem Broker übereinstimmen. Messwerte werden mit `retain: false` veröffentlicht.

## Betrieb

Vor Einsatz dieser Integration andere Regler für denselben Ausgang deaktivieren. Den aktuell benötigten Stellwert zuerst im manuellen Modus senden und den Empfang in Loxone prüfen. Dann Automatik einschalten.

Vorbereitete Werte: Temperaturbereich 43–44 °C, normaler Schritt 0,2 V, Pause 15 Sekunden, Messwertgültigkeit 30 Sekunden. Schnellreaktion: 3 °C Anstieg und 0,6 V Schritt; sämtliche Werte sind einstellbar.

Nach einem Neustart startet die Automatik ausgeschaltet. Einstellungen, Messquellen und der zuletzt gesendete Stellwert werden gespeichert. Fehlt eine der 16 Temperaturen oder ist sie veraltet, bleibt der Stellwert unverändert. Das Einklappen der Anzeige verändert die Regelung nicht.

UDP besitzt keine Empfangsbestätigung. Die angezeigte Spannung ist das gesendete Stellsignal, keine gemessene Ausgangsspannung, Ventilposition oder Durchflussmenge. Eine Ersatzreaktion bei vollständigem Home-Assistant-Ausfall muss auf Loxone-Seite eingerichtet werden.

## Entwicklungsstand

Version 0.1.1 der Oberfläche **Michi´s Steuerung**, aufbauend auf dem bisherigen Miner-Regler. 38 lokale Controller-Tests und Tests der Bedienlogik mit einem simulierten DOM bestanden. Die Integration wird auf einer Testinstallation eingesetzt; ein automatisierter vollständiger HA-Installationstest und ein visueller Browsertest stehen noch aus.


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


## Wechsel von der bisherigen technischen Domain

Ab 0.1.1 heißen Integrationsordner, Domain und Bedienseitenpfad **michis_steuerung**. Der bisherige technische Name bleibt ausschließlich als Erkennungsmerkmal für die Übernahme älterer Installationen im Code.

1. Bisherige Automatik ausschalten. Die alte Integration und ihre gespeicherten Einstellungen vorerst **nicht löschen**.
2. Das neue Paket so installieren, dass `/config/custom_components/michis_steuerung/manifest.json` existiert. Für den ersten Wechsel empfiehlt sich das manuelle ZIP-Paket. Der bisherige Ordner darf für die Übernahme vorerst bestehen bleiben.
3. Home Assistant neu starten und die neue Integration mit der Domain `michis_steuerung` hinzufügen. Werden zwei gleichnamige Einträge angeboten, den neuen technischen Namen auswählen.
4. **Bisherige Einstellungen übernehmen** bestätigen. Loxone-Verbindung, MQTT-Basispfade, Anzeigenamen, Grenzen, Pause und Schnellreaktion werden übernommen. Die alte Integration wird vor dem Start der neuen deaktiviert.
5. Werte prüfen. Die neue Automatik bleibt ausgeschaltet, bis sie bewusst aktiviert wird.
6. Erst nach erfolgreicher Prüfung kann die alte deaktivierte Integration entfernt und ihr alter Ordner gelöscht werden. Die importierten Einstellungen sind dann separat unter der neuen Domain gespeichert.

Nicht beide Regler gleichzeitig einschalten. Die Übernahme ist lokal mit simulierten HA-Schnittstellen getestet; ein vollständiger Installationstest dieser Domain-Umstellung in HA steht noch aus.


## V0.2-Beta1: zusätzliche Lüfter

Seit Beta2 werden frei benennbare Lüfter unter **Einstellungen → Geräte & Dienste → Michi´s Steuerung → Gerät hinzufügen → 0-10V Lüftersteuerung Loxone** angelegt. Der Miner-Regler muss zuerst eingerichtet und geladen sein. Vorhandene Beta1-Lüfter werden automatisch übernommen und erscheinen als eigene Einträge; nicht erneut anlegen. ESP32-IP, Loxone-IP, UDP-Port und einen eigenen Befehlsnamen eingeben, z. B. `Luefter:`. In Loxone muss der dazu passende virtuelle UDP-Eingang angelegt und mit dem Lüfterausgang verbunden werden. Mehr Spannung bedeutet mehr Kühlung.

Standardwerte: 27–28 °C, mindestens 2 V, höchstens 10 V, normale Schrittweite 0,2 V, Wartezeit 120 Sekunden. Unter **Einstellungen & Verbindung** sind Name, Grenzen, Wartezeit, Schnellreaktion und Verbindungen anpassbar. Verbindung und Spannungsgrenzen nur bei ausgeschalteter Automatik ändern; reine Reglerwerte können im Betrieb angepasst werden.

ESP32 DHT22 Klima: Modbus aktivieren. TCP-Port 502, Geräteadresse 1, Funktion 3, Registeradresse 0 Temperatur signed int16 /100, 1 Feuchte /100, 2 Gültigkeit. Alle drei Register werden zusammen alle 5 Sekunden gelesen. Ungültige Werte und Fehlerkennungen führen zum Halten des Stellwerts. Längere Verbindungsfehler werden angezeigt. Mindestspannung wird beim Aktivieren einmal gesendet; unveränderte Werte werden nicht periodisch wiederholt. UDP kann den Empfang durch Loxone nicht bestätigen.

**Bei Automatik aus** ist einstellbar: Mindestspannung senden (Standard), letzten Stellwert halten oder ausdrücklich 0 V senden. Ein Neustart sendet nichts und startet alle Automatiken ausgeschaltet. Nach Update/Neustart bitte benötigte Automatiken bewusst wieder aktivieren.

### Beta installieren

In HACS die Integration öffnen, im Drei-Punkte-Menü Informationen aktualisieren und **Erneut herunterladen** wählen. Falls nötig **Andere Version benötigt? / Need a different version?** öffnen und die Beta im Versionsfeld auswählen. Für automatische Beta-Updates kann der HACS-Schalter **Pre-release** für dieses Repository aktiviert werden. Version **v0.2-Beta2** auswählen, herunterladen und Home Assistant neu starten. Danach bei Bedarf den Browser mit ⌘+Umschalt+R neu laden. Die stabile Version v0.1.2 bleibt als normale Version verfügbar.

Die Beta2 ist mit 58 automatisierten Prüfungen und einer Browser-Vorschau mit simulierten Messwerten geprüft. Ein Test in einer echten Home-Assistant-Installation und mit dem ESP32/Loxone wurde hier nicht durchgeführt.


## Diagramme und breite Regler in Beta2

Miner und Lüfter verwenden dieselbe Ausrichtung der Temperatur, Spannung und Schalter. Im aufgeklappten Baustein folgt auf die Messwertkarten ein Diagramm über die ganze verfügbare Breite. Die Regler-Einstellungen stehen offen direkt darunter.

Jedes Diagramm hat eine eigene Zeitwahl: 15 Minuten, 1 Stunde, 6 Stunden oder 24 Stunden. Bis zu 24 Stunden Verlauf werden ab Start im Arbeitsspeicher gesammelt. Ein Update oder Neustart beginnt den Verlauf neu. Bei langen Zeiträumen reduziert die Übertragung die Zahl der Punkte und erhält dabei Spitzen und Messlücken. UDP-Stellwerte sind keine gemessene Ventilposition oder Lüfterdrehzahl.

Die Übernahme von Beta1 speichert die vorhandenen Einstellungen pro Lüfter in einem eigenen Speicher. Sie verändert weder den eingestellten Temperaturbereich noch die Loxone-Befehle. Wie bisher startet keine Automatik von selbst.

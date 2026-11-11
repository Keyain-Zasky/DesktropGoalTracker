# DesktropGoalTracker

Widget per Windows 10/11 a 64 bit che visualizza obiettivi e attività sul desktop con un calendario a griglia. Include un centro di controllo, preset grafici e un'icona nell'area di notifica.

## Installazione

Scarica `DesktropGoalTracker-Setup-0.1.1.exe` dalla pagina delle release e avvialo. L'installazione è per l'utente corrente e non richiede Python. L'installer non è firmato digitalmente: Windows potrebbe mostrare un avviso. L'avvio con Windows è opzionale.

Al primo avvio, se presente, viene proposta la migrazione dei dati della vecchia versione. I dati personali sono conservati in `%LOCALAPPDATA%\DesktropGoalTracker\Data` e non vengono rimossi dalla disinstallazione.

## Uso

Dall'icona nell'area di notifica si aprono le impostazioni, si mostra o nasconde il widget e si gestisce l'avvio automatico. Le modifiche grafiche diventano effettive con **Applica al desktop**. È possibile regolare monitor, posizione, scala e inclinazione, selezionare due punti per l'angolo, usare un editor con il mouse per spostare, ridimensionare, inclinare e centrare, gestire preset, scegliere il tema chiaro o scuro e attivare le ombre e disabilitare il timer manuale.

La griglia GitHub legge i contributi pubblici. Le integrazioni Google Calendar, Outlook, Todoist, Notion e Strava sono sperimentali e non sono state verificate con account reali. Per Google consulta [la guida](sysadmin-codex/widget/GOOGLE-CALENDAR.md). I cronometri misurano gli intervalli tra avvio e arresto e non riconoscono automaticamente pause o inattività. Selezione e trascinamento su monitor con DPI differenti richiedono ulteriori verifiche.

## Sviluppo

Su Windows installare Python 3.12, le dipendenze in `sysadmin-codex/widget/requirements.txt`, PyInstaller 6 e Inno Setup 7. Eseguire `installer/build.ps1` da PowerShell; per il compilatore Inno il programma cerca prima `build-tools/inno/portable/ISCC.exe`, quindi `ISCC.exe` nel PATH. I dati, le credenziali e le cache locali non fanno parte del repository.

Test: `python -m unittest discover -s sysadmin-codex/widget -p 'test_*.py'`.


## Supporta il progetto

Se desideri sostenere lo sviluppo: [☕ Buy Me a Coffee](https://buymeacoffee.com/keyain).

# Collegare Google Calendar

Il widget usa l'API Google Calendar in sola lettura e richiede il permesso `calendar.events.readonly`. Non modifica eventi e nella cache conserva solo il numero di eventi per giorno. Gli eventi futuri compaiono come eventi programmati, non come attività completate.

Per il primo collegamento è necessario un client OAuth **desktop** di Google Cloud. È una configurazione del proprio account, non un token da inviare a Codex:

1. Nel proprio progetto nella [Google Cloud Console](https://console.cloud.google.com/), abilitare Google Calendar API.
2. Configurare la schermata di consenso OAuth. Se l'app è esterna e in modalità test, aggiungere il proprio account come utente di test secondo le istruzioni di Google.
3. Creare una credenziale OAuth di tipo **applicazione desktop** e scaricare il JSON del client. Conservarlo privatamente e non caricarlo in chat o nel repository.
4. Aprire `Configura widget.cmd` → Integrazioni → Configura altro servizio → Google Calendar → **Accedi con Google**. Selezionare il JSON del client; autorizzare personalmente l'accesso in sola lettura nel browser.
5. Tornare al launcher, lasciare vuoto l'ID per il calendario principale oppure indicare l'ID del calendario scelto, quindi premere **Salva e sincronizza**. Scegliere poi Google Calendar come griglia annuale e salvare.

Il browser reindirizza temporaneamente a `127.0.0.1` sul PC per completare la procedura. Il refresh token e il client sono protetti tramite DPAPI per l'utente Windows corrente. Il token può essere revocato e potrebbe scadere; i progetti esterni in stato di test possono richiedere una nuova autorizzazione dopo sette giorni. Per revocare completamente l'accesso, rimuovere anche l'app dalle autorizzazioni dell'account Google.

Riferimenti ufficiali: [OAuth per app desktop](https://developers.google.com/identity/protocols/oauth2/native-app) · [Ambiti Calendar](https://developers.google.com/workspace/calendar/api/auth).

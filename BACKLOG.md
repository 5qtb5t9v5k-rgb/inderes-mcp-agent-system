# Backlog

Yhden tiedoston kokonaisnäkymä. Päivitetty 2026-05-08.

## Status-merkit

- ✅ **toteutettu** — koodi on merkityksellisesti toiminnassa
- 🚧 **käynnissä** — branchilla mutta ei vielä main:issa / ei testattu
- ⏸ **pysäytetty** — aloitettu mutta blokattu (syy mainittu)
- 💭 **idea** — pohdinnan kohde, ei vielä sitouduttu

## Hakuopas

- [§1 AI / agentti -kyvykkyydet](#1-ai--agentti--kyvykkyydet)
- [§2 Valuation feature (oma malli)](#2-valuation-feature-oma-malli)
- [§3 UI / UX](#3-ui--ux)
- [§4 Tekninen velka + observability](#4-tekninen-velka--observability)
- [§5 Tuote / strategia](#5-tuote--strategia)
- [§6 Evals — porttikäytävä AI-featureille](#6-evals--porttik%C3%A4yt%C3%A4v%C3%A4-ai-featureille)
- [§7 Hiljattain valmistunutta](#7-hiljattain-valmistunutta)

---

## 1. AI / agentti -kyvykkyydet

Kiinnostavin näkökulma: *"miksi siirtyä reaktiivisesta proaktiiviseen"*.
Suurin oppimisarvo: *"miten agentit oikeasti tekevät yhteistyötä"*.

### Toteutetut

- ✅ **Subagenttien thought traces** — `**Ajatus:**`-pakotettu rivi jokaisen
  subagentin alkuun. PR #18, #20, #21
- ✅ **LEADin Päättely-blokki** (BACKLOG #9 prompt-only-versio) — 4 kappaleen
  proosa: erimielisyys / ratkaisu / epävarma / jätin tekemättä. UI:ssa
  oma <details>-expanderi
- ✅ **Conflict detector** (BACKLOG #1 post-execute -puoli, commit `842fd92`) —
  erillinen LLM-kutsu subagenttien ja LEAD-synteesin välissä. Emittoi
  `conflicts.json` (agreements / conflicts / isolated_claims). LEAD näkee
  rakenteellisen ristiriitakartan ja ratkaisee konfliktit eksplisiittisesti.
  Kattaa myös BACKLOG #6 Disagreement surfacing -idean
- ✅ **Provenance threading** (BACKLOG #10) — tool-call-jälki syötetään LEADille
  *"TOOL CALL TRACE (ground truth)"* -blokkina. LEAD voi diffata
  subagenttien claimeja raakadataan. `synthesis.py:80–106`

### Auki — pieniä ja itsenäisiä

- 💭 **Devil's advocate -toggle** — chat-syötteen vieressä rasti
  *"🎭 Devil's advocate"*. Yksi ekstra-LLM-kutsu joka kritisoi LEADin
  oman vastauksen: *"mitä jätit huomiotta? mihin bear-puolen
  kommentaattori tarttuisi?"* Maksimi 4 lausetta. UI: uusi
  **🎭 Vasta-argumentti** -laatikko Yhteenvedon alle. **~2 h.** Korkea
  palautusmenoarvo.

- 💭 **Footnote markers `[1]`, `[2]`** — LEADin vastauksessa kvantitatiiviset
  claimit numeroidaan, hover/klikkaus näyttää: subagentti, tool-kutsu,
  varmuusaste. CSS jo valmiina (`.ia-fn`, `.ia-fn-q/r/s/p`); tarvitsee
  prompt-päivityksen + parserin. **~5 h.** Aktivoi olemassa olevan
  kuolleen CSS:n.

- 💭 **Confidence scoring** — jokainen subagentti raportoi 1–5 confidence
  per claim. Voisi yhdistää footnote-markereihin.

- 💭 **Tool-result entity validation post-processor** *(koodi-taso)* —
  ekstraktoi yhtiönimet tool-tuloksesta + vastauksen mainitsemat yhtiöt,
  diffaa: jos vastauksessa nimi jota ei tool-tuloksessa → flag → retry.
  Ratkaisi Case 001 -hallusinaation. Ks. `evals/known-cases.md`

- 💭 **Result-completeness check** — jos tool palauttaa N itemiä ja agent
  listaa M < N, pakota selitys. Ratkaisi Case 002:n.

- 💭 **Default-region inference** — suomenkielinen kysely → defaulttaa
  `regions=[FINLAND]` ellei toisin sanottu

### Auki — keskisuuria

- 💭 **#2 Reflektio + retry kun output on outoa** — havaitse anomaaliset
  outputit (CAGR > 100%, tyhjä, "ei dataa") → retry samalla agentilla
  lisätyllä kontekstilla *"edellinen vastauksesi sisälsi: [output].
  Tarkista onko järkevä."* Cap retry 1:een per agentti.
  *Riski:* retry voi maskata oikeasti puuttuvan datan oletuksilla — pitää
  erottaa "ei dataa" vs "outo data".

- 💭 **#5 Insight ledger — pitkäkestoinen muisti** — jokaisesta kyselystä
  LEAD destilloi 1–3 muistettavaa havaintoa, tallennetaan
  `~/.inderes_agent/insights.jsonl`. Seuraavalla kyselyllä relevantit
  ladataan kontekstiin → kasvava yritystuntemus sessioiden välillä
  *Avoimet:* insightin vanhentumislogiikka, kuinka monta kontekstiin
  (token-rajat), käyttäjähallinta UI:ssa

- 💭 **#9 Better LEAD model — Sonnet/Opus syntheesivaiheeseen** — Flash
  Liten tilalle. Vaatii ensin parked Pro-toggle-haaran korjaamisen.
  Hyödyllisin **kun #10 (provenance) on paikallaan** — ilman raakadataa
  Sonnet ei voi diffata claimeja paremmin. Kustannus ~40–200x per kysely.

### Auki — isoja arkkitehtuurillisia

- 💭 **#1 pre-execute plan + "Käytä vahvempaa suunnittelua" -toggle** —
  LEAD kirjoittaa strukturoidun **🧠 Suunnitelma** -blokin ennen
  subagenttien dispatchia. Toggle-pohjainen kuten valuation, *ei
  default*. Pohdintamuistio sparrauksesta 2026-05-08:
  - **Manager bias** (Cognition 22.4.2026): *"managers default to overly
    prescriptive, which backfires when manager lacks deep context"* —
    LEADilla ei ole tool-pintaa, joten yli-ohjaus on todellinen riski
  - **Opportunistinen löytäminen häviää** — staattisessa fan-outissa
    subagentti voi sattumalta törmätä yllättävään yksityiskohtaan;
    plan-pakotettuna ei "saa luvalla" eksyä sivuun
  - **Latenssi + token-kustannus** — yksi ylimääräinen LLM-kutsu, plus
    pidemmät promptit. Yksinkertaisissa kyselyissä hukkaa
  - **Plan ↔ result -mismatch** — jos suunnitelma sanoo "hae X" mutta
    MCP palauttaa tyhjää, kuka päättää uudelleenkirjoittamisesta?
  - **Oikea käyttötapa**: monivaiheiset riippuvuudet, vertailut joissa
    vertailuakseli ei ilmiselvä, tutkimukselliset kysymykset
  - **Default off, opt-in** käyttäjältä

- 💭 **#7 Subagent-to-subagent kutsu** — QUANT voi suoraan kutsua
  SENTIMENTtia. Klassinen multi-agent-haaste.
  *Avoimet:* infinite loop -esto, per-kutsu kustannuskatto, privacy/context
  isolation, tracing. Voi vaatia "team lead" -agentin koordinaattoriksi.

- 💭 **#8 Bull/Bear -debate-arkkitehtuuri** — sijoituspäätös-tyyppisille
  kyselyille spawnaa kaksi vastakkaista LEADia (bull + bear) + judge.
  Uudet promptit `bull.md`, `bear.md` (sama tool-setti kuin RESEARCH).
  *Riski:* Wynn et al. (arXiv 2509.05396) osoittivat että debate voi
  *huonontaa* tarkkuutta jos heikompi malli "vakuuttaa" vahvemman
  (CommonSenseQA: 53.4% → 46.8% debaten jälkeen). Mitigation: judge näkee
  aina molemmat *ja* alkuperäisen tool-tracen.

- 💭 **#4 Watchlist + päivittäinen briefing** — käyttäjä merkkaa
  "seuraa Sampoa", GitHub Action ajaa joka aamu, generoi *"mitä uutta?"*
  -markdownin. Sidebariin **📅 Aamun briefing** -osio. **Iso siirtymä
  reaktiivisesta proaktiiviseen.** Vaatii: scheduled job, watchlist-store,
  brief-generaattori, UI-osio.

### Pysäytetyt

- ⏸ **LEAD Pro-malli togglellä** (`feat/lead-pro-toggle` -branch) —
  blokattu MAF/Gemini-yhteensopivuusongelmaan: Pro hylkää
  *"Function calling config is set without function_declarations"*
  vaikka LEAD:llä ei ole työkaluja. Vaatii MAF:n internal
  config-rakentamisen tutkimista. Ratkaisu blokkaa myös #9:n.

---

## 2. Valuation feature (oma malli)

**Tila:** kehitys käynnissä paikallisella branchilla `feat/valuation-engine`,
ei pushattu. 6 commitia, 89/89 testiä vihreänä.

### Toteutettu paikallisesti (ei vielä pushattu)

- 🚧 **`valuation/engine.py`** — deterministinen Greenwald-Gordon -hybridi
  (commit `e04cceb`). 8-kohtainen filosofia koodina:
  FV_Gordon = ((ROE-g)/(k-g)) × BVPS, EPV = (ROE/k) × BVPS, GM, Rock Bottom,
  laatu/keskinkertainen/tuhoutuva-luokitus
- 🚧 **Excel-parity** — 10 suomalaisen yhtiön regressio sun
  `Arvonmääritys2023.xlsx`-aineistoa vasten. Kaikki numerot ±0.02 €
  toleranssilla
- 🚧 **`aino-valuation`-agentti + parser** (commit `78cd1a6`) — strukturoitu
  JSON-output, parser validoi ennen engineä
- 🚧 **Pipeline integration + sidebar-toggle** (commit `79cccdc`) —
  *"Käytä vaihtoehtoista arvonmääritystä"* -rasti
- 🚧 **Kestävä-taso ROE-sääntö + parser-validointi** (commit `4437b0f`) —
  median dominoi keskiarvon, deterministisesti validoitu Pythonissa.
  Nouseva → 5y_median, laskeva → min(3y_median, trend_weighted),
  vakaa → 5y_median
- 🚧 **EPV / kasvun hinnoittelu -dekompositio** (commit `4375797`) —
  market_premium_to_epv_pct, growth_priced_in_share, implied_g,
  safety_margin_to_fv_pct
- 🚧 **Laajempi rationale + LEAD-narratiivi** (commit `899f828`) —
  agent-prompt vaatii roe_rationale + 2-4 lausetta per parametri.
  LEAD-prompt 4-osainen "Oma malli vs Inderes" -sektio. BVPS-johto
  vaihdettu marketCap/sharesTotal/pb:hen

### Auki — välittömästi käytettäviä

- 💭 **Live-testaus useammalla yhtiöllä** — Sampo + Qt + Aktia + Citycon
  + Konecranes. Validointi että agentti tuottaa tarpeeksi pitkää
  rationale:a ilman truncationia. Tämä on porttikäytävä push:lle
- 💭 **Salkkumoodi** — sama valuation-engine sovellettuna salkun
  yhtiöille. Cron joka aamu, *"mitä on muuttunut viimeisen kk
  aikana"*. Vaatii: scheduled job, salkkutason synteesi-prompt,
  oma UI-näkymä erotuksena chat-vastaukselle

### Auki — laajennukset jotka vahvistavat mallia

- 💭 **Skenaariotaulukot UI:ssa** — Heikko/Perus/Hyvä (ROE × 0.9 / 1.0 / 1.1)
  per yhtiö, sun Excel-Yhtiökohtainen-sheetiltä. Engine osaa laskea jo,
  UI-renderöinti puuttuu
- 💭 **Herkkyystaulukot 6×6** — ROE × k ja g × k, sun
  `methodology/sensitivity.md` mukaisesti. Engine + UI
- 💭 **Visual valuation card** — spider-chart tai dial gauges, ei pelkkä
  teksti. Erityisesti kasvu/EPV-jako ansaitsisi visuaalin
- 💭 **Composite score "Rissasen Score"** — *suunnittelussa,
  ei sitouduttu*. Sparrauksen huomiot 2026-05-08:
  - **Älä laske yhdeksi kompositiopisteeksi** — additiivinen kompositio
    cancelloi signaalia (Q9+V3 ja Q3+V9 saavat saman pisteen mutta ovat
    eri sijoituspäätöksiä). Greenblattin Magic Formula käyttää
    rank-leikkausta, ei painotettua summaa
  - **Korreloituneet dimensiot kaksoiskirjaavat** — ROE/ROIC/FCF-konversio
    ovat 80%+ korreloituja, ei kolme itsenäistä mittaa
  - **Inderes-konsensus 10% on sirkulaarinen** — arkkitehtuuri jo nojaa
    Inderesiin; lisäpaino on double-dipping
  - **Suosittu tilalle:** näytä 6 dimensiota erikseen (spider-chart),
    "convergence flag" jos eroavat, ja sektori-relatiivinen pisteytys
    absoluuttisten arvojen sijaan
  - **Implementaatiopuutteet MCP:ssä:** ROIC, WACC, FCF, earnings
    revisions ja short interest puuttuvat. Mitkä mittarit on
    realistisia toteuttaa Inderesin datalla?
  - **Validointi**: ennen toteutusta backtestaa sun 74 yhtiön
    Excel-aineistoa vasten. Ennustava vai kuvaileva tarkoitus?

### Pohjalla oleva ongelma

- 💭 **MCP ei tue suoraa BVPS-kenttää** — johdetaan
  `marketCap / sharesTotal / pb`:stä. Dokumentoitu. Pidemmän aikavälin
  parannus: pyydä Inderestä lisäämään `bookValuePerShare` `fields`-enumiin.

---

## 3. UI / UX

### Toteutettu

- ✅ **Token-järjestelmän yhtenäistys** (commit `30174e5`) —
  --t-* / --ls-* / --r* / --s-* tokenit. Legacy --ia-* -aliakset poistettu
- ✅ **Aikajana-strippi + Avaa loki + Avaa päättely** (commit `070e512`) —
  yhtenäinen rytmi terminal-DNA-tyyliin
- ✅ **Right activity panel + close button** (commit `6acb316`)
- ✅ **Conflict box embedded in Päättely** — "Subagentit erimieltä"
  Päättely-expanderin sisällä
- ✅ **Followup chips** — keltaiset, suuremmat, ei tekstinylivuotoa
- ✅ **Inderes recommendation badge** — INCREASE/REDUCE/HOLD värikoodattuna
- ✅ **Lähteet klikattavina linkkeinä** — Inderes.fi-URL:t LEAD-vastauksessa
- ✅ **Persona-värinen live-status -box** — agentit näkyvät reaaliajassa
- ✅ **Live-narration finetuning** — *"Tunnistan, mitkä agentit
  tähän tarvitaan…"* tyyppiset rivit (commit `58bd36f`)

### Auki — pikkupolish

- 💭 **Tier 6: Responsive** — oikean paneelin breakpointit kapeille
  näytöille. `(max-width: 1280px)` → overlay-muoto, `(max-width: 720px)` →
  full-screen modal. Mobiili-fallback (1024px) on jo olemassa mutta ei
  testattu kunnolla. **~20 min**
- 💭 **`.streamlit/config.toml` `primaryColor`-override** — voisi pudottaa
  monta `!important`-overridea. *Riski:* jokainen Streamlit-painike saa
  värin → secondary-painikkeet voi rikkoutua. **~30 min testaus**
- 💭 **Animaatiopolish** — 150ms hover-transitionit kaikkiin chrome-elementteihin
  (button, paattely, timeline, chat-message). Pehmentää tunnelmaa. **~15 min**
- 💭 **CustomStatus-token-pass** — `.ia-cs`-säännöt käyttävät vielä raakoja
  arvoja (`padding: 8px 12px`). Snäppää --s-* / --t-*:ään. **~10 min**
- 💭 **Statusbar (`.ia-statusbar`)** — onko enää tarpeen kun Aikajana-strippi
  näyttää saman? Slim:taa, poista, vai pidä?

### Auki — keskisuuria

- 💭 **Bottom 🔍 Agenttien toimintaloki -expander** — duplikoi oikean
  paneelin sisällön. Käyttäjä päätti *"saa vielä jäädä"* mutta jos
  käytösperusteisesti se on tarpeeton, poistaminen toisi ~80 riviä
  koodia pois
- 💭 **Custom chat-message rendering** — lopeta `st.chat_message`in
  käyttö, renderöi omat viestilaatikot. Vaatii suuremman muutoksen
  mutta lopettaisi taistelun Streamlitin oletuksia vastaan.
- 💭 **Plotly-chartit QUANTille** — interaktiiviset time-series, peer-vertailu.
  `st.plotly_chart` natiivi. Suositeltu prioriteettivertailussa.

### Auki — laajempaa

- 💭 **Streaming output** — token-by-token vastauksen renderöinti
  chat-bubblessa. Streamlit tukee tämän, mutta MCP-kutsujen siirtäminen
  vaatii osa-tilojen hallintaa
- 💭 **PDF-vienti** — *"Vie tämä kysely PDF:ksi"* → matplotlib-charts +
  taulukot + analyysi

---

## 4. Tekninen velka + observability

### Toteutettu

- ✅ **Forensic logging per run** — `~/.inderes_agent/runs/<ts>/`-rakenne.
  Replay-friendly per BCBS 239 lineage-vaatimukset
- ✅ **HeadlessAuthError + `_auth_broken`-latch** — selkeä virheviesti kun
  Inderes-tokeni vanhentunut, ei silently-failure (commit `3f933f6`)
- ✅ **CancelledError fix** (commit `d5d9dfe`) — MCP-yhteyden katkos ei
  enää jätä UI:ta jumiin, näyttää saman "yhteys vanhentunut" -kortin
- ✅ **Token-rotation cron** — GitHub Actions joka 15 min. PR #25
- ✅ **Gist-mirror OAuth-tokeneille** — Streamlit Cloudin
  filesystem-readonly -rajoituksen kierto

### Auki — korkea prioriteetti (porttikäytävä AI-featureille, ks. §6)

- 💭 **👍 / 👎 -palaute UI:hin** — `feedback.json` per run, ei pakota
  kommenttia. Yhden illan työ. *Tämä on portti kaikkeen muuhun.*
- 💭 **Smoke test** — 5–10 known-good queryä pytestissä. Routing oikea,
  vähintään yksi tool-call, vastaus ei tyhjä, key entities löytyvät.
  Yhden illan työ.
- 💭 **`evals/golden.yaml` + `scripts/replay.py`** — kuratoidut run_id:t
  referensseinä, replay diffaa rakennetta (router, tool-calls, key
  entities) raw-tekstin sijaan. `evals/known-cases.md` on jo olemassa —
  Case 001 + Case 002 valmiit golden-rivit

### Auki — keskitaso

- 💭 **CircuitBreaker `FallbackGeminiChatClient`:lle** — 503/429-
  käsittelyyn. Tilakoneisto (CLOSED/OPEN/HALF_OPEN), eksponentiaalinen
  backoff + jitter, 429 vs 5xx eri cooldownit, per-model cooldown.
  ~50 lisäriviä koodia, saavuttaa LiteLLM-tasoisen resilienssin ilman
  kirjastoriippuvuutta. **~1–2 päivää**
- 💭 **OpenTelemetry GenAI Semantic Conventions v1.37** — `gen_ai.agent.name`,
  `gen_ai.operation.name`, `gen_ai.usage.*input_tokens` jne. forensic-
  lokitukseen. Mahdollistaa myöhemmän siirtymän OTel-yhteensopivaan
  observability-stackiin (Langfuse self-host, Phoenix). **~4 h**
- 💭 **`.streamlit/config.toml` `primaryColor` -override** — ks. §3, sama
  asia teknisestä näkökulmasta

### Auki — pidempi tähtäin

- 💭 **MCP capability documentation auto-generated** — build-time-skripti
  joka lukee tool-schemat ja tislaa `docs/mcp-capabilities.md`:n.
  LEAD-prompt sisällyttää sen → tietää mitä MCP tarjoaa. Mahdollistaa
  *"olisi voitu hakea X muttei haettu"* -tyyppistä päättelyä. **~2 h.**
  *(Pohdittiin sparrauksessa 2026-05-08 — käyttäjä halusi vielä odottaa)*
- 💭 **Issue register + stress-test scenarios** (BCBS 239 -compliance) —
  laajennus `evals/known-cases.md`:lle persistentiksi rekisteriksi.
  **~2 päivää**
- 💭 **Web-haku RESEARCHille** — Reuters/Bloomberg-otsikot Inderesin oman
  korpuksen rinnalle. **~1 päivä.** *Riski:* tietolähteen
  hygienia
- 💭 **Inline source citations per claim** — *(suora osuma vs observed
  hallusinaatiot, ks. evals/known-cases.md Case 001)*. Footnote-markers
  (§1) on ensimmäinen askel tähän
- 💭 **Historiallinen backtest** — *"Mitä olisit suositellut 3kk sitten
  Sammosta?"* — agentti rajaa kontekstinsa siihen päivämäärään ja
  katsoo nyt miten ennuste osui. Vaatii tool-puolen date-filteröintiä.

### Tunnetut ongelmat — pysyvät

- ℹ️ **Inderes Keycloak 10h SSO Session Max** — refresh tokenit
  invalidoituvat 10h kuluttua. Workaround: `bash scripts/relogin.sh`
  tai cron jos saatavilla. Empiirisesti dokumentoitu (cron-job.org
  testit: 120 onnistunutta rotationia, 121. epäonnistui 601 min
  kohdalla).
- ℹ️ **Streamlit Cloud deploy lag** — joskus auto-deploy on hidas;
  empty-commit force-redeploy tarvittu

---

## 5. Tuote / strategia

### Avoimet kysymykset

- 💭 **Yleisö** — pelkästään minä itse, vai kasvava käyttäjäkanta?
  Itselleni voin sietää korkean kompleksisuuden; yleisölle tuote
  pitää olla yksinkertaisempi tarina
- 💭 **Reaktiivinen vai proaktiivinen** — chat (nyt) vs watchlist + aamun
  briefingit. Mind shift, tuotteen identiteetti muuttuu
- 💭 **MiFID II — kuinka lähellä "personal recommendation" -rajaa
  uskalletaan käydä?** Stock research ei lähtökohtaisesti ole high-risk
  Annex III, mutta yksittäinen *"sinulle sopii X"* triggeröi koko
  investment-advice-velvoitepaketin (ESMA Test 4 — suitability)

### Mahdolliset julkaisut

- 💭 **Blog-postaus arkkitehtuurivalinnoista + Keycloak 10h -löytö** —
  täsmällinen empiirinen mittaus, replikaatio-instruktiot. Open-source-
  yhteisölle ja pohjoismaisille pankki-AI-tiimeille. Käyttäjien aikasäästö
  merkittävä. **~1 päivä**
- 💭 **PR Keycloak-dokumentaatioon** SSO Session Max -default-arvosta ja
  sen operationaalisista vaikutuksista refresh-tokeneille
- 💭 **MCP-Inderes-integraation README-update** — varoitus 10h-
  käyttäytymisestä, workaround offline_access-scopen kautta jos
  Inderes sallii

### Dokumentaatio

- 💭 **README — päivitys nykyiseen arkkitehtuuriin** (post-UI-refactor +
  valuation)
- 💭 **DESIGN_BRIEF.md drift check** — vanhempi suunnitelma joka voi olla
  päivittämättä
- 💭 **`/methodology` -kansion synkka enginen kanssa** — koodi muuttuu,
  metodologia-mds eivät
- 💭 **MULTI_AGENT_ARCHITECTURE.md korjaukset** sparrauksen 2026-05-07
  pohjalta:
  - CoALA-viite memory-jakoon (procedural-tier puuttuu kanonisesta)
  - Vahvempaa muotoilua *"yhteensopiva Cognitionin 22.4.2026 kanssa,
    lähimpänä OpenAI Cookbookin agents-as-a-tool 28.5.2025 -patternia"*
  - "anti-capabilities" → "least-agency rules" (OWASP Agentic Top 10)
  - MiFID II Test 4 -kytkentä eksplisiittiseksi
  - Pitfall-listan täydennys OWASP:in turvallisuusnäkökulmasta

### Strategiset isot

- 💭 **Plotly-chartit QUANTille** (käyttöliittymäfeature mutta strateginen
  vaikutus) — erottuu visuaalisesti, "Inderes Norasta" -tasolla parempi
- 💭 **Salkkumoodi proaktiivisuuden alkuna** — ks. §2

---

## 6. Evals — porttikäytävä AI-featureille

> **Kunnes evals-pohja on rakennettu, AI-kyvykkyysfeaturet eivät kannata
> investoida — emme tiedä toimivatko korjaukset.**

### Nelitasoinen polku

1. **👍 / 👎 -palaute UI:ssa** *(yksi ilta)* — `feedback.json` per run,
   ei pakota kommenttia. Kerää oikeaa-käyttöä-koskevaa palautetta.
2. **Smoke test** *(yksi ilta)* — pytest-fixture jossa 5–10 known-good
   queryä. Routing oikea, vähintään yksi oikea tool-call, vastaus ei
   tyhjä, tunnetut avainsanat löytyvät.
3. **`evals/golden.yaml` + `scripts/replay.py`** *(yksi ilta)* —
   kuratoidut run_id:t referensseinä, replay diffaa rakennetta
   (router, tool-calls, key entities) raw-tekstiä unohtaen.
4. **Production monitoring** *(jatkuva)* — aggregointiskripti joka
   näyttää viikon thumbs-up/down -suhteen, kategorisoi virhetyypit.

`evals/known-cases.md` on jo aloitettu — jokainen sieltä löytyvä tapaus
on potentiaalinen golden-rivi. Case 001 + Case 002 ovat selkeät
ensimmäiset.

### Strategiset evaluaatiot

- 💭 **Trajectory-eval** — Phoenix tai LangSmith. Tasolle 4 etenemiseen
- 💭 **Calibration** — post-hoc kalibrointi-kertoimet outputin varmuudelle
- 💭 **Red-teaming** — Microsoft AI Red Team -taksonomia tarkistuslistaksi
- 💭 **Drift detection** — Langfuse/Phoenix metriikat per viikko vs baseline.
  Hyödyllinen vasta kun production-traffic > 100 kyselyä/päivä

---

## 7. Hiljattain valmistunutta

(Niin että näkee mistä tasosta lähdettiin → mihin päästiin)

### 2026-05-08
- ✅ Valuation-feature paikallisella branchilla (engine, agentti,
  parser, UI, kestävä-taso ROE-sääntö, EPV-dekompositio,
  laajemmat rationale-kentät) — ks. §2

### 2026-05-07
- ✅ UI token-järjestelmän yhtenäistys + slim Päättely + amber chips
- ✅ Aktiviteettipaneeli + close button + päättelyyn upotettu konflikti
- ✅ CancelledError-virheen kunnollinen surfacointi
- ✅ Live-narrationin viimeistely

### Aikaisemmin
- ✅ #1 post-execute (conflict detector, `842fd92`)
- ✅ #3 thought traces (PR #18, #20, #21)
- ✅ #6 disagreement surfacing (osana #1)
- ✅ #9 prompt-only Päättely-blokki
- ✅ #10 provenance threading (`synthesis.py:80–106`)
- ✅ Inderes-suositus-badge (PR #28)
- ✅ Followup-chipit (PR #28)
- ✅ Klikattavat lähdelinkit (PR #29)
- ✅ Persona-värinen live-status (PR #23)
- ✅ Token-rotation cron (PR #25)

---

## Lukuvinkit

- **Ennen kuin lisäät uutta** §1:een — varmista että §6 (evals) on
  ajan tasalla. Ilman mittaria emme tiedä paranevatko featuremuutokset
  tilannetta.
- **Pohjarakenne pysyy:** jokaisella luvulla on "Toteutettu / Auki /
  Pysäytetty" -jako. Jos joku status muuttuu, päivitä se merkki.
- **Kun pohdit "tehdäänkö tämä?"** — etsi onko se §6:ssa
  porttikäytävää tarvitseva. Jos on, evals-foundation tehdään ensin.

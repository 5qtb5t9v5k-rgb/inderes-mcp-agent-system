# Feature backlog

Ideoita joita ei ole vielä toteutettu. Järjestys ~prioriteetin mukaan, ei kova pakko.

Kiinnostavin = "miksi siirtyä reaktiivisesta proaktiiviseen". Suurin oppimisarvo = "miten agentit oikeasti tekevät yhteistyötä".

**Toteutetut alunperin samasta listasta:**
- ✅ #3 Thought traces (Ajatus-rivit subagenteilla, 💭 Perustelut LEADilla) — PR #18, #20, #21
- ✅ Inderes-suositus-badge LEAD-vastauksen yläpuolella — PR #28
- ✅ Followup-chip:t synteesin alle (3 klikattavaa jatkokyselyä) — PR #28
- ✅ Lähteet klikattavina linkkeinä Inderes.fi:hin — PR #29
- ✅ Persona-värinen live-status box — PR #23
- ✅ GitHub Actions -cron joka 15 min token-rotaatioon — PR #25
- ✅ **#1 plan-then-execute (post-execute variant): pre-synthesis conflict detection** —
  commit 842fd92. Erillinen LLM-kutsu subagenttien ja LEAD-synteesin välissä;
  emittoi `conflicts.json` (agreements / conflicts / isolated_claims). LEAD näkee
  rakenteellisen ristiriitakartan ja ratkaisee konfliktit eksplisiittisesti
  perusteluissa. Toteutti samalla osan #6 *Disagreement surfacing*:sta. Kattaa
  Case 003:n "make emergent filtering explicit" -fix-kandidaatin.
- ⏸ **Parked**: LEAD Pro-malli togglellä — `feat/lead-pro-toggle` branchilla. Blokattu MAF/Gemini-yhteensopivuusongelmaan: Pro hylkää `Function calling config is set without function_declarations` vaikka LEAD:llä ei ole työkaluja. Vaatii MAF:n internal config-rakentamisen tutkimista.

---

## #1 Plan-then-execute LEADilla  *(keskisuuri — osittain toteutettu)*

> ✅ **Post-execute -puoli toteutettu** commitissa 842fd92 (pre-synthesis
> conflict detection — ks. ylempi Toteutetut-lista). Alla kuvattu
> *pre-execute* -suunnitteluvaihe (LEAD kirjoittaa strukturoidun
> suunnitelman ennen subagenttien dispatchia) on yhä kiinnostava ja tekemättä.


LEAD ei tällä hetkellä todellisuudessa "ajattele" suunnittelu-tasolla — se vain reitittää
classify_query:n kautta ja synteseuraa. Lisää välivaihe ennen subagenttien dispatchia:

1. Router luo karkean classification (nyk.)
2. **UUSI** — LEAD kirjoittaa **strukturoidun suunnitelman**:
   - Per subagentti: tarkennettu kysymys / fokus
   - Mahdollisesti agenteittain pudotuksia ("skip sentiment, kysely on puhtaasti numerollinen")
   - Mahdollisesti lisäyksiä ("kysymys vaatii myös portfolio-näkökulman vaikka router ei nostanut")
3. Subagentit ajetaan plan-tasolla räätälöidyillä prompteilla
4. Synteesi (nyk.)

UI näyttää suunnitelman omana blokkinaan **🧠 Suunnitelma** ennen subagenttien
toimintaa — käyttäjä näkee ennen kuin mitään ajetaan, mitä LEAD aikoo tehdä.

**Riippuvuus:** rakennettu PR #21:n LEADin "💭 Perustelut" -callouten päälle, ehkä jo
asettelu valmiina.

**Riski:** ylimääräinen LLM-kutsu hidastaa — kannattaa tehdä rinnakkain reitityksen
kanssa tai käyttää nopeaa Flash-mallia.

---

## #2 Reflektio + retry kun output on outoa  *(keskisuuri)*

Subagentit antavat joskus järjenvastaisia vastauksia (negatiivinen CAGR positiivisilla
arvoilla, tyhjät vastaukset, vain "data ei saatavilla", anomalous numbers). Lisää
post-processing -kerros joka:

1. Tarkistaa output:n red flag -kriteereillä:
   - Tyhjä / "_(empty response)_"
   - "ei saatavilla", "couldn't compute", "N/A" -tyyppisiä fraaseja
   - Numeerinen poikkeavuus (esim. CAGR > 100% tai < -50%)
   - Vain Ajatus-rivi, ei vastaussisältöä
2. Jos red flag -> **retry samalla agentilla** mutta lisätyllä kontekstilla:
   *"Edellinen vastauksesi sisälsi: [output]. Tarkista onko järkevä, jos ei niin
   vastaa toisin. Jos on, perustele miksi tämä numero / fraasi pitää paikkansa."*
3. Cap retry määrä 1:een per agentti (kustannukset, pingvinin loop)
4. UI näyttää retry-tilan: "▲ QUANT — REFLEKTOITU (alkuperäinen vaikutti
   epätavalliselta)"

**Riippuvuus:** toimii itsenäisesti, mutta arvokkaampi kun yhdistetty plan-then-execute:n
kanssa (LEAD näkee retry:n ja voi adapt synteesin).

**Riski:** retry voi maskata oikeasti puuttuvan datan oletuksilla — pitää erottaa
"ei dataa" (rehellinen) vs "outo data" (tarkista).

---

## #4 Watchlist + päivittäinen briefing  *(iso, eri päätelaite)*

Käyttäjä voi sanoa "seuraa Sampoa". Tallennetaan watchlist `~/.inderes_agent/watchlist.json`.

GitHub Action ajaa joka aamu:
- Hakee jokaiselle watchlistatulle yhtiölle "mitä uutta?"
- Käy läpi: uudet analyytikkonotet, insider-kaupat, tulosjulkistukset, foorumipiikit
- Tallentaa yhden markdown-tiedoston per päivä

Streamlitiin uusi sidebar-osio "📅 Aamun briefing" josta käyttäjä avaa päivittäisen yhteenvedon. Nappi "Päivitä nyt" forssaa heti.

**Miksi iso:** Siirtää koko tuotteen reaktiivisesta proaktiiviseen. Mind shift. Vaatii: scheduled job, watchlist-store, brief-generaattori, UI-osio.

**Riippuvuudet:** Toimii ilman muita featureita.

---

## #5 Pitkäkestoinen muisti — insight ledger  *(keskisuuri)*

Nyt `ConversationState` muistaa vain `last_companies` ja `last_summary`. Häviää sessiolopussa.

Lisää **insight ledger**: jokaisesta kyselystä LEAD destilloi 1-3 muistettavaa havaintoa
(esim. *"Sammon Q3 odotettua heikompi", "UPM:n insider-myynnit lisääntyneet"*).
Tallennetaan persistenttisti `~/.inderes_agent/insights.jsonl`.

Seuraavalla kyselyllä relevantit (matchaa company tai toimiala) ladataan kontekstiin
→ agentti rakentaa **kasvavan yritystuntemuksen** sen sijaan että tabula rasa joka kerta.

Reuna-tapaukset:
- Insightin vanhentumislogiikka (vanha tieto voi olla väärin nyt)
- Kuinka monta insighttia kontekstiin? (token-rajat)
- Käyttäjä voi nähdä/poistaa/muokata insighteja UI:ssä?

**Riippuvuudet:** Hyödyllisin yhdistettynä #1 plan-then-executeen — plan voi viitata
muistettuihin insighteihin.

---

## #6 Disagreement surfacing  *(keskisuuri — pääosin toteutettu eri muodossa)*

> ✅ **Toteutettu 842fd92:ssä rakenteellisempana versiona**: erillinen
> conflict-detector-LLM-kutsu emittoi `conflicts.json` ennen synteesiä;
> LEAD näkee `agreements / conflicts / isolated_claims` -kartan ja
> ratkaisee konfliktit perusteluissa (Puuilo-ajossa eksplisiittisesti
> Joller-insider-kaupan disambiguointi). Alla oleva alkuperäinen kuvaus
> kuvaa kevyemmän prompt-only-version — säilytetty referenssiksi siitä
> *minkä haastetta yritettiin ratkoa*.


Kun QUANTin numerot ja Inderesin estimaatit ovat ristiriidassa (esim. P/E 12x vs analyytikon 18x),
älä piilota sitä — **nostaa esiin** synteesissä omana osionaan **🚨 Ristiriidat**.

Toteutus:
- LEADin synteesi-prompt sisältää eksplisiittisen ohjeen: "Jos subagenttien tiedot
  ristiriitaisia, kirjaa Ristiriidat-osio."
- Vaihtoehtoisesti: post-processing joka diff-tarkistaa numeerisia ristiriitoja
  per metric

**Miksi arvokas:** Lisää luottamusta. Käyttäjä näkee mistä ollaan epävarmoja sen
sijaan että saa konfidenssikuvan vääristä numeroista.

**Pikavoitto-versio:** Lisää LEAD-promptin ohje, ei muutoksia koodiin. ~30 min.

---

## #7 Subagent-to-subagent kutsu  *(iso, arkkitehtuurimuutos)*

Nyt arkkitehtuuri yksitasoinen: LEAD → subagent → MCP. Jos QUANT tarvitsee sentimenttitietoa,
sen pitäisi pyytää LEADia ja LEAD dispatcheaa SENTIMENTin uudella roundilla.

**Suora subagent-to-subagent**: QUANT voi kutsua SENTIMENTtia ilman LEADin välityskäyntiä.

Haasteet:
- Infinite loop -esto
- Per-kutsu kustannuskatto (max N hyppyä)
- Kuka näkee mitä? (privacy / context isolation)
- Tracing — kuka kutsui ketä, kun?

**Miksi opettavainen:** Klassinen multi-agent system challenge. Pakottaa miettimään
koordinaatiota, dependency injectionia, costsia.

**Riippuvuudet:** Pitäisi mahdollisesti tehdä koordinaattorina toimiva *team lead*-agentti
ennen tätä, jotta arkkitehtuuri on selkeä.

---

## #8 Debate-arkkitehtuuri  *(iso)*

Tietyille kysymyksille ("kannattaako Sampoon ostaa?") spin up **kaksi vastakkaista
agenttia** — *bull* ja *bear* — jotka argumentoivat saman datan pohjalta vastakkaisia
näkemyksiä. LEAD tai erillinen *judge*-agentti tasapainottaa molemmat synteesissä.

Käyttötapaukset:
- Sijoituspäätös-tyyppiset kyselyt
- "Onko tämä yhtiö liian arvostettu?"
- Arvon vs kasvun debatti
- Tase-riskien arvostus

Toteutus:
- Uudet promptit `bull.md`, `bear.md` (samalla tool-setillä kuin RESEARCH)
- Router tunnistaa decision-tyyppisen kyselyn → spawnaa bull + bear
- Synteesi näyttää molemmat argumentit ennen omaa neutraalia kokoavaa vastausta

**Miksi arvokas:** Lisää intellectual rigor. Käyttäjä näkee oikeasti molemmat puolet
ennen omaa päätöstään.

---

## #9 LEAD-syntheesin näkyvä ajattelu — visible reasoning + uncertainty calibration  *(keskisuuri)*

Nyt LEAD:n `**💭 Perustelut:**` -lohko on tyyliltään *"Yhdistin X:n ja Y:n,
painotin Z:tä koska..."* — toimiva *executive summary* mutta ei näytä
ajattelua. Vertaa Claude/OpenAI o3/Grok -mallien ajatusketjuun:

- **Visible reasoning**: *"Yksi sentiment-haara väitti ettei
  insider-kauppoja ole, kun toinen kaksi viittasivat Jollerin
  maaliskuun ostoon. Kysyin itseltäni: miksi yhden näkemys eroaa?
  Todennäköisin selitys on hakuparametri tai työkalun tilainen ongelma,
  ei se että kauppoja ei olisi tapahtunut — pörssitiedote vahvistaa
  Jollerin transaktion. Jätän siis 'ei kauppoja' -tiedon huomiotta."*
- **Itse-kritiikki ja epävarmuuskalibrointi**: *"Olen melko varma tästä,
  mutta merkille pantavaa: en tarkistanut Jollerin transaktion
  alkuperäistä Inderes-tiedotetta itse — luotan kahden subagentin
  vahvistukseen. Jos lukijalle on tärkeä exact-summa, varmistakaa
  pörssitiedotteesta."*
- **Hierarkkinen jäsennys**: separointi *varma → todennäköinen →
  epävarma* -liukumaan, jotta käyttäjä näkee mitkä claimit ovat
  load-bearing ja mitkä reunamerkintöjä.

**Riippuvuus**: Conflict-detector (toteutettu 842fd92:ssä) syöttää
LEAD:lle jo strukturoidun ristiriitakartan — pohjana tämän reasoningin
päälle. Pelkkä prompt-tarkennus voi viedä pitkälle, mutta varsinainen
laatuhyppy vaatii todennäköisesti **isomman / "ajattelevamman" mallin
LEAD-rooliin** (esim. Claude tai o3 / GPT-4o-thinking — Gemini Flash
Lite kallistuu rakenteellisesti executive-summary-tyyliin).

**Tärkeä riippuvuus #10:stä (Provenance threading)**: ilman raakaa
työkaludataa LEAD:llä ei ole tarttumapintaa Case 4a/4b -tyyppisille
hallusinaatioille (näkee vain subagentin tiivistelmän). Parempi malli
ilman provenance:ia *vähentää todennäköisyyttä* hallusinointiin mutta
ei tee siitä tunnistettavaa. **Tehdään #10 ensin**, sitten #9 voi
aidosti hyödyntää datan ja perustella Sonnet/Opus:in lisäkustannusta.

**Toteutusmuotoja**:
1. *Pelkkä prompt* — `lead.md`-uudelleenkirjoitus jotta `**💭
   Perustelut:**` sisältää eksplisiittisesti *"olin epävarma X:stä,
   ratkaisin..."* + varmuusasteet. Halpaa, voi nostaa 30%.
2. *Mallin vaihto LEAD-roolissa* — esim. Claude-Sonnet pelkkään
   syntheesivaiheeseen, subagentit jäävät Geminille. Vaatii
   `agent_framework`-mallin Anthropic-clientin (jo riippuvuuksissa
   `agent-framework-anthropic`) plumbingin.
3. *Side-by-side dual LEAD* — Gemini ja Claude tekevät rinnakkaisen
   syntheesin, käyttäjä näkee molemmat välilehtinä. Kallista mutta
   erinomainen evals-aineisto.

**Riskit**: ajatusketjun rivit voivat paisuttaa vastauksen pituutta
liiaksi. Kannattaa pitää `**💭 Perustelut:**` -callout enintään ~6
rivin mittaisena, raskaampi reasoning vaatii ehkä erillisen
`<details>`-laatikon (UI-puolella expandable).

---

## #10 Provenance threading — pipe structured tool results to LEAD + UI  *(keskisuuri, seuraava)*

> **Status: seuraava toteutettava.** Foundational fix: ilman tätä
> parempi LEAD-malli (#9) ei silti voi diffata agentin claimeja
> työkaluvastaukseen, koska se ei näe raakadataa. Kustannusvaikutus
> ~2x input-tokenit (Flash Lite-mallilla senttejä päivässä), toisin
> kuin #9:n mallinvaihto joka olisi ~40-200x kalliimpi per kysely.

Nykyinen ketju: `tool → subagent (LLM tiivistää tekstiksi) → LEAD näkee vain tekstin`.

Sub-agentin tiivistys on häviöllinen kompressio: kalenterin 18 itemiä
voi typistyä 3:ksi, P/E-numeron desimaali voi droppaantua, yhtiönimi
voi vaihtua plausibleksi-mutta-vääräksi. LEAD ei voi tarkistaa
yhtään näistä koska se ei näe raakadataa.

**Korjaus**: säilötään tool-callit ja niiden tulokset rakenteellisesti
ja syötetään LEAD:lle.

```
tool → subagent
       ├─ teksti (kuten nyt)  ─┐
       └─ raw JSON              ├─→ LEAD näkee molemmat
                                │
                                └─→ UI näyttää "tool call" -laatikon expandable
```

### Ratkaisee suoraan

| Bugi | Mekanismi |
|---|---|
| Case 001 / 4a — hallusinointi (claim ≠ tool data) | LEAD näkee tool-tuloksen entiteetit, voi pudottaa claimit joita ei dataa tukena |
| Case 4b — false negative (tool data piilotettu) | LEAD näkee että listassa oli N item, voi vaatia agentin selittävän miksi M < N |
| Numeerinen virhe (P/E 12 vs 18) | LEAD voi ristivertailla raakadataan |
| Attribution error (claim "X sanoi", tosiasiassa Y) | LEAD näkee mistä tool-vastauksesta data tuli |

### Konkreettinen toteutus

1. **`SubagentResult`-rakenteeseen `tool_calls: list[ToolCallTrace]`**
   — agent_framework jo tallentaa tool_call-osat response.parts:eihin;
   uutta on niiden ekstraktointi `observability/output_parts.py`:ssa
   ja serialisointi.

2. **`run_log` persistöi**: subagent-NN-*.json saa kentän `tool_calls:
   [{name, args, result_summary, item_count, first_n_items}]`. Jos
   raakadata on iso (>50 itemiä), tallennetaan se erilliseen
   `subagent-NN-tool-results.json`-tiedostoon, JSON-runkoon vain
   yhteenveto.

3. **`synthesis.py` formatoi LEAD-promptin uuden blokin**
   *"TOOL CALL TRACE"*:
   ```
   Subagent 1 (sentiment) called list-calendar-events:
     args: {dateFrom: 2026-05-07, dateTo: 2026-05-07, regions: [FINLAND]}
     result: 18 items; types=[INTERIM_REPORT(15), GENERAL_MEETING(2),
             TRIANNUAL_DIVIDEND(1)]
     companies: [Stora Enso, Harvia, SRV Group, ..., NoHo Partners]
   ```
   Lead-prompttiin uusi instruktio: *"compare each subagent claim to
   what the tools actually returned; drop unsupported claims, surface
   omitted-but-relevant items."*

4. **UI: "🔧 Työkalut"-laatikko jokaisen subagent-laatikon alle**,
   expandable, näyttää tool-kutsut + tulokset käyttäjälle. Tämä on
   transparency-feature joka samalla helpottaa debugausta.

5. **Conflict-detector promptiin (myöhemmin)** voidaan myös laittaa
   tool-result viittaukset, mutta tämä ei ole MVP:ssä — riittää että
   LEAD:llä on data.

### Token-kustannus

Per Puuilo-tyyppinen 10-subagentti-kysely:
- Nykyinen LEAD-prompt: ~30-45k tokens input
- Provenance:lla: ~50-90k tokens input (lisäys ~20-50k)
- Hinta Flash Lite -mallilla: $0.004 → $0.007 per kysely
- 100 kyselyä/päivä = +$0.30/päivä, 1000/pv = +$3/päivä. Käytännössä senttejä.

### Riippuvuudet ja seuraajat

- **Edellytys #9:lle (parempi LEAD-malli)** — ilman raakadataa
  Sonnet/Opus ei voi tehdä parempaa diffia kuin Flash Lite.
- **Helpottaa evals-rakentamista (#4-vaiheinen polku alempana)** —
  golden run voi replayata tool-callit suoraan, eikä tarvitse rerunnata
  koko fan-outtia.
- **Päällekkäisyys "Tool-result entity validation post-processor":n
  kanssa** (Tool-result-rehellisyys -osio): provenance threading on
  *yleisempi* ratkaisu samaan ongelmaan. Entity-validation pysyy
  kelvollisena nopeana plug-in:ina jos LLM-pohjainen vahti ei riitä.

---

## Pienempiä ideoita / nice-to-have

- **Confidence scoring**: Jokainen subagentti raportoi 1-5 confidence per claim
- **Source provenance per claim**: Jokainen claim synteesissä → eksplisiittinen
  inline-viittaus (`(get-fundamentals/Sampo, 2025)`). PR #29 toi klikattavat
  linkit Lähteet-osioon, mut väitteen kanssa rinnakkain olevat tarkat
  citations vielä puuttuvat. *(Suora osuma vs. observed hallusinaatiot —
  ks. `evals/known-cases.md` Case 001.)*
- **Web search -työkalu RESEARCHille**: Pull recent news context (esim. Reuters/Bloomberg)
- **PDF-raportit**: "Vie tämä kysely PDF:ksi" → matplotlib-charts + tableat + analyysi
- **Plotly-chartit QUANTille**: Time-series, bar, scatter — `st.plotly_chart` natiivi.
  Suositeltu prioriteettivertailussa Inderesin Noraan; user-visible big win.
- **Historiallinen backtest**: "Mitä olisit suositellut 3kk sitten Sammosta?" — agentti
  rajaa kontekstinsa siihen päivämäärään ja katsoo nyt miten ennuste osui
- **Streaming output**: Token-by-token vastauksen renderöinti chat-bubblessa
- **Feedback loop**: 👍/👎 jokaisen vastauksen alla, kerätään dataa promptien parantamiseksi.
  *Tämän toteutus on portti evals-pohjaan — ks. alempi "Evals-rakentaminen".*
- **Konfliktinratkaisu kun MCP-data puuttuu**: Tällä hetkellä joskus QUANT raportoi "data
  ei saatavilla" mutta LEAD ei tiedä että puuttuu. Eksplisiittinen "missing data"-flag
  subagent-vastauksissa, LEAD ottaa huomioon synteesissä.

---

## Tool-result-rehellisyys (uusia, tämän keskustelun nostamia)

Konkreettiset bugit jotka ovat ajaneet näihin: ks. `evals/known-cases.md`.

- **Tool-result entity validation post-processor** *(koodi-taso)*. Per
  subagent-vastaus: ekstraktoi yhtiönimet tool-tuloksesta (`companyName`
  -kentästä), ekstraktoi vastauksen mainitsemat yhtiöt (regex tai NER),
  ja diffaa: jos vastauksessa nimi jota ei tool-tuloksessa → flag → retry
  lisätyllä kontekstilla ("älä keksi"). **Korjaisi Case 001:n
  automaattisesti.**
- **Result-completeness check** *(koodi-taso)*. Jos tool palauttaa N
  itemiä ja agent listaa M < N kun käyttäjä kysyi listausta → pakota
  agentti joko (a) listaamaan kaikki tai (b) eksplisiittisesti sanomaan
  "N tapahtumaa, näytän tärkeimmät Y koska...". **Korjaisi Case 002:n.**
- **Default-region inference**. Suomenkielinen kysely kontekstissa
  joka ei eksplisiittisesti mainitse muuta maata → defaulttaa
  `regions=[FINLAND]`. Voi olla joko prompt-rivi tai koodi-taso wrapper.
- **Smarter model for synthesis (parked Pro toggle)**. Flash Lite tekee
  havaittuja virheitä joita Pro-luokan malli tekisi todennäköisesti
  vähemmän — judgment-issuet (regions-filter), faithful summarization,
  rule-following. LEAD on luonteva paikka mihin laittaa parempi malli,
  koska se on yksi kutsu per kysely. Branch on parked
  `feat/lead-pro-toggle`-haarassa MAF-yhteensopivuusongelman takia.

---

## Evals-rakentaminen — ennen muiden featureiden lisäämistä

Tämän vaatimattaman lopun tarkoitus on dokumentoida miksi nykyinen
*kehitysjärjestys on prioriteettijärjestys*: ilman mittaria emme tiedä
parantavatko tai pahentavatko featuremuutokset systeemiä.

Toisen Claude-session kanssa keskusteltu 4-tasoinen polku:

1. **👍👎 user feedback in UI** *(yksi ilta)* — `feedback.json` per run,
   ei pakota kommenttia. Kerää oikeaa-käyttöä-koskevaa palautetta.
2. **Smoke test** *(yksi ilta)* — pytest-fixture jossa 5-10 known-good
   queryä. Routing pitää olla oikea, vähintään yksi oikea tool-call,
   vastaus ei tyhjä, tunnetut avainsanat löytyvät.
3. **`evals/golden.yaml` + `scripts/replay.py`** *(yksi ilta)* —
   kuratoidut run_id:t referensseinä, replay diffaa rakennetta (router,
   tool-calls, key entities) raw-tekstiä unohtaen.
4. **Production monitoring** *(jatkuva)* — aggregointiskripti joka
   näyttää viikon thumbs-up/down -suhteen, kategorisoi virhetyypit.

`evals/known-cases.md` on jo aloitettu — jokainen sieltä löytyvä
tapaus on potentiaalinen golden-rivi. Case 001 + Case 002 ovat selkeät
ensimmäiset.

**Kunnes evals-pohja on rakennettu, AI-kyvykkyysfeaturet (kohdat
"Tool-result-rehellisyys" yllä) eivät kannata investoida — emme tiedä
toimivatko korjaukset.**

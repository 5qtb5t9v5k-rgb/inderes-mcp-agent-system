/* Each artboard = one screen / one design question. */

const PUUILO_QUERY = '"Analysoi Puuilon myymäläverkoston kasvun tehokkuutta viimeisen 5 vuoden aikana: kuinka paljon liikevaihto on kasvanut per uusi myymälä (same-store sales + new stores -vaikutus), ja onko kasvustrategia edelleen kannattavaa vai näkyykö jo kannattavuuden heikentymistä uusissa myymälöissä?"';

/* 01 — Empty state */
function ABEmpty() {
  return (
    <div className="ad">
      <Topbar runId="—" />
      <div className="ad__body">
        <Sidebar />
        <main className="main">
          <div className="main__scroll">
            <Hero />
            <div style={{flex:1}}></div>
            <ChatInput />
          </div>
        </main>
      </div>
    </div>
  );
}

/* 02 — Mid-run (live status, no answer yet) */
function ABMidRun() {
  const lines = [
    { state:'done', ic:'🧭', body:'Reititin kysymyksen — <em>QUANT + RESEARCH</em> · kohde: <em>Puuilo</em>', ts:'+0.4s' },
    { state:'done', ic:'⚙', body:'Subagentit käynnistyivät rinnakkain', ts:'+0.5s' },
    { state:'done', ic:'▲', body:'<em style="color:var(--p-quant)">QUANT</em> haki tunnusluvut — <span class="muted">2 työkalukutsua</span>', ts:'+5.1s' },
    { state:'running', ic:'▲', body:'<em style="color:var(--p-quant)">QUANT</em> ajaa Pythonia: revenue / new-store-count', ts:'+8.2s' },
    { state:'running', ic:'■', body:'<em style="color:var(--p-research)">RESEARCH</em> kahlaa tilinpäätösraporttia FY2025', ts:'+8.2s' },
    { state:'pending', ic:'◇', body:'Konflikti-detektori — odottaa subagenttien valmistumista', ts:'' },
    { state:'pending', ic:'◆', body:'<em style="color:var(--p-lead)">LEAD</em> yhdistää tulokset synteesiksi', ts:'' },
  ];
  return (
    <div className="ad">
      <Topbar />
      <div className="ad__body">
        <Sidebar activePersonas={['quant','research']} current={0} />
        <main className="main">
          <div className="main__scroll">
            <Hero activePersonas={['quant','research']} showSubline={false} />
            <QueryBubble>{PUUILO_QUERY}</QueryBubble>
            <LiveStatus elapsed={8.4} lines={lines} />
          </div>
        </main>
      </div>
    </div>
  );
}

/* 03 — Result, log COLLAPSED. Päättely B (structured) shown as primary. */
function ABResult() {
  return (
    <div className="ad">
      <Topbar />
      <div className="ad__body">
        <Sidebar activePersonas={['quant','research']} current={0} />
        <main className="main">
          <div className="main__scroll">
            <Hero activePersonas={['quant','research']} showSubline={false} />
            <QueryBubble>{PUUILO_QUERY}</QueryBubble>

            <TimelineStrip duration={21.4} count={2} agents={['quant','research']} />

            <Perustelut>
              Yhdistin kvantitatiivisen analyysin (historiallinen kasvu ja marginaalikehitys) yhtiön tuoreimman tilinpäätösraportin laadullisiin strategiahavaintoihin. Painotin erityisesti konfliktien selvittämistä — EBIT-marginaalin ja myymälämäärän eroavaisuudet — tuomalla esiin raportoidut luvut ja niiden tulkintaerot.
            </Perustelut>

            <div className="answer">
              <h2>Kasvun tehokkuus ja kannattavuus</h2>
              <p>
                Puuilon myymäläverkoston laajentaminen on ollut viimeisen viiden vuoden aikana erittäin tehokasta:
                liikevaihto on kasvanut <strong>270 → 442&nbsp;M€</strong><a className="fn q" title="QUANT · get-fundamentals">¹</a>
                samalla kun oikaistu EBITA-marginaali on pysynyt <strong>17,5&nbsp;%</strong> tasolla
                <a className="fn r" title="RESEARCH · Tilinpäätös 2025">²</a>.
              </p>
              <ul>
                <li><b>Myymäläverkosto:</b> 56 myymälää tilikauden 2025 lopussa<a className="fn r" title="RESEARCH">²</a>, kasvu 7–10 myymälää vuodessa.</li>
                <li><b>Liikevaihtoa per uusi myymälä:</b> ~<strong>11,3&nbsp;M€</strong> (5v keskiarvo, Python-laskelma)<a className="fn q" title="QUANT · pythonin laskelma">¹</a>.</li>
                <li><b>Skaalautuvuus:</b> uudet myymälät kannattavia jo ensimmäisen kuukauden aikana avauksesta<a className="fn r" title="RESEARCH">²</a>.</li>
              </ul>

              <h2>Strategiset riskit</h2>
              <p>Vaikka historiadata tukee strategiaa, laajentumiseen liittyy uusia muuttujia:</p>
              <ul>
                <li><b>Kansainvälistyminen:</b> Ruotsiin seuraavan 18 kk aikana — uusi suoritustason riski.</li>
                <li><b>Markkinakylläisyys:</b> kotimaan tihentäminen edellyttää tarkkaa sijaintivalintaa kannibalisoinnin välttämiseksi.</li>
              </ul>
            </div>

            <PaattelyB slots={{
              disagree: 'Subagentit käyttivät eri mittareita kannattavuuteen (<code>EBIT 17,03 %</code> vs. <code>oikaistu EBITA 17,5 %</code>) ja myymälämäärään (<code>45 vs. 56</code>).',
              resolution: 'Käytin tuoreinta tilinpäätösraporttia (<b>RESEARCH</b>) lähteenä 56 myymälälle ja oikaistulle 17,5&nbsp;% marginaalille — heijastavat virallista raportointia tarkemmin.',
              uncertain: 'Vertailukelpoisen myynnin 3,7&nbsp;% kasvu on yksittäisen raportin varassa, mutta johdonmukainen yhtiön strategian kanssa.',
              skipped: 'En arvioinut Ruotsin-laajentumisen onnistumistodennäköisyyttä — esitin sen strategisena riskinä/mahdollisuutena.',
            }}/>

            <Sources items={[
              { title:'Puuilo (FI) — Tilinpäätöstiedote 2025', date:'25.03.2026', url:'#' },
              { title:'Puuilo Oy — Halpakaupan uusin peluri (foorumi-thread)', date:'05.05.2026', url:'#' },
            ]}/>

            <FollowUps items={[
              'Miten Puuilon arvostuskertoimet (P/E) vertautuvat muihin pohjoismaisiin halpakauppoihin?',
              'Mitä riskejä Ruotsin laajentumisessa on Inderesin analyysin mukaan?',
              'Miten Puuilon osinko ja tase kestävät tulevan investointivaiheen?',
            ]}/>

            <ChatInput />
          </div>
        </main>
      </div>
    </div>
  );
}

/* 04 — Result with side panel (log placement option A) */
function ABResultPanel() {
  return (
    <div className="ad">
      <Topbar />
      <div className="ad__body ad__body--withpanel">
        <Sidebar activePersonas={['quant','research']} current={0} />
        <main className="main">
          <div className="main__scroll">
            <Hero activePersonas={['quant','research']} showSubline={false} />
            <QueryBubble>{PUUILO_QUERY}</QueryBubble>
            <Perustelut>
              Yhdistin kvantitatiivisen analyysin yhtiön tuoreimman tilinpäätösraportin laadullisiin strategiahavaintoihin. Painotin konfliktien selvittämistä raportoitujen lukujen tulkintaeroissa.
            </Perustelut>

            <div className="answer">
              <h2>Kasvun tehokkuus ja kannattavuus</h2>
              <p>
                Liikevaihto kasvanut <strong>270 → 442&nbsp;M€</strong><a className="fn q" title="QUANT">¹</a>;
                oikaistu EBITA pysyi <strong>17,5&nbsp;%</strong><a className="fn r" title="RESEARCH">²</a>.
              </p>
              <ul>
                <li><b>Myymäläverkosto:</b> 56 myymälää, kasvu 7–10 / vuosi<a className="fn r">²</a>.</li>
                <li><b>Liikevaihtoa per uusi myymälä:</b> ~11,3&nbsp;M€<a className="fn q">¹</a>.</li>
                <li><b>Skaalautuvuus:</b> kannattava 1. kuukauden aikana<a className="fn r">²</a>.</li>
              </ul>
              <h2>Strategiset riskit</h2>
              <p>Ruotsin-laajentuminen, markkinakylläisyys.</p>
            </div>

            <PaattelyA open={false}/>
            <Sources items={[
              { title:'Puuilo — Tilinpäätöstiedote 2025', date:'25.03.2026', url:'#' },
            ]}/>
            <ChatInput />
          </div>
        </main>
        <ActivityPanel />
      </div>
    </div>
  );
}

/* 05 — Result with INLINE expander (log placement option B) */
function ABResultInline() {
  return (
    <div className="ad">
      <Topbar />
      <div className="ad__body">
        <Sidebar activePersonas={['quant','research']} current={0} />
        <main className="main">
          <div className="main__scroll">
            <Hero activePersonas={['quant','research']} showSubline={false} />
            <QueryBubble>{PUUILO_QUERY}</QueryBubble>

            <Perustelut>
              Yhdistin kvantitatiivisen analyysin yhtiön tuoreimman tilinpäätösraportin laadullisiin strategiahavaintoihin.
            </Perustelut>

            <div className="answer">
              <h2>Kasvun tehokkuus ja kannattavuus</h2>
              <p>
                Liikevaihto kasvanut <strong>270 → 442&nbsp;M€</strong><a className="fn q" title="QUANT">¹</a>;
                oikaistu EBITA pysyi <strong>17,5&nbsp;%</strong><a className="fn r" title="RESEARCH">²</a>.
              </p>
              <ul>
                <li><b>Myymäläverkosto:</b> 56 myymälää<a className="fn r">²</a>.</li>
                <li><b>Liikevaihtoa per uusi myymälä:</b> ~11,3&nbsp;M€<a className="fn q">¹</a>.</li>
              </ul>
            </div>

            <PaattelyB slots={{
              disagree: '<code>EBIT 17,03 %</code> vs. <code>oikaistu EBITA 17,5 %</code>; myymälämäärä <code>45 vs. 56</code>.',
              resolution: 'Käytin tuoreinta tilinpäätösraporttia (RESEARCH) lähteenä.',
              uncertain: 'Vertailukelpoisen myynnin 3,7&nbsp;% on yksittäisen raportin varassa.',
              skipped: 'En arvioinut Ruotsin-laajentumisen todennäköisyyttä.',
            }}/>

            {/* INLINE LOG — paneloitu, ei mega-expander */}
            <div className="inline-log">
              <div className="inline-log__head">
                <span>🔍</span>
                <b>AGENTTIEN TOIMINTALOKI</b>
                <span style={{color:'var(--ink-3)'}}>21.4s · 2 agenttia · 6 työkalukutsua</span>
                <span className="chev">▾ avoinna</span>
              </div>
              <div className="inline-log__lay">
                <div className="inline-log__nav">
                  <div className="ent is-active"><span className="glyph" style={{color:'var(--p-lead)'}}>◆</span><span>Yhteenveto</span><span className="ms">21.4s</span></div>
                  <div className="ent"><span className="glyph" style={{color:'var(--p-quant)'}}>▲</span><span>QUANT</span><span className="ms">12.3s</span></div>
                  <div className="ent"><span className="glyph" style={{color:'var(--p-research)'}}>■</span><span>RESEARCH</span><span className="ms">12.0s</span></div>
                  <div className="ent"><span style={{width:14}}>◇</span><span>Konflikti-detekt.</span><span className="ms">2.4s</span></div>
                  <div className="ent"><span className="glyph" style={{color:'var(--p-lead)'}}>◆</span><span>LEAD synteesi</span><span className="ms">5.8s</span></div>
                </div>
                <div className="inline-log__detail">
                  <div className="metrics" style={{marginBottom:14}}>
                    <div className="metric"><div className="lab">DURATION</div><div className="v num">21.4s</div></div>
                    <div className="metric"><div className="lab">SUBAGENTIT</div><div className="v num">2</div></div>
                  </div>
                  <div className="stages">
                    <div className="stage"><span className="nm">routing</span><div className="bar"><i style={{left:'0%', width:'2%', background:'var(--p-lead)'}}/></div><span className="v">0.4s</span></div>
                    <div className="stage"><span className="nm">QUANT</span><div className="bar"><i style={{left:'2%', width:'57%', background:'var(--p-quant)'}}/></div><span className="v">12.3s</span></div>
                    <div className="stage"><span className="nm">RESEARCH</span><div className="bar"><i style={{left:'2%', width:'56%', background:'var(--p-research)'}}/></div><span className="v">12.0s</span></div>
                    <div className="stage"><span className="nm">conflicts</span><div className="bar"><i style={{left:'59%', width:'11%', background:'var(--ink-2)'}}/></div><span className="v">2.4s</span></div>
                    <div className="stage"><span className="nm">LEAD</span><div className="bar"><i style={{left:'70%', width:'27%', background:'var(--p-lead)'}}/></div><span className="v">5.8s</span></div>
                  </div>
                  <div style={{marginTop:14, color:'var(--ink-2)', fontSize:11}}>
                    Klikkaa vasemmalta agenttia nähdäksesi sen ajatusketjun ja työkalukutsut.
                  </div>
                </div>
              </div>
            </div>

            <Sources items={[
              { title:'Puuilo — Tilinpäätöstiedote 2025', date:'25.03.2026', url:'#' },
            ]}/>
            <ChatInput />
          </div>
        </main>
      </div>
    </div>
  );
}

/* 06 — Päättely A vs B comparison (single artboard, two columns) */
function ABPaattelyCompare() {
  return (
    <div className="ad" style={{padding:'24px 32px', overflow:'auto'}}>
      <div style={{display:'grid', gridTemplateColumns:'1fr 1fr', gap:24, height:'100%'}}>
        <div style={{display:'flex', flexDirection:'column', gap:14}}>
          <div className="hero__eyebrow">OPTION A — PROOSA, KUTEN MALLI TUOTTAA SEN</div>
          <div style={{color:'var(--ink-2)', fontSize:12, lineHeight:1.6}}>
            Hyväksytään mallin tuottama vapaa proosa. Kerrotaan visuaalisesti
            "tämä on meta, ei vastaus" — italic-quote, kollapsi-affordanssi, hillitty chrome.
            Halpa toteuttaa, formaatti-rikkoutumiset eivät ole kohtalokkaita.
          </div>
          <PaattelyA open={true}>
            <p style={{margin:0}}>
              Subagentit käyttivät eri mittareita kannattavuuteen (EBIT 17,03 % vs. oikaistu EBITA 17,5 %) ja myymälämäärään (45 vs. 56). Käytin tuoreinta tilinpäätösraporttia lähteenä 56 myymälälle ja oikaistulle 17,5 % marginaalille, sillä ne heijastavat yhtiön virallista raportointia tarkemmin. Vertailukelpoisen myynnin 3,7 % kasvu on yksittäisen raportin varassa, mutta johdonmukainen yhtiön kasvustrategian kanssa. En ottanut kantaa Ruotsin-laajentumisen onnistumisen todennäköisyyteen, vaan esitin sen strategisena riskinä.
            </p>
          </PaattelyA>
          <div style={{color:'var(--ink-2)', fontSize:11, lineHeight:1.6}}>
            <b style={{color:'var(--ink-0)'}}>+</b> Yksinkertainen. Ei JSON-parsausta. Toimii vaikka Flash Lite ohittaisi rakenteen.<br/>
            <b style={{color:'var(--ink-0)'}}>+</b> Luonteva luettavuus.<br/>
            <b style={{color:'var(--ink-0)'}}>−</b> Ei skannattavaa. 4 elementtiä — agreement / resolution / uncertain / skipped — ovat näkymättömiä.<br/>
            <b style={{color:'var(--ink-0)'}}>−</b> Ei voi linkittää slottikohtaisesti (esim. "näytä vain mitä jäi tekemättä").
          </div>
        </div>

        <div style={{display:'flex', flexDirection:'column', gap:14}}>
          <div className="hero__eyebrow" style={{color:'var(--p-lead)'}}>OPTION B — STRUKTUROIDUT SLOTIT (suositus)</div>
          <div style={{color:'var(--ink-2)', fontSize:12, lineHeight:1.6}}>
            LEAD palauttaa JSON-objektin <code style={{background:'var(--bg-2)', padding:'1px 4px', borderRadius:2}}>&#123; disagree, resolution, uncertain, skipped &#125;</code>.
            UI rendered 4 slottia 2×2-gridissä, omilla glyfeillään ja väreillään.
            Kerrokset näkyvät yhdellä silmäyksellä; suoraviivaista linkittää konflikti-detektorin dataan.
          </div>
          <PaattelyB slots={{
            disagree: 'Subagentit käyttivät eri mittareita: <code>EBIT 17,03 %</code> vs. <code>oikaistu EBITA 17,5 %</code>; myymälämäärä <code>45 vs. 56</code>.',
            resolution: 'Käytin tuoreinta tilinpäätösraporttia (<b>RESEARCH</b>) lähteenä 56 myymälälle ja oikaistulle 17,5&nbsp;% marginaalille.',
            uncertain: 'Vertailukelpoisen myynnin 3,7&nbsp;% kasvu on yksittäisen raportin varassa.',
            skipped: 'En arvioinut Ruotsin-laajentumisen onnistumistodennäköisyyttä — esitin sen strategisena riskinä.',
          }}/>
          <div style={{color:'var(--ink-2)', fontSize:11, lineHeight:1.6}}>
            <b style={{color:'var(--ok)'}}>+</b> Skannattava. Käyttäjä näkee heti, mitä jäi tekemättä.<br/>
            <b style={{color:'var(--ok)'}}>+</b> Konflikti-detektorin <code style={{background:'var(--bg-2)', padding:'1px 4px', borderRadius:2}}>conflicts.json</code> mappaa luonnollisesti slot-rakenteeseen.<br/>
            <b style={{color:'var(--ok)'}}>+</b> Slot voi puuttua → UI piilottaa sen, ei rikkoo.<br/>
            <b style={{color:'var(--err)'}}>−</b> Vaatii LEAD-promptin viimeistelyn JSON-outputtia varten — joka on jo tehty conflict-detektorille, joten matala riski.
          </div>
        </div>
      </div>
    </div>
  );
}

/* 07 — Conflict callout (when resolution genuinely uncertain) */
function ABConflict() {
  return (
    <div className="ad">
      <Topbar />
      <div className="ad__body">
        <Sidebar activePersonas={['quant','research','sentiment']} current={0} />
        <main className="main">
          <div className="main__scroll">
            <Hero activePersonas={['quant','research','sentiment']} showSubline={false} />
            <QueryBubble>"Mikä on Sammon näkymä Q2:lle — onko kasvuvauhti hidastumassa?"</QueryBubble>
            <TimelineStrip duration={28.7} count={3} agents={['quant','research','sentiment']} />

            <Perustelut>
              Subagenttien näkemys eroaa. <b style={{color:'var(--ink-1)', fontStyle:'normal'}}>QUANT</b> näkee selvän hidastumisen YoY-luvuissa,
              <b style={{color:'var(--ink-1)', fontStyle:'normal'}}> RESEARCH</b> tukee Inderesin nostotekstiä, ja
              <b style={{color:'var(--ink-1)', fontStyle:'normal'}}> SENTIMENT</b> löytää foorumikeskustelusta sekalaista signaalia.
              En sulje konfliktia hiljaisesti — alla kummankin pohja.
            </Perustelut>

            <ConflictCallout
              topic="Q2-kasvun trendi"
              positions={[
                { persona:'quant', claim:'YoY-kasvu hidastunut Q1:n 8,4 %:sta arvioon 5,2 % — get-fundamentals + estimaatit.' },
                { persona:'research', claim:'Inderes pitää suosituksen INCREASE; analyytikko nostaa target-hintaa 11→12€.' },
                { persona:'sentiment', claim:'Foorumikeskustelussa sekä bullish (DPS) että bearish (capacity) signaaleja, vahvempi bullish.' },
              ]}
            />

            <div className="answer">
              <h2>Yhteenveto</h2>
              <p>
                Lyhyellä aikavälillä on todellinen jännite: <strong>numerot</strong> osoittavat hidastumisen suuntaan,
                mutta <strong>analyytikon näkemys</strong> ja <strong>foorumikeskustelu</strong> tukevat positiivista narratiivia.
                Ratkaisuni on raportoida molemmat — käyttäjä voi tehdä oman painotuksensa.
              </p>
            </div>

            <div className="anno">DESIGN NOTE — 🔀 callout näkyy VAIN kun resolution on aidosti epävarma. Useimmissa ajoissa se ratkaistaan hiljaisesti Perustelut-blokkiin.</div>

            <ChatInput />
          </div>
        </main>
      </div>
    </div>
  );
}

Object.assign(window, {
  ABEmpty, ABMidRun, ABResult, ABResultPanel, ABResultInline, ABPaattelyCompare, ABConflict,
});

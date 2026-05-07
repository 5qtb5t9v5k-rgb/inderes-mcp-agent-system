/* Reusable parts of the Agent Desk UI — all artboards compose from these. */

const PERSONAS = {
  lead:      { glyph: '◆', name: 'LEAD',      role: 'Päätoimittaja' },
  quant:     { glyph: '▲', name: 'QUANT',     role: 'Numerot' },
  research:  { glyph: '■', name: 'RESEARCH',  role: 'Analyytikko' },
  sentiment: { glyph: '●', name: 'SENTIMENT', role: 'Tunnelmat' },
  portfolio: { glyph: '✦', name: 'PORTFOLIO', role: 'Mallisalkku' },
};

function Topbar({ runId = '20260507-153211', model = 'gemini-3.1-flash-lite-preview' }) {
  return (
    <div className="ad__topbar">
      <span className="ad__brand">INDERES<span className="slash">//</span>AGENT · DESK</span>
      <span className="sep">│</span>
      <span>run {runId}</span>
      <span className="sep">│</span>
      <span>{model}</span>
      <div className="ad__status">
        <span className="dot"></span>
        <span>mcp.inderes.com · verkossa</span>
      </div>
    </div>
  );
}

function Sidebar({ activePersonas = [], runs = SAMPLE_RUNS, current = 0 }) {
  const personaList = ['lead','quant','research','sentiment','portfolio'];
  return (
    <aside className="side">
      <div className="side__disc">
        <b>HUOM</b>
        Ei Inderes Oyj:n tuottama tai hyväksymä. Ei sijoitusneuvoja.
      </div>

      <div className="side__sec">
        <h3>AGENTIT</h3>
        {personaList.map(p => {
          const isActive = activePersonas.includes(p);
          const dim = activePersonas.length > 0 && !isActive;
          return (
            <div key={p} className={`side__row ${dim ? 'is-dim' : ''} ${isActive ? 'is-active' : ''}`}>
              <span className={`glyph ${p}`} style={{color:`var(--p-${p})`}}>{PERSONAS[p].glyph}</span>
              <div className="nm">
                <b>{PERSONAS[p].name}</b>
                <span>{PERSONAS[p].role}</span>
              </div>
            </div>
          );
        })}
      </div>

      <div className="side__sec">
        <h3>VIIMEISIMMÄT AJOT</h3>
        {runs.map((r,i) => (
          <div key={i} className="side__run" style={i===current ? {background:'var(--bg-2)'} : null}>
            <span className="ts">{r.ts}</span>
            <span className="glyphs">
              {r.agents.map((a,j) => <span key={j} style={{color:`var(--p-${a})`}}>{PERSONAS[a].glyph}</span>)}
            </span>
            <span className="q">{r.q}</span>
          </div>
        ))}
      </div>
    </aside>
  );
}

const SAMPLE_RUNS = [
  { ts: '15:32', agents: ['quant','research'], q: 'Analysoi Puuilon myymäläverkoston kasvun…' },
  { ts: '14:08', agents: ['quant','research','sentiment','portfolio'], q: 'Mitkä pankkiosakkeet näyttävät…' },
  { ts: '11:42', agents: ['research'], q: 'Mitä Inderes sanoo Sammon Q1:stä?' },
  { ts: '10:15', agents: ['quant','sentiment'], q: 'Onko Keskon insider-kaupoissa…' },
  { ts: 'eilen', agents: ['portfolio'], q: 'Mallisalkun viimeiset muutokset' },
];

function Hero({ activePersonas = [], showSubline = true }) {
  const personaList = ['lead','quant','research','sentiment','portfolio'];
  return (
    <div className="hero">
      <div className="hero__eyebrow">MULTI-AGENT RESEARCH</div>
      <div className="hero__h1">
        INDERES <span className="plus">+</span> MCP <span className="plus">+</span> AGENTIT <span className="eq">=</span> <span className="res">INSIGHTS</span>
      </div>
      {showSubline && <div className="hero__sub">Tutki pohjoismaisia osakkeita viiden erikoistuneen agentin kautta.</div>}
      <div className="glyph-row">
        {personaList.map(p => (
          <span key={p} className={`gg ${activePersonas.length && !activePersonas.includes(p) ? 'is-dim' : ''}`}>
            <span className={p} style={{color:`var(--p-${p})`}}>{PERSONAS[p].glyph}</span>
            <span style={{color:`var(--p-${p})`}}>{PERSONAS[p].name}</span>
          </span>
        ))}
      </div>
    </div>
  );
}

function ChatInput({ value = '' }) {
  return (
    <div className="input">
      <span className="prompt">›</span>
      <span className="ph">{value || 'Kysy osakkeesta, sektorista tai mallisalkusta…'}</span>
      <span className="send">↑</span>
    </div>
  );
}

function QueryBubble({ children }) {
  return (
    <div className="qbox">
      <span className="who">DA</span>
      <div className="text">{children}</div>
    </div>
  );
}

/* ── Live status (mid-run) ─────────────────────────────────────────── */
function LiveStatus({ elapsed = 8.4, lines }) {
  return (
    <div className="live">
      <div className="live__head">
        <span className="pulse"></span>
        <b>KÄSITTELEN KYSYMYSTÄSI</b>
        <span className="timer">{elapsed.toFixed(1)}s</span>
      </div>
      {lines.map((l,i) => (
        <div key={i} className={`live__line is-${l.state}`}>
          <span className="ic">{l.ic}</span>
          <span className="body" dangerouslySetInnerHTML={{__html: l.body}}/>
          {l.ts && <span className="ts">{l.ts}</span>}
        </div>
      ))}
    </div>
  );
}

/* ── Result: collapsed timeline ────────────────────────────────────── */
function TimelineStrip({ duration = 21.4, count = 2, agents = ['quant','research'], onOpen }) {
  return (
    <div className="timeline" onClick={onOpen}>
      <span className="lab">AIKAJANA</span>
      <span className="v">{duration.toFixed(1)}s</span>
      <span className="lab">·</span>
      <span className="v">{count} agenttia</span>
      <span className="ag">
        {agents.map((a,i) => <span key={i} style={{color:`var(--p-${a})`}}>{PERSONAS[a].glyph} {PERSONAS[a].name}</span>)}
      </span>
      <span className="open">avaa loki ›</span>
    </div>
  );
}

/* ── Reasoning Perustelut ──────────────────────────────────────────── */
function Perustelut({ children }) {
  return (
    <div className="reasoning">
      <b>PERUSTELUT</b>
      {children}
    </div>
  );
}

/* ── Päättely option A: prose ──────────────────────────────────────── */
function PaattelyA({ open = false, children }) {
  return (
    <div className="paattely-a">
      <div className="paattely-a__head">
        <span className="chev">{open ? '▼' : '▶'}</span>
        <span>🧠</span>
        <b>Päättely</b>
        <span style={{color:'var(--ink-3)', marginLeft:'auto'}}>avaa nähdäksesi ajatusketju</span>
      </div>
      {open && <div>{children}</div>}
    </div>
  );
}

/* ── Päättely option B: structured slots ──────────────────────────── */
function PaattelyB({ slots }) {
  // slots = { disagree, resolution, uncertain, skipped }
  return (
    <div className="paattely-b">
      <div className="paattely-b__head">
        <span>🧠</span>
        <b>Päättely</b>
        <span className="meta">4 / 4 slottia · LEAD</span>
      </div>
      <div className="paattely-b__grid">
        <div className="slot disagree">
          <div className="slot__lab"><span className="icn">⚡</span> ERIMIELISYYS</div>
          <div className="slot__body" dangerouslySetInnerHTML={{__html: slots.disagree}}/>
        </div>
        <div className="slot resolution">
          <div className="slot__lab"><span className="icn">✓</span> MITEN RATKAISIN</div>
          <div className="slot__body" dangerouslySetInnerHTML={{__html: slots.resolution}}/>
        </div>
        <div className="slot uncertain">
          <div className="slot__lab"><span className="icn">?</span> EPÄVARMA</div>
          <div className="slot__body" dangerouslySetInnerHTML={{__html: slots.uncertain}}/>
        </div>
        <div className="slot skipped">
          <div className="slot__lab"><span className="icn">⊘</span> JÄTIN TEKEMÄTTÄ</div>
          <div className="slot__body" dangerouslySetInnerHTML={{__html: slots.skipped}}/>
        </div>
      </div>
    </div>
  );
}

/* ── Conflict callout (only when resolution is genuinely uncertain) ── */
function ConflictCallout({ topic, positions }) {
  return (
    <div className="conflict">
      <div className="conflict__head">🔀 SUBAGENTIT ERIMIELTÄ — {topic}</div>
      {positions.map((p,i) => (
        <div key={i} className="conflict__row">
          <span className="who" style={{color:`var(--p-${p.persona})`}}>
            {PERSONAS[p.persona].glyph} {PERSONAS[p.persona].name}
          </span>
          <span>{p.claim}</span>
        </div>
      ))}
    </div>
  );
}

/* ── Sources (footnoted) ──────────────────────────────────────────── */
function Sources({ items }) {
  return (
    <div className="sources">
      <div className="sources__head">📖 LÄHTEET</div>
      {items.map((s,i) => (
        <div key={i} className="src">
          <span className="num">[{i+1}]</span>
          <a href={s.url}>{s.title}</a>
          <span className="date">{s.date}</span>
        </div>
      ))}
    </div>
  );
}

/* ── Follow-ups ───────────────────────────────────────────────────── */
function FollowUps({ items }) {
  return (
    <div>
      <div className="sources__head" style={{marginBottom:8}}>💡 VOISIT KYSYÄ MYÖS</div>
      <div className="followups">
        {items.map((q,i) => (
          <div key={i} className="chip"><span className="q">›</span>{q}</div>
        ))}
      </div>
    </div>
  );
}

/* ── Activity panel (right side) ──────────────────────────────────── */
function ActivityPanel({ onClose }) {
  return (
    <aside className="panel">
      <div className="panel__head">
        <span>🔍</span>
        <b>AGENTTIEN TOIMINTALOKI</b>
        <span className="x" onClick={onClose}>✕</span>
      </div>
      <div className="panel__tabs">
        <span className="tab is-active">Yhteenveto</span>
        <span className="tab">Agentit <span className="n">2</span></span>
        <span className="tab">Työkalut <span className="n">5</span></span>
        <span className="tab">Konfliktit <span className="n">1</span></span>
      </div>
      <div className="panel__body">
        <div className="metrics">
          <div className="metric"><div className="lab">DURATION</div><div className="v num">21.4s</div><div className="sub">routing 0.4s · fanout 12.3s · LEAD 5.8s</div></div>
          <div className="metric"><div className="lab">SUBAGENTIT</div><div className="v num">2</div><div className="sub">QUANT · RESEARCH</div></div>
          <div className="metric"><div className="lab">TYÖKALUKUTSUT</div><div className="v num">5</div><div className="sub">Inderes MCP · 0 fallback</div></div>
          <div className="metric"><div className="lab">ERRORS</div><div className="v num ok">0</div><div className="sub">kaikki onnistuivat</div></div>
        </div>

        <div className="stages">
          <div className="stage"><span className="nm">routing</span>
            <div className="bar"><i style={{left:'0%', width:'2%', background:'var(--p-lead)'}}/></div>
            <span className="v">0.4s</span>
          </div>
          <div className="stage"><span className="nm">QUANT</span>
            <div className="bar">
              <i style={{left:'2%', width:'57%', background:'var(--p-quant)'}}/>
            </div>
            <span className="v">12.3s</span>
          </div>
          <div className="stage"><span className="nm">RESEARCH</span>
            <div className="bar">
              <i style={{left:'2%', width:'56%', background:'var(--p-research)'}}/>
            </div>
            <span className="v">12.0s</span>
          </div>
          <div className="stage"><span className="nm">conflicts</span>
            <div className="bar"><i style={{left:'59%', width:'11%', background:'var(--ink-2)'}}/></div>
            <span className="v">2.4s</span>
          </div>
          <div className="stage"><span className="nm">LEAD</span>
            <div className="bar"><i style={{left:'70%', width:'27%', background:'var(--p-lead)'}}/></div>
            <span className="v">5.8s</span>
          </div>
        </div>

        <AgentCard
          persona="quant"
          duration="12.3s"
          calls={2}
          think="Analysoin Puuilon liikevaihdon ja kannattavuuden kehitystä vuosilta 2021–2025. Käytän Pythonia laskemaan liikevaihdon kasvun suhteessa myymälämäärän kasvuun…"
          tools={[
            { name:'search-companies', args:'{"query":"Puuilo"}', items:1, names:['Puuilo'] },
            { name:'get-fundamentals', args:'{"fields":["revenue","ebitPercent"], "startYear":2021, "companyIds":["COMPANY:335"]}', items:5, names:['2021–2025 quarters'] },
          ]}
          extra="Python eval: revenue per new store ≈ 11.3M€ · EBIT% trend [16.5, 15.9, 15.6, 17.0, 17.0]"
        />

        <AgentCard
          persona="research"
          duration="12.0s"
          calls={4}
          think="Analysoin Puuilon viimeisimmän tilinpäätöksen (FY2025) perusteella myymäläverkoston kasvua ja kannattavuutta…"
          tools={[
            { name:'search-companies', args:'{"query":"Puuilo"}', items:1, names:['Puuilo'] },
            { name:'list-reports', args:'{"companyId":"COMPANY:335", "limit":10}', items:10, names:['Tilinpäätös 2025','Q3 2025',' …'] },
            { name:'get-report-content', args:'{"reportId":"R:55821"}', items:1, names:['Tilinpäätöstiedote 2025'] },
            { name:'get-thread-summary', args:'{"threadId":"19301"}', items:1, names:['Puuilo-keskustelu'] },
          ]}
        />
      </div>
    </aside>
  );
}

function AgentCard({ persona, duration, calls, think, tools, extra }) {
  const p = PERSONAS[persona];
  return (
    <div className={`agcard ${persona}`}>
      <div className="agcard__head">
        <span className="glyph" style={{color:`var(--p-${persona})`}}>{p.glyph}</span>
        <span className="nm" style={{color:`var(--p-${persona})`}}>{p.name}</span>
        <span className="role">{p.role}</span>
        <span className="meta">
          <span className="ok">✓ valmis</span>
          <span>{duration}</span>
          <span>{calls} kutsua</span>
        </span>
      </div>
      <div className="agcard__body">
        <div className="think"><b style={{color:'var(--ink-1)', fontStyle:'normal'}}>Ajatus:</b> {think}</div>
        {extra && <div style={{color:'var(--ink-2)', fontSize:11}}>{extra}</div>}
      </div>
      <div className="agcard__tools">
        <div className="toolhead">▾ TYÖKALUKUTSUT <span className="n">({tools.length})</span></div>
        <ol>
          {tools.map((t,i) => (
            <li key={i}>
              <span className="tool" style={{color:`var(--p-${persona})`}}>{t.name}</span>
              <span className="args"> {t.args}</span>
              <div className="ret">→ {t.items} item{t.items!==1?'s':''} · {t.names.slice(0,3).join(', ')}{t.names.length>3?'…':''}</div>
            </li>
          ))}
        </ol>
      </div>
    </div>
  );
}

/* expose globally */
Object.assign(window, {
  PERSONAS, Topbar, Sidebar, Hero, ChatInput, QueryBubble,
  LiveStatus, TimelineStrip, Perustelut, PaattelyA, PaattelyB,
  ConflictCallout, Sources, FollowUps, ActivityPanel, AgentCard,
});

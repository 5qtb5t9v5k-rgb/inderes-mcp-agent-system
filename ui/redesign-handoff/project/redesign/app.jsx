/* Wire everything into the design canvas. */

const e = React.createElement;

function App() {
  return (
    <DesignCanvas
      title="Inderes Agent Desk · Redesign"
      subtitle="Bloomberg/IDE-henkinen terminal-DNA · Streamlit-toteutuskelpoinen · 7 ruutua"
    >
      <DCSection id="flow" title="Flow — empty → mid-run → result">
        <DCArtboard id="01" label="01 · Empty state" width={1280} height={820}>
          <ABEmpty/>
        </DCArtboard>
        <DCArtboard id="02" label="02 · Mid-run · live status" width={1280} height={820}>
          <ABMidRun/>
        </DCArtboard>
        <DCArtboard id="03" label="03 · Result — log kollapsoituneena" width={1280} height={1280}>
          <ABResult/>
        </DCArtboard>
      </DCSection>

      <DCSection id="log" title="§6.1 — Aktiviteettilokin paikka — A vs B">
        <DCArtboard id="04" label="A · Side panel (Claude.ai-tyyli)" width={1660} height={900}>
          <ABResultPanel/>
        </DCArtboard>
        <DCArtboard id="05" label="B · Inline expander, paloiteltu" width={1280} height={1100}>
          <ABResultInline/>
        </DCArtboard>
      </DCSection>

      <DCSection id="paattely" title="§5 — 🧠 Päättely · Option A vs B vertailu">
        <DCArtboard id="06" label="06 · A: vapaa proosa  vs  B: strukturoidut slotit" width={1400} height={760}>
          <ABPaattelyCompare/>
        </DCArtboard>
      </DCSection>

      <DCSection id="conflict" title="§6.4 — 🔀 Conflict surfacing (vain kun resolution on aidosti epävarma)">
        <DCArtboard id="07" label="07 · Subagentit erimieltä — oma callout" width={1280} height={900}>
          <ABConflict/>
        </DCArtboard>
      </DCSection>
    </DesignCanvas>
  );
}

ReactDOM.createRoot(document.getElementById('root')).render(<App/>);

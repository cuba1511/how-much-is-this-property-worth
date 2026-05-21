/* report-tweaks-v1.jsx — Copy tweaks for the Dashboard report */

const TWEAK_DEFAULTS = /*EDITMODE-BEGIN*/{
  "eyebrow": "— Reporte Inversor · Q2 · 2026",
  "title": "Cuánto ha ganado y <em>cómo salir</em> al mercado.",
  "lede": "Este reporte traduce la revalorización de tu propiedad en un rango de salida realista y tres escenarios comerciales. Al final, te proponemos los próximos pasos para capturar la plusvalía y, si quieres, reinvertirla en tu siguiente operación con Prop Hero.",
  "cta-title": "Vendamos al precio justo y <em>reinvirtamos</em> juntos.",
  "cta-body": "Tenemos tu rango, tus comparables y tres escenarios sobre la mesa. En 30 minutos te explicamos cuál encaja con tu situación fiscal y de tiempo — y si quieres, te enseñamos las próximas oportunidades que estamos cerrando para reinvertir la plusvalía."
}/*EDITMODE-END*/;

function applyTweak(key, value) {
  document.querySelectorAll(`[data-tweak="${key}"]`).forEach(el => {
    el.innerHTML = value;
  });
}

// Multi-line textarea tweak, styled to match the panel's other fields.
function TweakTextarea({ label, value, rows = 4, hint, onChange }) {
  return (
    <div className="twk-row">
      <div className="twk-lbl">
        <span>{label}</span>
        {hint && <span className="twk-val" style={{ fontSize: 10 }}>{hint}</span>}
      </div>
      <textarea
        className="twk-field"
        style={{
          height: 'auto',
          minHeight: rows * 16 + 8,
          padding: '6px 8px',
          fontFamily: 'inherit',
          lineHeight: 1.35,
          resize: 'vertical'
        }}
        rows={rows}
        value={value}
        onChange={(e) => onChange(e.target.value)}
      />
    </div>
  );
}

function App() {
  const [t, setTweak] = useTweaks(TWEAK_DEFAULTS);

  React.useEffect(() => {
    Object.entries(t).forEach(([k, v]) => applyTweak(k, v));
  }, [t]);

  return (
    <TweaksPanel title="Tweaks · Copy">
      <TweakSection label="Encabezado" />
      <TweakTextarea
        label="Eyebrow"
        value={t.eyebrow}
        rows={1}
        onChange={v => setTweak('eyebrow', v)}
      />
      <TweakTextarea
        label="Título principal"
        value={t.title}
        rows={2}
        hint="<em> = resalta"
        onChange={v => setTweak('title', v)}
      />
      <TweakTextarea
        label="Lede / intro"
        value={t.lede}
        rows={5}
        onChange={v => setTweak('lede', v)}
      />

      <TweakSection label="Cierre · CTA" />
      <TweakTextarea
        label="Título CTA"
        value={t['cta-title']}
        rows={2}
        hint="<em> = resalta"
        onChange={v => setTweak('cta-title', v)}
      />
      <TweakTextarea
        label="Cuerpo CTA"
        value={t['cta-body']}
        rows={5}
        onChange={v => setTweak('cta-body', v)}
      />
    </TweaksPanel>
  );
}

const root = ReactDOM.createRoot(document.getElementById('tweaks-root'));
root.render(<App />);

/* report-tweaks-v2.jsx — Copy tweaks for the Editorial report */

const TWEAK_DEFAULTS = /*EDITMODE-BEGIN*/{
  "eyebrow": "— Capítulo 00 · Tu salida al mercado",
  "title": "Tu propiedad <em>ha&nbsp;ganado</em> peso en el mercado.",
  "lede": "Treinta y ocho meses después de la compra, los datos dicen una cosa concreta: tu piso de Zaragoza vale entre <b>146.765&nbsp;€</b> y <b>161.178&nbsp;€</b>. Este reporte te enseña cuánto has ganado, qué está pagando el mercado y qué precio recomendamos para salir — y reinvertir.",
  "cta-title": "Salimos a mercado al <em>precio justo</em>, y reinvertimos juntos.",
  "cta-body": "Tienes el rango, los comparables y tres escenarios sobre la mesa. En una llamada de 30 minutos cerramos el precio de salida y, si quieres, te enseñamos qué operaciones estamos comprando ahora mismo para reinvertir la plusvalía que acabas de capturar."
}/*EDITMODE-END*/;

function applyTweak(key, value) {
  document.querySelectorAll(`[data-tweak="${key}"]`).forEach(el => {
    el.innerHTML = value;
  });
}

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
      <TweakSection label="Portada" />
      <TweakTextarea label="Eyebrow" value={t.eyebrow} rows={1}
        onChange={v => setTweak('eyebrow', v)} />
      <TweakTextarea label="Título principal" value={t.title} rows={3} hint="<em> = resalta"
        onChange={v => setTweak('title', v)} />
      <TweakTextarea label="Lede / intro" value={t.lede} rows={5} hint="<b> = negrita"
        onChange={v => setTweak('lede', v)} />

      <TweakSection label="Cierre · CTA" />
      <TweakTextarea label="Título CTA" value={t['cta-title']} rows={3} hint="<em> = resalta"
        onChange={v => setTweak('cta-title', v)} />
      <TweakTextarea label="Cuerpo CTA" value={t['cta-body']} rows={5}
        onChange={v => setTweak('cta-body', v)} />
    </TweaksPanel>
  );
}

const root = ReactDOM.createRoot(document.getElementById('tweaks-root'));
root.render(<App />);

# -*- coding: utf-8 -*-
"""
Check diário de criativos (Meta Ads) — Bruno Corano · Renda em Dólar.

Gera o HTML "O que fazer hoje" (modelo do check Maíra Cardi, adaptado ao funil
VSL sem MQL: o sinal intermediário é o checkout iniciado) a partir das MESMAS
regras de atribuição da dashboard (build.process). Somente leitura das planilhas.

    python relatorios/check_diario.py --out-dir <pasta> [--data AAAA-MM-DD]
        [--meta-file meta.csv --sales-file sales.csv]

--data = último dia com dados considerado (padrão: ontem, horário de Brasília).
Depois converta o HTML em PDF com relatorios/html2pdf.js.
"""
from __future__ import annotations

import argparse
import html
import os
import re
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "build"))
import build  # noqa: E402  (engine da dashboard: leitura + atribuição)
import config as cfg  # noqa: E402

BRT = timezone(timedelta(hours=-3))
TAX = cfg.TAX_FACTOR
CAC_META = cfg.CAC_TARGET            # R$ 162
ROAS_META = cfg.ROAS_TARGET          # 2,0

# Regras de ação (aprovadas pelo gestor em 18/11/2026)
MIN_GASTO_JULGAR = 650.0             # gasto 30d mínimo para julgar o CAC
DESLIGAR_CAC = 2 * CAC_META          # R$ 324
DIMINUIR_CAC = 1.5 * CAC_META        # R$ 243
SEM_VENDA_7D = 400.0                 # R$ gastos em 7 dias sem venda -> desligar
AUMENTAR_VENDAS = 2
ATIVO_MIN_DIA = 5.0                  # menos que isso por dia (3 dias) = parado
FONTE_GRANDE = 0.30                  # >=30% do gasto 14d: corte em 2 etapas


# --------------------------------------------------------------------------- #
def ckey(ad: str) -> str:
    """Agrupa variações do mesmo criativo (cópias, AD_RD x AD_[RD], VÍDEO x VIDEO)."""
    n = build.norm(ad)
    n = re.sub(r"(\s*[—–-]\s*copia(\s*\d+)?)+$", "", n)
    n = n.replace("[", "").replace("]", "")
    n = re.sub(r"[_\s]+", "_", n).strip("_")
    return n


def clean_name(ad: str) -> str:
    return re.sub(r"(\s*[—–-]\s*C[óo]pia(\s*\d+)?)+$", "", ad.strip(), flags=re.I)


def brl(v, dec=0):
    if v is None:
        return "—"
    s = f"{v:,.{dec}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return "R$ " + s


def brl_k(v):
    if v >= 1000:
        return "R$ " + f"{v/1000:,.1f}".replace(".", ",") + " mil"
    return brl(v)


def pct(v, dec=0):
    return (f"{v*100:.{dec}f}".replace(".", ",") + "%") if v is not None else "—"


def cls_cost(v, meta):
    if v is None:
        return ""
    return "ok" if v <= meta else ("warn" if v <= 2 * meta else "bad")


def cls_roas(v):
    if v is None:
        return ""
    return "ok" if v >= ROAS_META else ("warn" if v >= 1 else "bad")


def esc(s):
    return html.escape(str(s))


# --------------------------------------------------------------------------- #
def compute(data, D: date):
    d = lambda n: (D - timedelta(days=n)).isoformat()   # noqa: E731
    Ds = D.isoformat()
    win = {"3": d(2), "7": d(6), "14": d(13), "30": d(29), "p7": d(13)}
    meta = [m for m in data["meta"] if m["d"] and m["d"] <= Ds]
    sales = [s for s in data["sales"] if s["d"] and s["d"] <= Ds and s["meta"]]

    def tot(lo, hi=Ds):
        sp = sum(m["sp"] for m in meta if lo <= m["d"] <= hi) * TAX
        ck = sum(m["ck"] for m in meta if lo <= m["d"] <= hi)
        v = sum(s["main"] for s in sales if lo <= s["d"] <= hi)
        f = sum(s["val"] for s in sales if lo <= s["d"] <= hi)
        return dict(sp=sp, ck=ck, v=v, f=f, cac=sp / v if v else None,
                    cpc=sp / ck if ck else None, roas=f / sp if sp else None)

    # meta de custo por checkout = CAC alvo x conversão histórica checkout->venda
    hist = tot("0000-00-00")
    conv_hist = hist["v"] / hist["ck"] if hist["ck"] else 0
    ck_meta = round(CAC_META * conv_hist) if conv_hist else None

    T14, T3, T7 = tot(win["14"]), tot(win["3"]), tot(win["7"])
    Tp7 = tot(win["p7"], d(7))
    T30 = tot(win["30"])

    # ---- por criativo
    C = defaultdict(lambda: defaultdict(float))
    names = defaultdict(lambda: defaultdict(float))
    days = defaultdict(set)
    for m in meta:
        k = ckey(m["ad"])
        # nome exibido = versão com mais gasto nos últimos 3 dias (a que está rodando)
        names[k][clean_name(m["ad"])] += m["sp"] if m["d"] >= win["3"] else m["sp"] * 1e-3
        c = C[k]
        sp = m["sp"] * TAX
        for w in ("3", "7", "14", "30"):
            if m["d"] >= win[w]:
                c["sp" + w] += sp
                c["ck" + w] += m["ck"]
        if m["sp"] > 0:
            days[k].add(m["d"])
            c["first"] = min(c.get("first") or "9999", m["d"]) if c.get("first") else m["d"]
            c["last"] = max(c.get("last") or "", m["d"])
    for s in sales:
        k = ckey(s["ad"])
        c = C[k]
        if not names[k]:
            names[k][clean_name(s["ad"])] += 0
        for w in ("7", "30"):
            if s["d"] >= win[w]:
                c["v" + w] += s["main"]
                c["f" + w] += s["val"]

    sp14_tot = sum(c["sp14"] for c in C.values()) or 1
    rows = []
    for k, c in C.items():
        # Só criativos com gasto no Meta em 30 dias. Vendas sem linha do Meta
        # (UTM quebrada como "{{ad.name}}", ou nome antigo) não viram linha.
        if c["sp30"] <= 0:
            continue
        nm = max(names[k].items(), key=lambda x: x[1])[0] if names[k] else k
        sp30, v30 = c["sp30"], c["v30"]
        r = dict(k=k, name=nm, sp14=c["sp14"], ck14=c["ck14"], sp30=sp30, v30=v30, f30=c["f30"],
                 sp7=c["sp7"], v7=c["v7"], sp3=c["sp3"],
                 cpc14=c["sp14"] / c["ck14"] if c["ck14"] else None,
                 cac30=sp30 / v30 if v30 else None, roas30=c["f30"] / sp30 if sp30 else None,
                 active=c["sp3"] / 3 >= ATIVO_MIN_DIA, share=c["sp14"] / sp14_tot,
                 first=c.get("first"), last=c.get("last"),
                 ndays=len([x for x in days[k] if x >= win["30"]]))
        r["daily3"] = c["sp3"] / 3
        rows.append(r)

    groups = {"cortar": [], "diminuir": [], "aumentar": [], "olho": []}
    parados = []
    for r in sorted(rows, key=lambda x: -x["sp14"]):
        cac, sp30 = r["cac30"], r["sp30"]
        if not r["active"]:
            if r["v30"] >= AUMENTAR_VENDAS and cac is not None and cac <= CAC_META:
                bud = r["sp30"] / max(r["ndays"], 1)
                r.update(tag="RELIGAR", tcls="up",
                         why=f"Vende dentro da meta. Parado desde {fmt_d(r['last'])}; voltar com cerca de {brl(bud)}/dia.",
                         delta=bud)
                groups["aumentar"].append(r)
            elif r["sp14"] > 0:
                parados.append(r)
            continue
        judged = sp30 >= MIN_GASTO_JULGAR
        no_sale_7 = r["sp7"] >= SEM_VENDA_7D and r["v7"] == 0
        if (judged and (cac is None or cac > DESLIGAR_CAC)) or no_sale_7:
            if no_sale_7 and not (judged and (cac is None or cac > DESLIGAR_CAC)):
                why = f"{brl(r['sp7'])} gastos nos últimos 7 dias sem nenhuma venda."
            elif cac is None:
                why = f"{brl(sp30)} gastos em 30 dias sem venda."
            else:
                why = f"CAC de {brl(cac)}, acima de 2x a meta ({brl(DESLIGAR_CAC)})."
            if r["share"] >= FONTE_GRANDE:
                r.update(tag="CORTAR 50%", tcls="cut",
                         why=f"Maior fonte de gasto ({pct(r['share'])}): metade hoje, desliga em 3 dias se não melhorar. " + why,
                         delta=-0.5 * r["daily3"])
            else:
                r.update(tag="DESLIGAR", tcls="cut", why=why, delta=-r["daily3"])
            groups["cortar"].append(r)
        elif judged and cac is not None and cac > DIMINUIR_CAC:
            r.update(tag="−30%", tcls="down",
                     why=f"CAC de {brl(cac)}, entre 1,5x e 2x a meta.", delta=-0.3 * r["daily3"])
            groups["diminuir"].append(r)
        elif r["v30"] >= AUMENTAR_VENDAS and cac is not None and cac <= CAC_META:
            r.update(tag="+25%", tcls="up",
                     why="Vende dentro da meta" + (f" com ROAS {fmt_x(r['roas30'])}." if r["roas30"] else "."),
                     delta=0.25 * r["daily3"])
            groups["aumentar"].append(r)
        else:
            if r["first"] and r["first"] >= win["7"]:
                why = "Começou agora; " + ("já vendeu." if r["v30"] else "ainda sem venda.")
            elif not judged:
                why = f"Pouco gasto para concluir ({brl(sp30)} em 30 dias)."
            elif cac is not None and cac <= CAC_META:
                why = "Dentro da meta, mas com só 1 venda; esperar confirmar."
            else:
                why = "CAC entre a meta e 1,5x a meta; acompanhar."
            r.update(tag="MANTER", tcls="keep", why=why, delta=0)
            groups["olho"].append(r)
    groups["aumentar"].sort(key=lambda x: (x["cac30"] or 9e9))
    olho_total = len(groups["olho"])
    groups["olho"] = groups["olho"][:8]

    # ---- alertas e destaques
    lvl = cls_cost(T14["cac"], CAC_META) if T14["cac"] else "bad"
    trend = None
    if T14["cac"] and T3["cac"]:
        trend = "piorando" if T3["cac"] > T14["cac"] * 1.1 else ("melhorando" if T3["cac"] < T14["cac"] * 0.9 else "estável")
    elif T3["v"] == 0:
        trend = "piorando"
    alert = {
        "ok": "🟢 CAC dentro da meta",
        "warn": "🟠 CAC acima da meta",
        "bad": "🔴 CAC acima de 2x a meta",
    }[lvl or "bad"] + (f" e {trend}." if trend else ".")
    if T14["roas"] is not None:
        alert += f" ROAS de {fmt_x(T14['roas'])} em 14 dias (meta {fmt_x(ROAS_META)})."

    pins = []
    if Tp7["sp"]:
        dsp = T7["sp"] / Tp7["sp"] - 1
        dv = (T7["v"] / Tp7["v"] - 1) if Tp7["v"] else None
        s = (f"<b>A semana gastou {pct(abs(dsp))} {'a mais' if dsp >= 0 else 'a menos'} que a anterior "
             f"e as vendas {('subiram ' if dv >= 0 else 'caíram ') + pct(abs(dv)) if dv is not None else 'mudaram'} "
             f"({T7['v']} contra {Tp7['v']}).</b> ")
        if dv is not None and dsp > 0.1 and dv < dsp - 0.1:
            s += "O dinheiro extra não virou venda na mesma proporção."
        elif dv is not None and dv > dsp + 0.1:
            s += "A eficiência melhorou: mais vendas por real investido."
        else:
            s += "Vendas acompanharam o investimento."
        pins.append(s)
    conv30 = T30["v"] / T30["ck"] if T30["ck"] else None
    if conv30 is not None and conv_hist:
        s = f"<b>{pct(conv30, 1)} dos checkouts viram venda (30 dias); o histórico é {pct(conv_hist, 1)}.</b> "
        s += ("Vale conferir a página de checkout e as formas de pagamento." if conv30 < conv_hist * 0.85
              else "A conversão do checkout está dentro do normal; o gargalo, se houver, está antes dele.")
        pins.append(s)
    dentro = sorted([r for r in rows if r["active"] and r["v30"] >= 1 and r["cac30"] and r["cac30"] <= CAC_META],
                    key=lambda x: x["cac30"])
    if dentro:
        pins.append(f"<b>{len(dentro)} criativo(s) ativo(s) dentro da meta de CAC ({brl(CAC_META)}).</b> "
                    f"Melhor: {esc(dentro[0]['name'])} ({brl(dentro[0]['cac30'])}).")
    else:
        best = sorted([r for r in rows if r["active"] and r["cac30"]], key=lambda x: x["cac30"])[:2]
        rng = " e ".join(brl(r["cac30"]) for r in best)
        pins.append(f"<b>Nenhum criativo ativo está dentro da meta de CAC ({brl(CAC_META)}).</b> "
                    + (f"Os melhores ficam em {rng}. " if best else "") + "Faltam criativos novos.")

    econ = -sum(r.get("delta", 0) for g in groups.values() for r in g)
    return dict(D=D, T14=T14, T3=T3, T7=T7, Tp7=Tp7, ck_meta=ck_meta, conv_hist=conv_hist,
                alert=alert, lvl=lvl, pins=pins, groups=groups, olho_total=olho_total,
                parados=sorted(parados, key=lambda x: -x["sp14"]), econ=econ)


def fmt_d(iso):
    return f"{iso[8:10]}/{iso[5:7]}" if iso else "—"


def fmt_x(v):
    return (f"{v:.1f}".replace(".", ",") + "x") if v is not None else "—"


# --------------------------------------------------------------------------- #
CSS = """
*{box-sizing:border-box}body{font-family:Inter,'Segoe UI',Arial,sans-serif;color:#1d1d1f;margin:0;font-size:10.5px;line-height:1.35}
.page{padding:26px 30px}
.kicker{color:#8a8a8f;letter-spacing:.12em;font-size:10px;text-transform:uppercase}
h1{font-size:22px;margin:2px 0 10px;font-weight:700}
.alert{border-left:4px solid #c62828;background:#fdecec;padding:8px 12px;font-weight:700;font-size:12px;margin-bottom:10px}
.alert.warn{border-color:#e07b00;background:#fff3e0}.alert.ok{border-color:#2e7d32;background:#e8f5e9}
.cards{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-bottom:10px}
.card{border:1px solid #e3e3e6;border-radius:6px;padding:8px 10px}
.card .l{color:#6e6e73;font-size:10px}.card .v{font-size:19px;font-weight:700;margin:2px 0}.card .a{color:#6e6e73;font-size:9.5px}
.ok{color:#2e7d32}.warn{color:#d97706}.bad{color:#c62828}
.pins{background:#f4f4f6;border-radius:6px;padding:8px 12px;margin-bottom:8px}.pins p{margin:3px 0}
.legend{color:#6e6e73;font-size:9.5px;margin:4px 0}
table{width:100%;border-collapse:collapse}
th{font-size:9px;color:#6e6e73;font-weight:600;text-align:right;border-bottom:1px solid #ccc;padding:3px 4px}
th.l,td.l{text-align:left}
td{padding:5px 4px;border-bottom:1px solid #ececef;vertical-align:top;text-align:right;white-space:nowrap}
td.nm{white-space:normal;text-align:left}td.nm b{font-size:10.5px;word-break:break-word}td.nm .w{color:#555;font-size:9.5px}
td.tag{width:72px;text-align:left}
.t{display:inline-block;font-size:8.5px;font-weight:700;padding:2px 5px;border-radius:3px}
.t.cut{background:#fdecec;color:#c62828}.t.down{background:#fff3e0;color:#d97706}.t.up{background:#e8f5e9;color:#2e7d32}.t.keep{background:#eceff1;color:#455a64}
tr.g td{font-weight:700;font-size:12px;padding:6px 6px;text-align:left}
tr.g1 td{background:#fdecec;color:#b71c1c}tr.g2 td{background:#fff3e0;color:#b45309}tr.g3 td{background:#e8f5e9;color:#1b5e20}tr.g4 td{background:#eceff1;color:#37474f}
.note{color:#6e6e73;font-size:9.5px;margin:6px 0}
.box{background:#f4f4f6;border-radius:6px;padding:8px 12px;margin-top:8px}
.foot{color:#9a9aa0;font-size:8.5px;margin-top:10px;line-height:1.4}
tr{page-break-inside:avoid}
"""


def render(R) -> str:
    D = R["D"]
    hoje = D + timedelta(days=1)
    T14, T3, T7, Tp7 = R["T14"], R["T3"], R["T7"], R["Tp7"]
    ckm = R["ck_meta"]
    dv7 = (T7["ck"] / Tp7["ck"] - 1) if Tp7["ck"] else None
    st = "estável" if dv7 is None or abs(dv7) < .05 else (f"subindo {pct(dv7)}" if dv7 > 0 else f"caindo {pct(-dv7)}")
    cards = [
        ("Custo por checkout (14d)", brl(T14["cpc"]), cls_cost(T14["cpc"], ckm) if ckm else "",
         f"meta {brl(ckm)} · 3 dias: {brl(T3['cpc'])}"),
        ("Checkouts (7d)", f"{int(T7['ck'])}", "", f"semana anterior: {int(Tp7['ck'])} · {st}"),
        ("CAC (14d)", brl(T14["cac"]), cls_cost(T14["cac"], CAC_META),
         f"meta {brl(CAC_META)} · 3 dias: {brl(T3['cac'])}"),
        ("Vendas (14d)", f"{T14['v']}", "",
         f"ROAS {fmt_x(T14['roas'])} · gasto de {brl_k(T14['sp'])}"),
    ]
    h = [f"<!doctype html><html lang='pt-BR'><head><meta charset='utf-8'><style>{CSS}</style></head><body><div class='page'>"]
    h.append(f"<div class='kicker'>Bruno Corano · Renda em Dólar · Check de {hoje.strftime('%d/%m')}</div>")
    h.append("<h1>O que fazer hoje</h1>")
    h.append(f"<div class='alert {R['lvl']}'>{esc(R['alert'])}</div>")
    h.append("<div class='cards'>" + "".join(
        f"<div class='card'><div class='l'>{l}</div><div class='v {c}'>{v}</div><div class='a'>{a}</div></div>"
        for l, v, c, a in cards) + "</div>")
    h.append("<div class='pins'>" + "".join(f"<p>📌 {p}</p>" for p in R["pins"]) + "</div>")
    h.append("<div class='legend'>Cores: <b class='ok'>verde</b> dentro da meta · <b class='warn'>laranja</b> até 2x a meta · "
             "<b class='bad'>vermelho</b> acima de 2x a meta (ROAS: verde ≥ 2,0 · laranja ≥ 1,0 · vermelho &lt; 1,0)</div>")
    h.append("<table><tr><th></th><th class='l'>Criativo</th><th>Gasto 14d</th><th>Checkouts 14d</th><th>Custo/checkout</th>"
             "<th>Vendas 30d</th><th>CAC 30d</th><th>ROAS 30d</th></tr>")
    titles = [("cortar", "1. Desligar ou cortar", "g1"), ("diminuir", "2. Diminuir 30%", "g2"),
              ("aumentar", "3. Aumentar", "g3"), ("olho", "4. De olho (ainda sem conclusão)", "g4")]
    for key, title, gc in titles:
        rows = R["groups"][key]
        if not rows:
            continue
        h.append(f"<tr class='g {gc}'><td colspan='8'>{title}</td></tr>")
        for r in rows:
            h.append(
                f"<tr><td class='tag'><span class='t {r['tcls']}'>{esc(r['tag'])}</span></td>"
                f"<td class='nm'><b>{esc(r['name'])}</b><div class='w'>{esc(r['why'])}</div></td>"
                f"<td>{brl_k(r['sp14'])}</td><td>{int(r['ck14'])}</td>"
                f"<td class='{cls_cost(r['cpc14'], ckm) if ckm else ''}'><b>{brl(r['cpc14'])}</b></td>"
                f"<td>{int(r['v30'])}</td>"
                f"<td class='{cls_cost(r['cac30'], CAC_META)}'><b>{brl(r['cac30'])}</b></td>"
                f"<td class='{cls_roas(r['roas30'])}'><b>{fmt_x(r['roas30'])}</b></td></tr>")
    h.append("</table>")
    if R["olho_total"] > len(R["groups"]["olho"]):
        h.append(f"<div class='note'>+ {R['olho_total'] - len(R['groups']['olho'])} criativo(s) ativo(s) de menor gasto sem ação indicada.</div>")
    if R["parados"]:
        nm = ", ".join(esc(r["name"]) for r in R["parados"][:10])
        extra = f" e mais {len(R['parados']) - 10}" if len(R["parados"]) > 10 else ""
        h.append(f"<div class='note'>Já parados na prática (menos de R$ 5/dia nos últimos 3 dias), confirmar que estão pausados: {nm}{extra}.</div>")
    e = R["econ"]
    h.append("<div class='box'>" + (
        f"💰 <b>Com essas mudanças a conta passa a gastar cerca de {brl(abs(e))} por dia {'a menos' if e >= 0 else 'a mais'}.</b> "
        + ("Decidir hoje: baixar o investimento ou subir criativos novos parecidos com os que vendem dentro da meta."
           if e > 0 else "O aumento vai para criativos que vendem dentro da meta.")) + "</div>")
    h.append(
        f"<div class='foot'>Dados até {D.strftime('%d/%m/%Y')} (dia completo). Custos com imposto ({str(TAX).replace('.', ',')}). "
        "Venda = compra do produto principal atribuída ao Meta Ads (UTM campanha + anúncio, ou utm_source FB). "
        f"Meta de custo por checkout = CAC alvo × conversão histórica checkout→venda ({pct(R['conv_hist'], 1)}). "
        "Criativo = anúncio com o mesmo nome, somando cópias. "
        f"Desligar: CAC acima de {brl(DESLIGAR_CAC)} depois de gastar {brl(MIN_GASTO_JULGAR)} em 30d, ou {brl(SEM_VENDA_7D)} gastos sem venda em 7d "
        "(fontes com 30%+ do gasto são cortadas em 2 etapas). "
        f"Diminuir 30%: CAC entre {brl(DIMINUIR_CAC)} e {brl(DESLIGAR_CAC)}. "
        f"Aumentar 25%: 2+ vendas com CAC até {brl(CAC_META)}. Religar: parado com 2+ vendas e CAC até {brl(CAC_META)} em 30d.</div>")
    h.append("</div></body></html>")
    return "".join(h)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--data", help="último dia de dados (AAAA-MM-DD); padrão: ontem (BRT)")
    ap.add_argument("--meta-file")
    ap.add_argument("--sales-file")
    a = ap.parse_args()
    D = date.fromisoformat(a.data) if a.data else (datetime.now(BRT).date() - timedelta(days=1))
    meta_rows = build.load_rows(build.META_CSV_URL, a.meta_file)
    sales_rows = build.load_rows(build.SALES_CSV_URL, a.sales_file)
    R = compute(build.process(meta_rows, sales_rows), D)
    os.makedirs(a.out_dir, exist_ok=True)
    out = os.path.join(a.out_dir, f"check-renda-em-dolar-{(D + timedelta(days=1)).isoformat()}.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(render(R))
    print(out)


if __name__ == "__main__":
    main()

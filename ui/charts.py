"""Диаграммы Altair в одном стиле: тонкие метки, приглушённая сетка, русские числа."""
import altair as alt
import pandas as pd

from ui.common import COMP_COLOR, COMPONENTS, DIVERGING, money

# Подпись оси в млн: 12.5 → «12,5».
RU_AXIS = "replace(replace(format(datum.value, ',.1f'), regexp(',', 'g'), ' '), '.', ',')"
FONT = "Inter, -apple-system, 'Segoe UI', sans-serif"


def _style(ch, height):
    return (ch.properties(height=height)
            .configure_axis(grid=True, gridColor="#ececec", domainColor="#c9c9c9", tickColor="#c9c9c9",
                            labelColor="#5b5b5b", titleColor="#5b5b5b", labelFont=FONT, titleFont=FONT,
                            labelFontSize=12, titleFontSize=12, titleFontWeight="normal")
            .configure_legend(labelFont=FONT, titleFont=FONT, labelFontSize=12, titleFontSize=12,
                              orient="bottom", direction="horizontal", columns=3, symbolType="square", labelLimit=320)
            .configure_view(strokeWidth=0))


def stacked(long_df, y, y_order, totals, height=None, y_title=None):
    """Горизонтальная стопка платежей; итог подписан на конце бара.

    long_df: y × «платёж» × «сумма»; totals: y × «итог».
    """
    d = long_df.copy()
    d["млн"] = d["сумма"] / 1e6
    d["подпись_суммы"] = d["сумма"].map(money)
    t = totals.copy()
    t["млн"] = t["итог"] / 1e6
    t["подпись"] = t["итог"].map(lambda v: money(v, "млн") + " тг")
    xmax = max(t["млн"].max(), 0.001) * 1.22   # запас под концевую подпись — в самой шкале
    order = [lbl for _, lbl, _ in COMPONENTS]
    present = [o for o in order if o in set(d["платёж"])]
    x = alt.X("sum(млн):Q", title="млн тг", scale=alt.Scale(domain=[0, xmax], nice=False),
              axis=alt.Axis(labelExpr=RU_AXIS, tickCount=6))
    yenc = alt.Y(f"{y}:N", sort=y_order, title=y_title, axis=alt.Axis(labelLimit=260))
    bars = alt.Chart(d).mark_bar(height={"band": 0.62}, stroke="white", strokeWidth=2).encode(
        x=x, y=yenc,
        color=alt.Color("платёж:N", sort=present, title=None,
                        scale=alt.Scale(domain=present, range=[COMP_COLOR[p] for p in present])),
        order=alt.Order("порядок:Q"),
        tooltip=[alt.Tooltip(f"{y}:N", title=y_title or "сценарий"),
                 alt.Tooltip("платёж:N"), alt.Tooltip("подпись_суммы:N", title="тг")],
    )
    labels = alt.Chart(t).mark_text(align="left", dx=6, font=FONT, fontSize=12, color="#2b2b2b").encode(
        x=alt.X("млн:Q", scale=alt.Scale(domain=[0, xmax], nice=False)), y=alt.Y(f"{y}:N", sort=y_order),
        text="подпись:N")
    return _style(alt.layer(bars, labels), height or alt.Step(46))


def lines(df, x, y, color, color_domain, color_range, x_title, y_title, y_axis_expr=None,
          rule_x=None, rule_label=None, x_type="O", height=320, tooltip_fmt=None, x_sort=None):
    base = alt.Chart(df).encode(
        x=alt.X(f"{x}:{x_type}", title=x_title, axis=alt.Axis(labelAngle=0), sort=x_sort),
        y=alt.Y(f"{y}:Q", title=y_title, axis=alt.Axis(labelExpr=y_axis_expr) if y_axis_expr else alt.Axis()),
        color=alt.Color(f"{color}:N", title=None,
                        scale=alt.Scale(domain=color_domain, range=color_range), sort=color_domain),
        tooltip=[alt.Tooltip(f"{color}:N", title="маршрут"), alt.Tooltip(f"{x}:{x_type}", title=x_title),
                 alt.Tooltip(f"{tooltip_fmt or y}:N" if tooltip_fmt else f"{y}:Q", title=y_title)],
    )
    layers = [base.mark_line(strokeWidth=2, strokeCap="round", strokeJoin="round"),
              base.mark_point(filled=True, size=55, stroke="white", strokeWidth=1.5)]
    if rule_x is not None:
        r = pd.DataFrame({x: [rule_x], "t": [rule_label]})
        layers.append(alt.Chart(r).mark_rule(strokeDash=[4, 4], color="#8a8a8a").encode(x=f"{x}:{x_type}"))
        layers.append(alt.Chart(r).mark_text(align="left", dx=5, dy=-8, color="#5b5b5b", font=FONT,
                                             fontSize=12, baseline="top").encode(
            x=f"{x}:{x_type}", y=alt.value(4), text="t:N"))
    return _style(alt.layer(*layers), height)


def heatmap(df, x, y, value, label, x_title, y_title, legend_title, x_sort=None, y_sort=None, height=None):
    """Расходящаяся карта: синий — первый вариант дешевле, красный — второй."""
    lim = max(abs(df[value]).max(), 0.001)
    base = alt.Chart(df).encode(
        x=alt.X(f"{x}:O", title=x_title, sort=x_sort, axis=alt.Axis(labelAngle=0)),
        y=alt.Y(f"{y}:O", title=y_title, sort=y_sort),
    )
    cells = base.mark_rect(stroke="white", strokeWidth=2, cornerRadius=3).encode(
        color=alt.Color(f"{value}:Q", title=legend_title,
                        scale=alt.Scale(domain=[-lim, -lim / 2, 0, lim / 2, lim], range=DIVERGING, interpolate="rgb"),
                        legend=alt.Legend(orient="bottom", direction="horizontal", gradientLength=260,
                                          labelExpr=RU_AXIS)),
        tooltip=[alt.Tooltip(f"{y}:O", title=y_title), alt.Tooltip(f"{x}:O", title=x_title),
                 alt.Tooltip(f"{label}:N", title=legend_title)],
    )
    text = base.mark_text(font=FONT, fontSize=11).encode(
        text=f"{label}:N",
        color=alt.condition(f"abs(datum.{value}) > {lim * 0.55}", alt.value("white"), alt.value("#2b2b2b")),
    )
    return _style(alt.layer(cells, text), height or alt.Step(28))


def bars(df, x, y, color, color_domain, color_range, label, x_title, height=None, y_order=None):
    """Сгруппированные горизонтальные бары с подписью значения."""
    xmax = df[x].max() * 1.25
    h = height or alt.Step(22)
    enc = dict(y=alt.Y(f"{y}:N", sort=y_order, title=None, axis=alt.Axis(labelLimit=260)),
               x=alt.X(f"{x}:Q", title=x_title, scale=alt.Scale(domain=[0, xmax], nice=False),
                       axis=alt.Axis(labelExpr=RU_AXIS, tickCount=6)))
    b = alt.Chart(df).mark_bar(cornerRadiusEnd=4, height={"band": 0.7}).encode(
        **enc, yOffset=alt.YOffset(f"{color}:N", sort=color_domain),
        color=alt.Color(f"{color}:N", title=None, scale=alt.Scale(domain=color_domain, range=color_range)),
        tooltip=[alt.Tooltip(f"{y}:N"), alt.Tooltip(f"{color}:N"), alt.Tooltip(f"{label}:N", title=x_title)])
    t = alt.Chart(df).mark_text(align="left", dx=5, font=FONT, fontSize=11, color="#2b2b2b").encode(
        **enc, yOffset=alt.YOffset(f"{color}:N", sort=color_domain), text=f"{label}:N")
    return _style(alt.layer(b, t), h)

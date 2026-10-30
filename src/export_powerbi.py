"""Exporteer de analyse naar CSV-tabellen voor het Power BI-rapport.

Gebruik:  python src/export_powerbi.py
Uitvoer:  data/processed/*.csv  (komma als scheidingsteken, punt als decimaal;
          Power Query laadt ze met Culture "en-US", zie powerbi/laden.pq)
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from kalibratie import (COLOCATIE_DAGEN, DQO_INDICATIEF, HERKALIBRATIE_DAGEN,
                        KALIBRATIE_EINDE, MET_OMGEVING, ROOT, SENSOREN, fit,
                        blokdrift, kalibreer, kwaliteitsvlaggen, laad_ruwe_data,
                        maandprestaties, monte_carlo, onzekerheidsbudget,
                        prestaties, samenvatting_budget)

UIT = ROOT / "data" / "processed"
INTERVALLEN = [7, 14, 30, 60, 90]


def bouw_tabellen(df: pd.DataFrame) -> dict[str, pd.DataFrame]:
    validatie = df.index > KALIBRATIE_EINDE
    metingen, maanden, intervallen, budgetten, samenvattingen = [], [], [], [], []

    for sensor, cfg in SENSOREN.items():
        omg = MET_OMGEVING[sensor]
        statisch = kalibreer(df, sensor, omg)
        herkal = kalibreer(df, sensor, omg, HERKALIBRATIE_DAGEN)
        vlag = kwaliteitsvlaggen(df[cfg["ruw"]])
        ref = df[cfg["ref"]]

        m = pd.DataFrame({
            "tijdstip": df.index,
            "sensor": sensor,
            "referentie": ref.values,
            "ruw_signaal": df[cfg["ruw"]].values,
            "gekalibreerd_statisch": statisch.values,
            "gekalibreerd_herkalibratie": herkal.values,
            "temperatuur": df["T"].values,
            "rel_vochtigheid": df["RH"].values,
            "abs_vochtigheid": df["AH"].values,
            "vlag_ontbreekt": vlag.ontbreekt.values,
            "vlag_piek": vlag.piek.values,
            "periode": np.where(validatie, "validatie", "kalibratie"),
        })
        m["fout_herkalibratie"] = m.gekalibreerd_herkalibratie - m.referentie
        m["rel_fout_herkalibratie"] = m.fout_herkalibratie / m.referentie
        m["binnen_dqo"] = (m.rel_fout_herkalibratie.abs() <= DQO_INDICATIEF).astype("boolean")
        m.loc[m.rel_fout_herkalibratie.isna(), "binnen_dqo"] = pd.NA
        metingen.append(m)

        mp = maandprestaties(df, sensor, {"statisch": statisch,
                                          "herkalibratie": herkal})
        volledig = pd.DataFrame({
            "maand": ref.resample("MS").size().index,
            "volledigheid_referentie": ref.resample("MS").count().values
            / ref.resample("MS").size().values,
            "volledigheid_sensor": df[cfg["ruw"]].resample("MS").count().values
            / ref.resample("MS").size().values,
        })
        mp = mp.merge(volledig, on="maand")
        mp["maand"] = mp.maand.dt.date      # alleen datum, zonder tijd
        maanden.append(mp)

        for iv in [None, *INTERVALLEN]:
            reeks = statisch if iv is None else kalibreer(df, sensor, omg, iv)
            p = prestaties(ref[validatie], reeks[validatie])
            intervallen.append({"sensor": sensor,
                                "interval_dagen": 0 if iv is None else iv,
                                "interval_label": "geen (statisch)" if iv is None
                                else f"{iv} dagen", **p})

        drift = blokdrift(ref[validatie], herkal[validatie],
                          HERKALIBRATIE_DAGEN).abs().quantile(0.95)
        model = fit(df.loc[:KALIBRATIE_EINDE], cfg["ref"], cfg["ruw"], omg)
        b = onzekerheidsbudget(df, sensor, model, drift, HERKALIBRATIE_DAGEN)
        budgetten.append(b)
        mc = monte_carlo(b)
        s = samenvatting_budget(b)
        rel = m.loc[validatie, "rel_fout_herkalibratie"].dropna()
        samenvattingen.append({
            "sensor": sensor, **s,
            "mc_ondergrens_95": np.quantile(mc, 0.025),
            "mc_bovengrens_95": np.quantile(mc, 0.975),
            "empirisch_abs_fout_p95": rel.abs().quantile(0.95),
            "dqo": DQO_INDICATIEF,
        })

    sensoren = pd.DataFrame([
        {"sensor": s, "naam": c["naam"], "eenheid": c["eenheid"],
         "referentiekanaal": c["ref"], "sensorkanaal": c["ruw"],
         "grenswaarde": c["grenswaarde"], "omgevingscorrectie": MET_OMGEVING[s],
         "herkalibratie_dagen": HERKALIBRATIE_DAGEN,
         "colocatie_dagen": COLOCATIE_DAGEN}
        for s, c in SENSOREN.items()])

    return {
        "metingen": pd.concat(metingen, ignore_index=True),
        "maandkwaliteit": pd.concat(maanden, ignore_index=True),
        "kalibratie_interval": pd.DataFrame(intervallen),
        "onzekerheidsbudget": pd.concat(budgetten, ignore_index=True),
        "onzekerheid_samenvatting": pd.DataFrame(samenvattingen),
        "sensoren": sensoren,
    }


def main() -> dict[str, pd.DataFrame]:
    UIT.mkdir(parents=True, exist_ok=True)
    tabellen = bouw_tabellen(laad_ruwe_data())
    for naam, t in tabellen.items():
        t.to_csv(UIT / f"{naam}.csv", index=False, float_format="%.6g",
                 date_format="%Y-%m-%d %H:%M:%S")
        print(f"{naam:26s} {len(t):6d} rijen")
    return tabellen


if __name__ == "__main__":
    main()

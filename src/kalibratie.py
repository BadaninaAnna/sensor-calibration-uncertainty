"""Kalibratie, drift en meetonzekerheid van goedkope gassensoren.

Dataset: UCI Air Quality (De Vito et al., 2008) - uurwaarden van een
metaaloxide-sensorarray naast een gecertificeerde referentie-analysator,
maart 2004 - april 2005, Italiaanse stad.

Alle functies zijn puur (DataFrame in, DataFrame uit), zodat de notebook en
het exportscript dezelfde logica gebruiken.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw" / "AirQualityUCI.csv"

# Sensorconfiguratie: referentiekanaal, ruw sensorkanaal en eenheid.
SENSOREN = {
    "CO": {"ref": "CO(GT)", "ruw": "PT08.S1(CO)", "eenheid": "mg/m³",
           "naam": "Koolmonoxide", "grenswaarde": 10.0},
    "NO2": {"ref": "NO2(GT)", "ruw": "PT08.S4(NO2)", "eenheid": "µg/m³",
            "naam": "Stikstofdioxide", "grenswaarde": 200.0},
}

# Data Quality Objective voor indicatieve metingen, Richtlijn 2008/50/EG,
# bijlage I: relatieve uitgebreide onzekerheid <= 25 % (CO en NO2).
DQO_INDICATIEF = 0.25

# Aanname (type B): uitgebreide onzekerheid van de referentiemethode
# (EN 14626 voor CO, EN 14211 voor NO2) = 15 % bij k = 2.
U_REF_REL = 0.15

KALIBRATIE_EINDE = pd.Timestamp("2004-04-30 23:00")

# Gekozen configuratie per sensor (zie notebook, hoofdstuk 5): CO heeft geen
# baat bij een omgevingscorrectie (overfitting op voorjaarscondities), NO2 wel
# (sterke kruisgevoeligheid voor temperatuur en vocht).
MET_OMGEVING = {"CO": False, "NO2": True}
HERKALIBRATIE_DAGEN = 14
COLOCATIE_DAGEN = 28


# --------------------------------------------------------------------------
# 1. Inlezen en opschonen
# --------------------------------------------------------------------------
def laad_ruwe_data(pad: Path = RAW) -> pd.DataFrame:
    df = pd.read_csv(pad, sep=";", decimal=",")
    df = df.dropna(how="all", axis=1).dropna(how="all")
    df["tijdstip"] = pd.to_datetime(df["Date"] + " " + df["Time"],
                                    format="%d/%m/%Y %H.%M.%S")
    df = df.drop(columns=["Date", "Time"]).set_index("tijdstip").sort_index()
    # -200 is de codering voor een ontbrekende waarde in deze dataset.
    return df.replace(-200, np.nan)


def kwaliteitsvlaggen(reeks: pd.Series, venster: int = 24,
                      z_grens: float = 6.0, vast_uren: int = 4) -> pd.DataFrame:
    """Markeer ontbrekende, vastgelopen en piekwaarden in een uurreeks."""
    ontbreekt = reeks.isna()
    # Vastgelopen: dezelfde waarde >= vast_uren opeenvolgende uren.
    groep = (reeks != reeks.shift()).cumsum()
    lengte = reeks.groupby(groep).transform("size")
    vast = (lengte >= vast_uren) & ~ontbreekt
    # Piek: robuuste z-score van de afwijking t.o.v. de lopende mediaan.
    mediaan = reeks.rolling(venster, center=True, min_periods=6).median()
    afw = reeks - mediaan
    mad = afw.abs().rolling(venster * 7, center=True, min_periods=24).median()
    z = 0.6745 * afw / mad.replace(0, np.nan)
    piek = (z.abs() > z_grens) & ~ontbreekt
    return pd.DataFrame({"ontbreekt": ontbreekt, "vastgelopen": vast,
                         "piek": piek})


# --------------------------------------------------------------------------
# 2. Kalibratiemodellen
# --------------------------------------------------------------------------
@dataclass
class Model:
    """Log-lineair model: ln(ref) = X @ beta, met X = [1, ln(ruw), (T, AH)]."""
    beta: np.ndarray
    cov: np.ndarray
    s_res: float          # standaardafwijking residuen in ln-ruimte
    n: int
    met_omgeving: bool

    def ontwerp(self, df: pd.DataFrame, ruw: str) -> np.ndarray:
        return ontwerpmatrix(df, ruw, self.met_omgeving)

    def voorspel(self, df: pd.DataFrame, ruw: str) -> pd.Series:
        X = self.ontwerp(df, ruw)
        # Smearing-correctie (Duan) zodat de terugtransformatie onvertekend is.
        return pd.Series(np.exp(X @ self.beta + self.s_res**2 / 2), index=df.index)


def ontwerpmatrix(df: pd.DataFrame, ruw: str, met_omgeving: bool) -> np.ndarray:
    kolommen = [np.ones(len(df)), np.log(df[ruw].to_numpy())]
    if met_omgeving:
        kolommen += [df["T"].to_numpy(), df["AH"].to_numpy()]
    return np.column_stack(kolommen)


def fit(df: pd.DataFrame, ref: str, ruw: str, met_omgeving: bool) -> Model:
    d = df.dropna(subset=[ref, ruw, "T", "AH"])
    d = d[d[ref] > 0]
    X = ontwerpmatrix(d, ruw, met_omgeving)
    y = np.log(d[ref].to_numpy())
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    res = y - X @ beta
    dof = len(y) - X.shape[1]
    s2 = res @ res / dof
    cov = s2 * np.linalg.inv(X.T @ X)
    return Model(beta, cov, float(np.sqrt(s2)), len(y), met_omgeving)


def kalibreer(df: pd.DataFrame, sensor: str, met_omgeving: bool = True,
              herkalibratie_dagen: int | None = None,
              colocatie_dagen: int = COLOCATIE_DAGEN) -> pd.Series:
    """Gekalibreerde reeks.

    herkalibratie_dagen=None: één kalibratie op de eerste periode (statisch).
    Anders: elke N dagen opnieuw fitten op de laatste `colocatie_dagen` dagen
    met referentiedata, en toepassen op de volgende N dagen.
    """
    cfg = SENSOREN[sensor]
    bruikbaar = df.dropna(subset=[cfg["ruw"], "T", "AH"])
    if herkalibratie_dagen is None:
        model = fit(df.loc[:KALIBRATIE_EINDE], cfg["ref"], cfg["ruw"], met_omgeving)
        return model.voorspel(bruikbaar, cfg["ruw"]).reindex(df.index)

    uit = pd.Series(np.nan, index=df.index)
    start = KALIBRATIE_EINDE + pd.Timedelta(hours=1)
    model = fit(df.loc[:KALIBRATIE_EINDE], cfg["ref"], cfg["ruw"], met_omgeving)
    uit.loc[:KALIBRATIE_EINDE] = model.voorspel(
        bruikbaar.loc[:KALIBRATIE_EINDE], cfg["ruw"])
    stap = pd.Timedelta(days=herkalibratie_dagen)
    while start <= df.index.max():
        einde = start + stap - pd.Timedelta(hours=1)
        venster = df.loc[start - pd.Timedelta(days=colocatie_dagen):start - pd.Timedelta(hours=1)]
        if venster[cfg["ref"]].notna().sum() >= 48:   # min. 2 dagen referentie
            model = fit(venster, cfg["ref"], cfg["ruw"], met_omgeving)
        deel = bruikbaar.loc[start:einde]
        if len(deel):
            uit.loc[deel.index] = model.voorspel(deel, cfg["ruw"])
        start = einde + pd.Timedelta(hours=1)
    return uit


# --------------------------------------------------------------------------
# 3. Prestatie-indicatoren
# --------------------------------------------------------------------------
def prestaties(ref: pd.Series, gekal: pd.Series) -> dict:
    d = pd.concat({"ref": ref, "gek": gekal}, axis=1).dropna()
    if len(d) < 2:
        return {"n": len(d), "bias": np.nan, "rmse": np.nan, "r2": np.nan,
                "binnen_dqo": np.nan}
    fout = d.gek - d.ref
    ss_tot = ((d.ref - d.ref.mean()) ** 2).sum()
    rel = (fout / d.ref).abs()
    return {
        "n": len(d),
        "bias": fout.mean(),
        "rmse": np.sqrt((fout ** 2).mean()),
        "r2": 1 - (fout ** 2).sum() / ss_tot,
        "binnen_dqo": (rel <= DQO_INDICATIEF).mean(),
    }


def maandprestaties(df: pd.DataFrame, sensor: str, varianten: dict) -> pd.DataFrame:
    ref = df[SENSOREN[sensor]["ref"]]
    rijen = []
    for naam, reeks in varianten.items():
        for maand, idx in ref.groupby(ref.index.to_period("M")).groups.items():
            r = prestaties(ref.loc[idx], reeks.loc[idx])
            rijen.append({"sensor": sensor, "variant": naam,
                          "maand": maand.to_timestamp(), **r})
    return pd.DataFrame(rijen)


def relatieve_fout(ref: pd.Series, gekal: pd.Series) -> pd.Series:
    d = pd.concat({"ref": ref, "gek": gekal}, axis=1).dropna()
    return (d.gek - d.ref) / d.ref


def blokdrift(ref: pd.Series, gekal: pd.Series, blok_dagen: int) -> pd.Series:
    """Relatieve bias per blok van `blok_dagen` dagen (mediaan, robuust)."""
    rel = relatieve_fout(ref, gekal)
    return rel.groupby(pd.Grouper(freq=f"{blok_dagen}D")).median().dropna()


# --------------------------------------------------------------------------
# 4. Meetonzekerheid (GUM, JCGM 100:2008) en Monte Carlo (JCGM 101:2008)
# --------------------------------------------------------------------------
def onzekerheidsbudget(df: pd.DataFrame, sensor: str, model: Model,
                       drift_rel: float, interval_dagen: int) -> pd.DataFrame:
    """Relatief onzekerheidsbudget van één gekalibreerde uurwaarde.

    Werkt in ln-ruimte: een standaardonzekerheid u in ln(c) is in goede
    benadering een relatieve standaardonzekerheid u/c.
    """
    cfg = SENSOREN[sensor]
    kal = df.loc[:KALIBRATIE_EINDE].dropna(subset=[cfg["ruw"], "T", "AH"])
    # Gevoeligheid t.o.v. modelparameters bij gemiddelde bedrijfscondities.
    x0 = model.ontwerp(kal, cfg["ruw"]).mean(axis=0)
    u_param = float(np.sqrt(x0 @ model.cov @ x0))
    # Resolutie: 1 telling van de ruwe sensor, rechthoekig, gevoeligheid b1/ruw.
    ruw_gem = kal[cfg["ruw"]].mean()
    u_resolutie = abs(model.beta[1]) * (1 / ruw_gem) / (2 * np.sqrt(3))

    rijen = [
        ("Spreiding kalibratiemodel (residuen)", "A", "normaal", model.s_res),
        ("Onzekerheid modelparameters", "A", "normaal", u_param),
        ("Referentie-analysator (EN-norm, k=2)", "B", "normaal", U_REF_REL / 2),
        (f"Drift binnen {interval_dagen}-daags interval", "B", "rechthoekig",
         drift_rel / np.sqrt(3)),
        ("Resolutie ruwe sensor (1 telling)", "B", "rechthoekig", u_resolutie),
    ]
    b = pd.DataFrame(rijen, columns=["component", "type", "verdeling", "u_rel"])
    b.insert(0, "sensor", sensor)
    b["bijdrage_var"] = b.u_rel ** 2
    b["aandeel"] = b.bijdrage_var / b.bijdrage_var.sum()
    return b


def samenvatting_budget(budget: pd.DataFrame, k: float = 2.0) -> dict:
    u_c = float(np.sqrt(budget.bijdrage_var.sum()))
    return {"u_c_rel": u_c, "k": k, "U_rel": k * u_c,
            "voldoet_dqo": k * u_c <= DQO_INDICATIEF}


def monte_carlo(budget: pd.DataFrame, n: int = 1_000_000, seed: int = 42) -> np.ndarray:
    """Propageer de componenten als verdelingen; geeft relatieve fouten terug."""
    rng = np.random.default_rng(seed)
    som = np.zeros(n)
    for _, r in budget.iterrows():
        if r.verdeling == "normaal":
            som += rng.normal(0, r.u_rel, n)
        else:  # rechthoekig met halve breedte a = u * sqrt(3)
            a = r.u_rel * np.sqrt(3)
            som += rng.uniform(-a, a, n)
    return np.expm1(som)   # ln-ruimte -> relatieve fout

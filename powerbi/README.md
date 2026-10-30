# Power BI-rapport: Sensorkwaliteit & meetonzekerheid

## Datamodel (sterschema)

```
            Datum (DAX)                 sensoren (dimensie)
                │ 1                          │ 1
                │                            │
                ▼ *                          ▼ *
            metingen  ◄──────────────── sensor ──────────► maandkwaliteit
                                         │               kalibratie_interval
                                         │               onzekerheidsbudget
                                         └──────────────► onzekerheid_samenvatting
```

- `sensoren[sensor]` 1 → * met `metingen`, `maandkwaliteit`, `kalibratie_interval`, `onzekerheidsbudget` en `onzekerheid_samenvatting`.
- `Datum[Date]` 1 → * `metingen[datum]`. Markeer `Datum` als datumtabel.
- Filterrichting overal **enkel** (van dimensie naar feit).

### Datumtabel

```dax
Datum =
ADDCOLUMNS (
    CALENDAR ( DATE ( 2004, 3, 1 ), DATE ( 2005, 4, 30 ) ),
    "Jaar", YEAR ( [Date] ),
    "Maand", FORMAT ( [Date], "mmm yyyy" ),
    "MaandSort", YEAR ( [Date] ) * 100 + MONTH ( [Date] ),
    "Kwartaal", "Q" & QUARTER ( [Date] ) & " " & YEAR ( [Date] )
)
```

Sorteer `Maand` op `MaandSort`.

## Measures (tabel `_Measures`)

```dax
Uren = COUNTROWS ( metingen )

Volledigheid sensor =
1 - DIVIDE (
    CALCULATE ( COUNTROWS ( metingen ), metingen[vlag_ontbreekt] = TRUE () ),
    [Uren]
)

Volledigheid referentie =
DIVIDE (
    CALCULATE ( COUNTROWS ( metingen ), NOT ISBLANK ( metingen[referentie] ) ),
    [Uren]
)

-- Uren waarin het referentiestation uitviel maar de sensor een waarde leverde
Uren opgevuld door sensor =
CALCULATE (
    COUNTROWS ( metingen ),
    ISBLANK ( metingen[referentie] ),
    NOT ISBLANK ( metingen[gekalibreerd_herkalibratie] )
)

% binnen DQO =
DIVIDE (
    CALCULATE ( COUNTROWS ( metingen ), metingen[binnen_dqo] = TRUE () ),
    CALCULATE ( COUNTROWS ( metingen ), NOT ISBLANK ( metingen[binnen_dqo] ) )
)

Bias =
CALCULATE ( AVERAGE ( metingen[fout_herkalibratie] ), metingen[periode] = "validatie" )

RMSE =
VAR t =
    FILTER (
        metingen,
        metingen[periode] = "validatie"
            && NOT ISBLANK ( metingen[fout_herkalibratie] )
    )
RETURN
    SQRT ( AVERAGEX ( t, metingen[fout_herkalibratie] ^ 2 ) )

Mediane relatieve fout =
MEDIANX (
    FILTER ( metingen, NOT ISBLANK ( metingen[rel_fout_herkalibratie] ) ),
    metingen[rel_fout_herkalibratie]
)

Uitgebreide onzekerheid U = SELECTEDVALUE ( onzekerheid_samenvatting[U_rel] )

DQO-status =
VAR u = [Uitgebreide onzekerheid U]
RETURN
    SWITCH (
        TRUE (),
        ISBLANK ( u ), "Kies één sensor",
        u <= 0.25, "✔ Voldoet aan DQO (≤ 25 %)",
        "✖ Voldoet niet: U = " & FORMAT ( u, "0 %" ) & " > 25 %"
    )

Eenheid = SELECTEDVALUE ( sensoren[eenheid] )
```

Formatteer `Volledigheid …`, `% binnen DQO`, `Mediane relatieve fout` en `Uitgebreide onzekerheid U` als percentage.

## Rapportpagina's

**1. Overzicht.** Slicer `sensoren[naam]` (één selectie). Vier kaarten: *Volledigheid sensor*, *% binnen DQO*,
*Uitgebreide onzekerheid U* en *Uren opgevuld door sensor*. Een kaart met *DQO-status*. Een lijndiagram met
`metingen[tijdstip]` op de x-as en `referentie` en `gekalibreerd_herkalibratie` als waarden (zoom met een datumslicer).

**2. Drift & kalibratie.** Een lijndiagram uit `maandkwaliteit`: x = `maand`, y = `bias`, legenda = `variant`.
Een staafdiagram uit `kalibratie_interval`: x = `interval_label` (gesorteerd op `interval_dagen`), y = `binnen_dqo`.
Een spreidingsdiagram `referentie` tegenover `gekalibreerd_herkalibratie`.

**3. Meetonzekerheid.** Een liggend staafdiagram uit `onzekerheidsbudget`: as = `component`, waarde = `aandeel`.
Een tabel met `component`, `type`, `verdeling` en `u_rel`. Een matrix uit `onzekerheid_samenvatting` met
voorwaardelijke opmaak op `U_rel` (rood als > `dqo`).

**4. Datakwaliteit.** Een matrix met rijen `Datum[Maand]`, kolommen `sensoren[sensor]` en de waarden
*Volledigheid sensor* en *Volledigheid referentie*, met een kleurschaal. Een kaart met het aantal `vlag_piek = TRUE`.

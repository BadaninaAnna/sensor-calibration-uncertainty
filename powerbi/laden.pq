// Power Query (M) - laadt de geëxporteerde CSV's met vaste landinstelling en-US
// (punt als decimaalteken), ongeacht de taal van Windows/Power BI.
//
// Gebruik: maak in Power BI een parameter "Map" (tekst) met het volledige pad
// naar data\processed\  (eindigend op een backslash), en maak per tabel een
// lege query aan met de bijbehorende code hieronder.

// ---------------------------------------------------------------- metingen
let
    Bron = Csv.Document(File.Contents(Map & "metingen.csv"),
        [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),
    Koppen = Table.PromoteHeaders(Bron, [PromoteAllScalars = true]),
    Types = Table.TransformColumnTypes(Koppen, {
        {"tijdstip", type datetime}, {"sensor", type text},
        {"referentie", type number}, {"ruw_signaal", type number},
        {"gekalibreerd_statisch", type number}, {"gekalibreerd_herkalibratie", type number},
        {"temperatuur", type number}, {"rel_vochtigheid", type number},
        {"abs_vochtigheid", type number}, {"vlag_ontbreekt", type logical},
        {"vlag_piek", type logical}, {"periode", type text},
        {"fout_herkalibratie", type number}, {"rel_fout_herkalibratie", type number},
        {"binnen_dqo", type logical}}, "en-US"),
    Datum = Table.AddColumn(Types, "datum", each DateTime.Date([tijdstip]), type date)
in
    Datum

// ---------------------------------------------------------- maandkwaliteit
let
    Bron = Csv.Document(File.Contents(Map & "maandkwaliteit.csv"),
        [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),
    Koppen = Table.PromoteHeaders(Bron, [PromoteAllScalars = true]),
    Types = Table.TransformColumnTypes(Koppen, {
        {"sensor", type text}, {"variant", type text}, {"maand", type date},
        {"n", Int64.Type}, {"bias", type number}, {"rmse", type number},
        {"r2", type number}, {"binnen_dqo", type number},
        {"volledigheid_referentie", type number}, {"volledigheid_sensor", type number}}, "en-US")
in
    Types

// ----------------------------------------------------- kalibratie_interval
let
    Bron = Csv.Document(File.Contents(Map & "kalibratie_interval.csv"),
        [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),
    Koppen = Table.PromoteHeaders(Bron, [PromoteAllScalars = true]),
    Types = Table.TransformColumnTypes(Koppen, {
        {"sensor", type text}, {"interval_dagen", Int64.Type}, {"interval_label", type text},
        {"n", Int64.Type}, {"bias", type number}, {"rmse", type number},
        {"r2", type number}, {"binnen_dqo", type number}}, "en-US")
in
    Types

// ------------------------------------------------------ onzekerheidsbudget
let
    Bron = Csv.Document(File.Contents(Map & "onzekerheidsbudget.csv"),
        [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),
    Koppen = Table.PromoteHeaders(Bron, [PromoteAllScalars = true]),
    Types = Table.TransformColumnTypes(Koppen, {
        {"sensor", type text}, {"component", type text}, {"type", type text},
        {"verdeling", type text}, {"u_rel", type number},
        {"bijdrage_var", type number}, {"aandeel", type number}}, "en-US")
in
    Types

// ------------------------------------------------ onzekerheid_samenvatting
let
    Bron = Csv.Document(File.Contents(Map & "onzekerheid_samenvatting.csv"),
        [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),
    Koppen = Table.PromoteHeaders(Bron, [PromoteAllScalars = true]),
    Types = Table.TransformColumnTypes(Koppen, {
        {"sensor", type text}, {"u_c_rel", type number}, {"k", type number},
        {"U_rel", type number}, {"voldoet_dqo", type logical},
        {"mc_ondergrens_95", type number}, {"mc_bovengrens_95", type number},
        {"empirisch_abs_fout_p95", type number}, {"dqo", type number}}, "en-US")
in
    Types

// ---------------------------------------------------------------- sensoren
let
    Bron = Csv.Document(File.Contents(Map & "sensoren.csv"),
        [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),
    Koppen = Table.PromoteHeaders(Bron, [PromoteAllScalars = true]),
    Types = Table.TransformColumnTypes(Koppen, {
        {"sensor", type text}, {"naam", type text}, {"eenheid", type text},
        {"referentiekanaal", type text}, {"sensorkanaal", type text},
        {"grenswaarde", type number}, {"omgevingscorrectie", type logical},
        {"herkalibratie_dagen", Int64.Type}, {"colocatie_dagen", Int64.Type}}, "en-US")
in
    Types

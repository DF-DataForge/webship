# 10 — Retours, backorders en voorraad

* **Doel**: de drie dingen die Stoqflow zelf aanmaakt of bijhoudt, correct in
  Odoo verwerken: retours van klanten, backorders van gedeeltelijk geleverde
  orders, en de voorraad in het Stoqflow-magazijn.
* **Doelpubliek**: logistiek, Odoo-beheerder.
* **Duur**: ± 4:00
* **Klaarzetten**: demodatabase met sandboxsleutels. In Stoqflow: een retour
  (inkooporder met leveranciersreferentie `Retour S000xx` voor een eerder
  geleverde verkooporder, status *Geleverd*), een gedeeltelijk verzonden order
  met een vervolgorder, en een voorraadverschil voor *Woody's Crew Socks*.

## Hoofdstukken

`0:00` Inleiding · `0:15` Retours ophalen · `0:55` Een retourlevering aanmaken ·
`1:30` Retours automatisch verwerken · `1:45` Backorders: twee manieren ·
`2:40` Backorders opvolgen · `3:00` Voorraad vergelijken · `3:45` Samenvatting

## Draaiboek

| # | Tijd | Beeld | Voice-over | Tekst in beeld |
|---|---|---|---|---|
| 1 | 0:00–0:06 | Openingskaart. | — | **Retours, backorders en voorraad** |
| 2 | 0:06–0:15 | Menu **Stoqflow** opengeklapt: **Retours**, **Backorders**, **Voorraad**. | Sommige dingen gebeuren in het magazijn zelf: een klant stuurt iets terug, een order wordt maar deels geleverd, of de voorraad wordt geteld. Zo houdt u Odoo gelijk. | Retours · backorders · voorraad |
| 3 | 0:15–0:40 | Stoqflow-sandbox: een retour, vastgelegd als inkooporder met leveranciersreferentie *Retour S00012*. | Stoqflow legt een retour vast als een inkooporder, met in de leveranciersreferentie het woord Retour gevolgd door het nummer van het oorspronkelijke verkooporder. Zo weet Odoo bij welk order de retour hoort. | Retour = inkooporder "Retour S…" |
| 4 | 0:40–0:55 | **Stoqflow → Retours**: knop **Retours synchroniseren** (of in de instellingen **Retours ophalen uit Stoqflow**). Lijst met de retour, filters *Geleverd*, *Voltooid*. | In Odoo haalt u de retours op via Stoqflow, Retours. De lijst toont elke retour met zijn status in Stoqflow. | Stoqflow → Retours |
| 5 | 0:55–1:30 | Retour openen: **Retourinfo** met **Originele verkooporder**, **Retourregels**. Klik **Retourlevering aanmaken** → melding *created successfully* → de retourlevering in Odoo, gekoppeld aan de verkooporder. Inzet: is de retour nog niet geleverd, dan vraagt Odoo om bevestiging. | Open een retour: u ziet het oorspronkelijke verkooporder en de teruggestuurde producten. Klik op Retourlevering aanmaken: Odoo maakt een retour op basis van de oorspronkelijke levering, zodat de verkooporder, de voorraad en een eventuele creditnota kloppen. Is de retour in Stoqflow nog niet binnen, dan vraagt Odoo eerst of u toch wilt doorgaan. | Retourlevering aanmaken |
| 6 | 1:30–1:45 | Instellingen, blok **Retours**: **Retours automatisch invoegen in Odoo** aangevinkt; in Geplande taken: *Fetch returns from Stoqflow* actief. | Wilt u dat niet per retour doen, vink dan Retours automatisch invoegen aan. De geplande taak haalt de retours op en maakt de retourleveringen zelf. | Automatisch |
| 7 | 1:45–2:15 | Schema: order 24 stuks → 20 verzonden. Links: *Odoo-backorder (4)*. Rechts: *Stoqflow-vervolgorder (4)*. Twee pijlen: **A. koppelen** en **B. verwijderen in Stoqflow**. | Levert Stoqflow een order maar deels, dan maakt Odoo een backorder voor de rest, zoals u zag in video 07. Maar Stoqflow maakt vaak zelf ook een vervolgorder. U kiest hoe u daarmee omgaat. | Twee backorders, één keuze |
| 8 | 2:15–2:40 | Blok **Synchronisatie**: **Backorders koppelen** aangevinkt. Odoo-backorder: tabblad Stoqflow met de link naar het vervolgorder, processcode *Verstuurd naar Stoqflow*. Daarna blok **Backorders**: **Backorders automatisch verwijderen in Stoqflow**. | Manier A: Stoqflow levert de rest. Met Backorders koppelen verbindt Odoo zijn backorder met het vervolgorder van Stoqflow, en volgt het verder op zoals elk order. Manier B: u beslist zelf over de rest. Met Backorders automatisch verwijderen in Stoqflow wist Odoo de vervolgorders in Stoqflow, en stuurt u de backorder in Odoo zelf door wanneer het past. | A: koppelen · B: verwijderen in Stoqflow |
| 9 | 2:40–3:00 | **Stoqflow → Backorders**: lijst met **Type**, link naar het order en de **Bovenliggende order in Stoqflow**, kolom **Backorder in Odoo**. Selectie → **Selectie verwijderen in Stoqflow** (bevestiging bij een backorder zonder Odoo-backorder). | In Stoqflow, Backorders ziet u alle vervolgorders uit Stoqflow, met het oorspronkelijke order en de backorder in Odoo. Hier verwijdert u ze ook manueel, één voor één of in groep. | Stoqflow → Backorders |
| 10 | 3:00–3:20 | Instellingen, blok **Voorraadbeheer**: **Voorraad laden uit Stoqflow**. Daarna **Stoqflow → Voorraad**: kolommen Odoo-hoeveelheid, Stoqflow totaal, gereserveerd, beschikbaar, verschillen, laatste controle. | Tot slot de voorraad. Met Voorraad laden uit Stoqflow, of elke dag via de geplande taak, haalt Odoo de voorraad van Stoqflow op. Het scherm Stoqflow, Voorraad zet die naast de voorraad in Odoo, product per product. | Voorraad vergelijken |
| 11 | 3:20–3:45 | Filter **Voorraad wijkt af** → *Woody's Crew Socks* met een verschil. Lijn selecteren → **Stoqflow-voorraad toepassen op Odoo** → hoeveelheid in Odoo gelijk. Inzet: optie **Odoo-voorraad automatisch aanpassen** in de geplande taken. | Met het filter Voorraad wijkt af ziet u meteen waar Odoo en Stoqflow verschillen. Zoek eerst de oorzaak: een levering die nog open staat bijvoorbeeld. Klopt de telling van Stoqflow, selecteer de lijn en klik op Stoqflow-voorraad toepassen op Odoo. Vertrouwt u Stoqflow volledig, laat de geplande taak de voorraad dan automatisch aanpassen. | Voorraad wijkt af → toepassen |
| 12 | 3:45–3:54 | De drie menu's naast elkaar. | Retours, backorders en voorraad: zo blijven Odoo en het magazijn op elkaar afgestemd. | — |
| 13 | 3:54–4:00 | Eindkaart. | — | Volgende: opvolgen en fouten oplossen |

## Eindkaart

*Bekijk video 11: opvolgen en fouten oplossen.*

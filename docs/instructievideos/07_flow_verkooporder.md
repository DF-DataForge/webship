# 07 — Flow: van verkooporder tot uitgaande levering

* **Doel**: één verkooporder van begin tot eind volgen: bevestigen in Odoo,
  doorsturen naar Stoqflow, picken en verzenden in Stoqflow, en automatisch
  afgewerkt in Odoo, met tracking. Daarna de twee uitzonderingen: een
  gedeeltelijke levering (backorder) en een annulering.
* **Doelpubliek**: verkoop, logistiek, Odoo-beheerder.
* **Duur**: ± 4:30
* **Klaarzetten**: demodatabase met sandboxsleutels en de geplande taken uit
  video 06 (voor de opname mag u **Manueel uitvoeren** gebruiken in plaats van
  te wachten). Voorraad van kleding in *SQF/Stock*. Klant *Lotte Peeters* en
  B2B-klant *Concrete Wave Skateshop*. Stoqflow-sandbox open in een tweede
  tabblad om de statussen van het order te kunnen wijzigen.

## Hoofdstukken

`0:00` De flow in één beeld · `0:25` Verkooporder bevestigen · `0:55` De levering en de processcode ·
`1:25` Doorsturen naar Stoqflow · `2:00` In Stoqflow: picken en verzenden ·
`2:35` Terug in Odoo: automatisch gevalideerd · `3:10` Gedeeltelijke levering en backorder ·
`3:50` Een order annuleren · `4:15` Samenvatting

## Draaiboek

| # | Tijd | Beeld | Voice-over | Tekst in beeld |
|---|---|---|---|---|
| 1 | 0:00–0:06 | Openingskaart. | — | **Van verkooporder tot uitgaande levering** |
| 2 | 0:06–0:25 | Schema: *Verkooporder* → *Levering SQF/Stock → Klant* (Odoo) ⇄ *Order* (Stoqflow) met de statussen *Klaar om te picken → Picken → Inpakken → Klaar om te verzenden → Voltooid*, en terug: *aantallen + tracking*. | Dit is de belangrijkste flow: een klant bestelt, Stoqflow verzendt. In Odoo maakt u alleen de verkooporder. De levering gaat vanzelf naar Stoqflow, en wanneer Stoqflow klaar is, komen de geleverde aantallen en de tracking vanzelf terug. | Verkoop → levering → Stoqflow-order |
| 3 | 0:25–0:55 | Verkoop → **Nieuw**: klant *Lotte Peeters*, lijnen 2 × *Woody's Logo Tee (White, S)* en 1 × *Woody's Beanie*. Tabblad Overige info: **Magazijn** = *Stoqflow Fulfilment*. **Bevestigen**. | Maak een verkooporder zoals altijd. Controleer bij Overige info dat het magazijn Stoqflow Fulfilment is; als u dat als standaard instelde, staat het er al. Webshoporders komen hier op dezelfde manier binnen. Bevestig het order. | Magazijn = Stoqflow Fulfilment |
| 4 | 0:55–1:25 | Slimme knop **Levering** → levering *SQF/OUT/…*, van *SQF/Stock* naar *Klanten*. Tabblad **Stoqflow**: **Processcode** *In afwachting*, nog geen orderlink. Daarna **Stoqflow → Orders**: de levering staat in de lijst, kolom **Object in Stoqflow** = *Order*. | Odoo maakt een levering uit SQF/Stock. Omdat die locatie een Stoqflow-locatie is, verschijnt er een tabblad Stoqflow, met processcode In afwachting: de levering wacht om doorgestuurd te worden. In het menu Stoqflow, Orders vindt u alle leveringen en ontvangsten die via Stoqflow lopen. | Processcode: In afwachting |
| 5 | 1:25–1:45 | **Stoqflow → Instellingen** → **Manueel uitvoeren** bij *Wachtende orders verwerken* (of op de levering zelf **Manueel synchroniseren**). Terug naar de levering. | De geplande taak Wachtende orders verwerken stuurt de levering door. Om niet te wachten klikken we hier op Manueel uitvoeren. Op de levering zelf kan het ook, met Manueel synchroniseren. | Doorsturen |
| 6 | 1:45–2:00 | Tabblad **Stoqflow**: **Orderlink Stoqflow** gevuld, **Laatste synchronisatie op**, **Resultaat laatste synchronisatie** groen, **Status in Stoqflow** *Klaar om te picken*, processcode *Verstuurd naar Stoqflow*. Chatter met de notitie. | Het order staat in Stoqflow. U ziet de link, het tijdstip, het resultaat en de status: Klaar om te picken. Lotte bestond nog niet in Stoqflow; Odoo heeft haar eerst als klant aangemaakt, of gematcht als ze al bestond. | Verstuurd naar Stoqflow |
| 7 | 2:00–2:35 | Klik op de **Orderlink Stoqflow** → het order in de Stoqflow-app: klant, adres, lijnen met SKU's, shop. Status in de sandbox doorschakelen: *Picken* → *Inpakken* → *Voltooid*, met een pakket en trackingnummer. | Via de link opent u het order in Stoqflow: dezelfde klant, hetzelfde adres en dezelfde producten, herkend aan hun SKU. Het magazijn pickt, pakt in en verzendt. In deze sandbox doen we dat even manueel. Bij het verzenden krijgt het pakket een trackingnummer. | In Stoqflow: picken, inpakken, verzenden |
| 8 | 2:35–3:10 | Odoo, na **Gewijzigde orders ophalen**: de levering staat op **Gereed**. Tabblad Stoqflow: status *Voltooid*, **Laatste wijziging in Stoqflow**. Tabblad **Stoqflow-pakketten**: pakket met trackinglink. Tabblad **Pickanalyse**. Terug naar de verkooporder: kolom *Geleverd* = 2 en 1. | Bij de volgende ronde haalt Odoo het voltooide order op. Het neemt de gepickte aantallen over en valideert de levering zelf. Op het tabblad Pakketten staat de trackinglink voor de klant, op Pickanalyse wat er precies gepickt werd. Op de verkooporder staan de geleverde aantallen goed, dus u kunt meteen factureren op basis van wat echt verzonden is. | Automatisch gevalideerd · tracking |
| 9 | 3:10–3:25 | Andere open levering met processcode *Verstuurd naar Stoqflow*: klik **Valideren** → foutmelding *… is managed by the Stoqflow sync …*. | Valideer zulke leveringen nooit zelf: Odoo houdt u tegen, want anders lopen Odoo en Stoqflow uit elkaar. Moet het toch, zet dan eerst de processcode op Manueel. | Niet zelf valideren |
| 10 | 3:25–3:50 | B2B-order *Concrete Wave Skateshop*: 24 × *Woody's Crew Socks*. In Stoqflow worden er 20 verzonden. In Odoo: levering gevalideerd met 20, een **backorder** voor 4 met processcode *Manueel*. Daarna de backorder met link naar het Stoqflow-vervolgorder. | Kan Stoqflow niet alles leveren, dan valideert Odoo de levering met wat er echt verzonden is en maakt een backorder voor de rest. Die backorder stuurt Odoo niet als nieuw order door: met Backorders koppelen zoekt Odoo het vervolgorder dat Stoqflow zelf aanmaakte, en koppelt het eraan. | Gedeeltelijk → backorder |
| 11 | 3:50–4:15 | Nieuwe verkooporder, bevestigd en doorgestuurd. **Annuleren** op de verkooporder → levering geannuleerd → tabblad Stoqflow: status *Geannuleerd*, processcode *Geannuleerd*. In Stoqflow: order geannuleerd. | Annuleert u een order dat al in Stoqflow staat, dan annuleert Odoo het daar ook, op voorwaarde dat u die optie aanzette in de instellingen. Is het order in Stoqflow al gepickt, neem dan eerst contact op met het magazijn. | Annuleren = ook in Stoqflow |
| 12 | 4:15–4:24 | Schema van scène 2, nu met vinkjes. | Samengevat: u verkoopt in Odoo, Stoqflow levert, en Odoo werkt zichzelf bij. | Verkopen in Odoo, leveren via Stoqflow |
| 13 | 4:24–4:30 | Eindkaart. | — | Volgende: van inkooporder tot ontvangst |

## Processcodes in deze flow

| Processcode | Betekenis | Wie doet wat |
|---|---|---|
| *In afwachting* | Wacht om naar Stoqflow te gaan | Geplande taak stuurt door |
| *Verstuurd naar Stoqflow* | Staat in Stoqflow, wordt gevolgd | Stoqflow pickt, Odoo valideert |
| *Fout* | Doorsturen mislukt (na de syncpogingen) | Iemand lost het op, zie video 11 |
| *Manueel* | Odoo stuurt niet automatisch door (domeinfilter, backorder) | Manueel synchroniseren of zelf afhandelen |
| *Geannuleerd* | Geannuleerd in Odoo en Stoqflow | — |
| *Niet van toepassing* | Geen Stoqflow-locatie betrokken | Gewone Odoo-flow |

## Eindkaart

*Bekijk video 08: van inkooporder tot inkomende levering.*

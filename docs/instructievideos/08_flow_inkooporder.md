# 08 — Flow: van inkooporder tot inkomende levering

* **Doel**: een inkooporder volgen van bestelling tot ontvangst in het
  Stoqflow-magazijn: de ontvangst wordt een aangekondigde inkooporder in
  Stoqflow, en de echt ontvangen aantallen komen terug naar Odoo.
* **Doelpubliek**: aankoop, logistiek.
* **Duur**: ± 3:45
* **Klaarzetten**: demodatabase met sandboxsleutels en actieve geplande taken
  (of **Manueel uitvoeren**). Leverancier *ThreadWorks Apparel Lda* met volledig
  adres en e-mail. Op de locatie *SQF/Stock* is het **Stoqflow-magazijn**
  ingevuld (video 03). Stoqflow-sandbox open in een tweede tabblad.

## Hoofdstukken

`0:00` De flow in één beeld · `0:20` Inkooporder bevestigen · `0:50` De ontvangst ·
`1:10` Aankondigen in Stoqflow · `1:45` In Stoqflow: ontvangen en uitpakken ·
`2:20` Terug in Odoo: ontvangst gevalideerd · `2:50` Minder ontvangen dan besteld ·
`3:25` Samenvatting

## Draaiboek

| # | Tijd | Beeld | Voice-over | Tekst in beeld |
|---|---|---|---|---|
| 1 | 0:00–0:06 | Openingskaart. | — | **Van inkooporder tot inkomende levering** |
| 2 | 0:06–0:20 | Schema: *Inkooporder* → *Ontvangst Leverancier → SQF/Stock* (Odoo) ⇄ *Inkooporder* (Stoqflow) met *Besteld → Onderweg → Geleverd → Uitpakken → Voltooid*, terug: *ontvangen aantallen*. | Bestelt u goederen die rechtstreeks in het Stoqflow-magazijn toekomen, dan moet Stoqflow weten wat er onderweg is. Odoo kondigt de levering aan, en neemt na ontvangst de getelde aantallen over. | Inkoop → ontvangst → Stoqflow-inkooporder |
| 3 | 0:20–0:50 | Inkoop → **Nieuw**: leverancier *ThreadWorks Apparel Lda*, lijnen 24 × *Woody's Logo Tee (Black, M)*, 120 × *Woody's Crew Socks*. Tabblad Overige info: **Leveren aan** = *Stoqflow Fulfilment: Ontvangsten*. **Order bevestigen**. | Maak de inkooporder zoals altijd. Belangrijk is het veld Leveren aan: kies de ontvangsten van Stoqflow Fulfilment. Een inkooporder die Odoo zelf maakt vanuit een aanvulregel op SQF/Stock, heeft dat al goed staan. Bevestig de order. | Leveren aan = Stoqflow Fulfilment |
| 4 | 0:50–1:10 | Slimme knop **Ontvangst** → *SQF/IN/…*, van *Leveranciers* naar *SQF/Stock*. Tabblad **Stoqflow**: processcode *In afwachting*. In **Stoqflow → Orders**: **Object in Stoqflow** = *Inkooporder*. | Odoo maakt een ontvangst naar SQF/Stock. Omdat ze in de Stoqflow-locatie aankomt, wordt ze een inkooporder in Stoqflow. Ze wacht nu om doorgestuurd te worden. | Object in Stoqflow: Inkooporder |
| 5 | 1:10–1:45 | **Manueel synchroniseren** op de ontvangst. Tabblad Stoqflow: link naar de inkooporder in Stoqflow, status *Besteld*, processcode *Verstuurd naar Stoqflow*. Daarna het contact *ThreadWorks*: tabblad Stoqflow, **Synchroniseren als leverancier** aangevinkt, link naar de leverancier. | De geplande taak stuurt de ontvangst door; hier doen we het manueel. Odoo maakt de leverancier aan in Stoqflow als die nog niet bestond, of matcht hem met een bestaande, en kondigt de inkooporder aan met status Besteld, in het magazijn dat u op de locatie koos. | Aangekondigd in Stoqflow |
| 6 | 1:45–2:20 | Stoqflow-sandbox: de inkooporder met leverancier, referentie van Odoo en de lijnen. Status doorschakelen: *Onderweg* → *Geleverd* → *Uitpakken* → *Voltooid*, met ontvangen aantallen 24 en 120. | In Stoqflow ziet het magazijn welke goederen er komen, van wie en hoeveel. Bij aankomst wordt alles uitgepakt en geteld. Odoo volgt de status mee: onderweg, geleverd, uitpakken, voltooid. | In Stoqflow: ontvangen en tellen |
| 7 | 2:20–2:50 | Odoo na **Gewijzigde orders ophalen**: ontvangst op **Gereed**, aantallen 24 en 120. Inkooporder: kolom *Ontvangen* gevuld. Voorraad → *SQF/Stock*: hoeveelheid gestegen. | Zodra Stoqflow de inkooporder voltooit, neemt Odoo de ontvangen aantallen over en valideert het de ontvangst. De voorraad in SQF staat meteen goed, en de leveranciersfactuur kunt u controleren op wat echt ontvangen is. | Automatisch ontvangen |
| 8 | 2:50–3:25 | Tweede inkooporder: 24 × *Kickflip Hoodie (Black, L)*. In Stoqflow worden er 20 geteld. In Odoo: ontvangst gevalideerd met 20, **backorder** voor 4. Inzet: een ontvangst waar Stoqflow 0 telde blijft open, met de melding in **Resultaat laatste synchronisatie**. | Komt er minder binnen dan besteld, dan valideert Odoo de ontvangst met wat er echt geteld is, en maakt een backorder voor de rest. Werd er niets ontvangen, dan laat Odoo de ontvangst open en zegt waarom. Zo blijft uw voorraad altijd gelijk met wat er fysiek in het magazijn ligt. | Minder ontvangen → backorder |
| 9 | 3:25–3:39 | Schema van scène 2, met vinkjes. | Samengevat: bestellen in Odoo, Stoqflow ontvangt en telt, Odoo boekt de juiste aantallen. | Bestellen in Odoo, ontvangen via Stoqflow |
| 10 | 3:39–3:45 | Eindkaart. | — | Volgende: bevoorraden vanuit het eigen magazijn |

## Aandachtspunten voor de opname

* Blijft de ontvangst in *Fout* met *Supplier does not exist in Stoqflow*,
  controleer dan het adres en het e-mailadres van de leverancier (verplichte
  velden, video 04).
* Zonder **Stoqflow-magazijn** op de locatie *SQF/Stock* weet Stoqflow niet
  waar de goederen aankomen. Controleer dat vóór de opname.

## Eindkaart

*Bekijk video 09: bevoorraden vanuit het eigen magazijn.*

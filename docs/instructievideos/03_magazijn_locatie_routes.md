# 03 — Magazijn, locatie en routes

* **Doel**: het magazijn van Stoqflow in Odoo inrichten, de Stoqflow-locatie
  aanduiden en de routes zo instellen dat verkoop, aankoop en bevoorrading
  vanzelf de juiste Stoqflow-documenten maken.
* **Doelpubliek**: Odoo-beheerder, logistiek verantwoordelijke.
* **Duur**: ± 4:00
* **Klaarzetten**: de database uit video 02 (verbonden, magazijnen geladen),
  met het eigen magazijn `H800` Skate Workshop H800. Een contact
  *Stoqflow Fulfilment Centre* met het adres van het fulfilmentmagazijn.
  Ter vergelijking open in een tweede tabblad: de demodatabase Woody's Skate
  Supply.

## Hoofdstukken

`0:00` Het principe · `0:35` Voorraadinstellingen · `0:55` Het Stoqflow-magazijn ·
`1:40` De Stoqflow-locatie · `2:25` Routes voor verkoop · `2:55` Routes voor aankoop ·
`3:20` Bevoorrading vanuit het eigen magazijn · `3:45` Samenvatting

## Draaiboek

| # | Tijd | Beeld | Voice-over | Tekst in beeld |
|---|---|---|---|---|
| 1 | 0:00–0:06 | Openingskaart. | — | **Magazijn, locatie en routes** |
| 2 | 0:06–0:35 | Schema (animatie): locatie *SQF/Stock* in het midden. Pijl eruit → *Order in Stoqflow*. Pijl erin → *Inkooporder in Stoqflow*. Pijl tussen twee gewone locaties → *niet naar Stoqflow*. | De koppeling kijkt naar één ding: de locatie. U duidt in Odoo één voorraadlocatie aan als Stoqflow-locatie. Een overboeking die uit die locatie vertrekt, wordt een order in Stoqflow. Een overboeking die erin aankomt, wordt een inkooporder, een aangekondigde levering. Al de rest blijft in Odoo. Daarom is de inrichting van magazijn en routes zo belangrijk. | Eruit = order · erin = inkooporder · rest = enkel Odoo |
| 3 | 0:35–0:55 | Voorraad → Configuratie → **Instellingen**, blok Magazijn: **Opslaglocaties** en **Routes met meerdere stappen** aanvinken. **Opslaan**. | Zet eerst in de Voorraad-instellingen de opslaglocaties en de routes met meerdere stappen aan. Zonder die opties ziet u de locaties en routes niet. | Opslaglocaties · routes |
| 4 | 0:55–1:20 | Voorraad → Configuratie → **Magazijnen** → **Nieuw**. Naam *Stoqflow Fulfilment*, korte naam *SQF*, adres *Stoqflow Fulfilment Centre*. | Maak een apart magazijn voor Stoqflow, los van uw eigen magazijn. Hier noemen we het Stoqflow Fulfilment, met korte naam SQF, en het adres van het fulfilmentcentrum. | Eén magazijn voor Stoqflow |
| 5 | 1:20–1:40 | Tabblad Configuratie van het magazijn: **Inkomende zendingen** op 1 stap (ontvangen en opslaan), **Uitgaande zendingen** op 1 stap (leveren). Inzoomen. Daarna **Bevoorraden vanuit**: *Skate Workshop H800*. **Opslaan**. | Zet ontvangst en levering allebei op één stap. Stoqflow pickt, pakt in en verzendt zelf: extra stappen in Odoo zouden alleen dubbel werk geven, en de laatste stap zou nooit automatisch gevalideerd worden. Komen uw producten deels uit uw eigen magazijn, kies dat dan bij Bevoorraden vanuit. | Ontvangst 1 stap · levering 1 stap |
| 6 | 1:40–2:05 | Voorraad → Configuratie → **Locaties** → *SQF/Stock*. Vinkje **Is Stoqflow locatie?** aan. Veld **Stoqflow-magazijn**: het magazijn uit Stoqflow kiezen. | Open nu de voorraadlocatie van dat magazijn, SQF/Stock, en vink Is Stoqflow locatie aan. Kies in het veld Stoqflow-magazijn het magazijn uit uw Stoqflow-account. Dat veld is nodig voor inkomende leveringen: zo weet Stoqflow in welk magazijn de goederen aankomen. | Is Stoqflow locatie? · Stoqflow-magazijn |
| 7 | 2:05–2:25 | Veld **Stoqflow company ID** verschijnt na het vinkje. Callout: *alleen nodig bij meerdere Stoqflow-locaties*. Daarna lijst van locaties: alleen *SQF/Stock* heeft het vinkje. | Werkt u met meer dan één Stoqflow-bedrijf, dan vult u bij elke locatie het Stoqflow company ID in, zodat de voorraad in de juiste locatie terechtkomt. Met één locatie laat u het leeg. Duid nooit de locaties van uw eigen magazijn aan. | Alleen SQF/Stock aanvinken |
| 8 | 2:25–2:55 | Gebruiker → **Voorkeuren** (of Instellingen → Gebruikers): **Standaardmagazijn** *Stoqflow Fulfilment*. Daarna Website → Configuratie → Instellingen: magazijn van de webshop *Stoqflow Fulfilment*. Een nieuwe verkooporder: tabblad Overige info, **Magazijn** = *Stoqflow Fulfilment*. | Voor de verkoop bepaalt het magazijn op de verkooporder van waar geleverd wordt. Zet het Stoqflow-magazijn als standaardmagazijn bij de verkopers en, als u een Odoo-webshop heeft, in de website-instellingen. Zo vertrekt elke levering uit SQF/Stock en wordt ze een Stoqflow-order. | Verkoop: magazijn = SQF |
| 9 | 2:55–3:20 | Product *Woody's Logo Tee*, tabblad Voorraad: route **Inkopen** aangevinkt. Nieuwe inkooporder: veld **Leveren aan** = *Stoqflow Fulfilment: Ontvangsten*. Daarna Voorraad → Bevoorrading: aanvulregel op *SQF/Stock* met route *Inkopen*. | Voor de aankoop kiest u op de inkooporder bij Leveren aan de ontvangsten van Stoqflow Fulfilment. Werkt u met aanvulregels, maak ze dan aan op de locatie SQF/Stock met de route Inkopen. Odoo maakt dan zelf inkooporders die in het Stoqflow-magazijn toekomen. | Aankoop: leveren aan SQF |
| 10 | 3:20–3:45 | Product *Woody's Street Complete 8.0"*, tabblad Voorraad: route *Stoqflow Fulfilment: … Skate Workshop H800* aangevinkt. Schema: *H800/Stock → Transit* (Odoo) → *Transit → SQF/Stock* (inkooporder in Stoqflow). | Wordt een product in uw eigen magazijn gemaakt of bewaard, gebruik dan de bevoorradingsroute die Odoo aanmaakte toen u Bevoorraden vanuit instelde. De eerste stap, van uw magazijn naar transit, blijft in Odoo. De tweede stap, van transit naar SQF, wordt een inkooporder in Stoqflow: zo weet Stoqflow dat er goederen onderweg zijn. | Bevoorrading: 2e stap = inkooporder |
| 11 | 3:45–3:54 | Samenvattende tabel in beeld (zie hieronder). | Kortom: één magazijn op één stap, één aangevinkte locatie, en routes die naar die locatie wijzen. In de flowvideo's ziet u dit in actie. | Samenvatting |
| 12 | 3:54–4:00 | Eindkaart. | — | Volgende: synchronisatieregels |

### Samenvatting in beeld (scène 11)

| Overboeking | Van | Naar | In Stoqflow |
|---|---|---|---|
| Levering verkooporder | SQF/Stock | Klant | **Order** |
| Ontvangst inkooporder | Leverancier | SQF/Stock | **Inkooporder** |
| Bevoorrading, stap 1 | H800/Stock | Transit | — (enkel Odoo) |
| Bevoorrading, stap 2 | Transit | SQF/Stock | **Inkooporder** |
| Overboeking binnen het eigen magazijn | H800 | H800 | — (*Niet van toepassing*) |

## Aandachtspunten voor de opname

* Een locatie die pas later aangevinkt wordt, is geen probleem: de geplande
  taak *Reclassify Stoqflow object types* zet het type van bestaande
  overboekingen elke dag recht.
* Backorders die Odoo zelf aanmaakt in de Stoqflow-locatie krijgen de
  processcode *Manueel*: Odoo stuurt ze niet opnieuw als nieuw order door.
  Dat komt terug in video 07.

## Eindkaart

*Magazijn klaar? Bekijk video 04: synchronisatieregels voor orders, klanten en vervoerders.*

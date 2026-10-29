# 06 — Automatisering en bewaking: geplande taken, meldingen en dagrapport

* **Doel**: de koppeling automatisch laten draaien met de geplande taken, en
  instellen wie verwittigd wordt als er iets misloopt.
* **Doelpubliek**: Odoo-beheerder.
* **Duur**: ± 3:30
* **Klaarzetten**: de database uit video 05. Twee gebruikers (bv. *Logistiek*
  en *Beheerder*) en een gedeeld e-mailadres `logistiek@woodys.example`.

## Hoofdstukken

`0:00` Inleiding · `0:15` Hoe statussen terugkomen · `0:45` De geplande taken ·
`1:55` Manueel uitvoeren · `2:10` Foutnotificaties en syncpogingen · `2:50` Dagelijks rapport ·
`3:20` Samenvatting

## Draaiboek

| # | Tijd | Beeld | Voice-over | Tekst in beeld |
|---|---|---|---|---|
| 1 | 0:00–0:06 | Openingskaart. | — | **Automatisering en bewaking** |
| 2 | 0:06–0:15 | **Stoqflow → Instellingen**, scrollen naar **Geplande taken**. | Tot nu toe hebben we alles ingesteld, maar nog niets automatisch laten lopen. Dat doen we nu. | — |
| 3 | 0:15–0:45 | Blok **Synchronisatie**: **Incrementele statusupdates** aangevinkt. Schema: Odoo vraagt elke 10 minuten "wat is er gewijzigd sinds…?" → Stoqflow antwoordt met alleen de gewijzigde orders. | Eerst: hoe komen statussen en hoeveelheden terug naar Odoo? Met Incrementele statusupdates vraagt Odoo aan Stoqflow alleen de orders die gewijzigd zijn sinds de vorige keer. Dat is snel en licht, ook bij duizenden orders. Laat deze optie aan. | Incrementele statusupdates |
| 4 | 0:45–1:05 | Blok **Geplande taken**, tabel met kolommen *Taak*, *Actief*, *Om de*. Rij **Wachtende orders verwerken**: actief, om de 15 minuten. | In het blok Geplande taken zet u elke taak aan of uit en kiest u hoe vaak ze draait. Wachtende orders verwerken stuurt nieuwe leveringen en ontvangsten naar Stoqflow. Om het kwartier is een goed ritme. | Wachtende orders verwerken |
| 5 | 1:05–1:25 | Rij **Gewijzigde orders ophalen (incrementeel)**: actief, om de 10 minuten. Rij **Orderinfo & hoeveelheden ophalen**: niet actief. | Gewijzigde orders ophalen haalt de statussen, gepickte hoeveelheden en trackinglinks op en valideert voltooide leveringen. Zet die om de tien minuten. Orderinfo en hoeveelheden ophalen is de oude, zware methode die elk open order apart opvraagt: laat ze uit en gebruik ze alleen om eenmalig alles bij te werken. | Gewijzigde orders · om de 10 min |
| 6 | 1:25–1:55 | Rijen **Voorraad importeren uit Stoqflow** (dagelijks, met **Odoo-voorraad automatisch aanpassen**), **Dagelijks rapport versturen** (dagelijks), **Fetch returns from Stoqflow** en **Backorders ophalen uit Stoqflow** (om de 30 minuten), **Reclassify Stoqflow object types** (dagelijks). | De andere taken: de voorraad elke dag vergelijken, en desgewenst automatisch aanpassen. Het dagrapport versturen. Retours en backorders ophalen. En de herclassificatie, die nakijkt of elke overboeking het juiste type heeft. Over retours, backorders en voorraad gaat video 10. | Voorraad · rapport · retours · backorders |
| 7 | 1:55–2:10 | Klik **Manueel uitvoeren** naast *Wachtende orders verwerken* → bevestiging *Run manually?* → OK. | Wilt u niet wachten, klik dan op Manueel uitvoeren naast een taak. Handig na de eerste configuratie of tijdens een test. | Manueel uitvoeren |
| 8 | 2:10–2:30 | Blok **Foutnotificaties**: **Ontvangers van notificaties**: gebruikers *Logistiek* en *Beheerder*, bijkomend e-mailadres `logistiek@woodys.example`. | Bij Foutnotificaties kiest u wie een e-mail krijgt als een levering of ontvangst niet doorgestuurd kan worden. Kies gebruikers, en vul eventueel extra adressen in, gescheiden door komma's. | Wie wordt verwittigd? |
| 9 | 2:30–2:50 | **Aantal syncpogingen** = 3. **Fouten loggen in de chatter van de overboeking** aanvinken. Inzet: chatter van een levering met een foutbericht. | Mislukt het doorsturen, dan probeert Odoo het opnieuw, tot het aantal syncpogingen bereikt is. Daarna krijgt de levering de processcode Fout en moet iemand ze bekijken. Met Fouten loggen in de chatter blijft elke fout ook in de historiek van de levering staan. | Syncpogingen · fouten in de chatter |
| 10 | 2:50–3:10 | Blok **Dagelijks rapport**: **Ontvangers van het rapport** kiezen. Klik **Rapport nu versturen**. Inzet: de e-mail met verwerkte en mislukte overboekingen. | Het dagelijks rapport vat elke dag samen welke overboekingen verwerkt zijn, gelukt en mislukt. Kies de ontvangers en klik op Rapport nu versturen om het te testen. | Dagelijks rapport |
| 11 | 3:10–3:22 | **Opslaan**. Daarna **Tijdstippen laatste controle** met de tijdstippen van de laatste run. | Sla op. Onderaan bij Tijdstippen laatste controle ziet u wanneer Odoo het laatst statussen heeft opgehaald. Staat dat tijdstip stil, dan draait een taak niet. | Laatste controle |
| 12 | 3:22–3:30 | Eindkaart. | Daarmee is de configuratie klaar. In de volgende video's volgen we de flows van begin tot eind. | Volgende: van verkooporder tot levering |

## Aanbevolen instelling

| Taak | Actief | Om de |
|---|---|---|
| Wachtende orders verwerken | ja | 15 minuten |
| Gewijzigde orders ophalen (incrementeel) | ja | 10 minuten |
| Orderinfo & hoeveelheden ophalen | nee (alleen om bij te werken) | 30 minuten |
| Voorraad importeren uit Stoqflow | ja | 1 dag |
| Dagelijks rapport versturen | ja | 1 dag |
| Fetch returns from Stoqflow | ja, als u retours via Stoqflow verwerkt | 30 minuten |
| Backorders ophalen uit Stoqflow | ja | 30 minuten |
| Reclassify Stoqflow object types | ja | 1 dag |

## Eindkaart

*Alles draait? Bekijk video 07: van verkooporder tot uitgaande levering.*

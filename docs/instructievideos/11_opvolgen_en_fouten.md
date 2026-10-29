# 11 — Opvolgen en fouten oplossen

* **Doel**: dagelijks opvolgen of alles vlot naar Stoqflow gaat, de meest
  voorkomende fouten herkennen en oplossen, en weten welke informatie u aan
  Data Forge bezorgt als u er niet uitkomt.
* **Doelpubliek**: logistiek, Odoo-beheerder.
* **Duur**: ± 4:00
* **Klaarzetten**: demodatabase met sandboxsleutels en een paar leveringen in
  *Fout*: één met een product zonder synchronisatie (*SKU not found in
  Stoqflow*), één met een klant zonder straat (*Street is missing in billing
  address*), en één in *Manueel* door het domeinfilter. Het dagrapport van
  vandaag in de mailbox.

## Hoofdstukken

`0:00` Inleiding · `0:15` Het overzicht Stoqflow-orders · `0:50` Het dashboard ·
`1:10` Een fout lezen · `1:35` De vijf meest voorkomende fouten · `2:50` Opnieuw doorsturen ·
`3:05` Statusupdates en JSON-historiek · `3:35` Hulp vragen · `3:50` Samenvatting

## Draaiboek

| # | Tijd | Beeld | Voice-over | Tekst in beeld |
|---|---|---|---|---|
| 1 | 0:00–0:06 | Openingskaart. | — | **Opvolgen en fouten oplossen** |
| 2 | 0:06–0:15 | E-mail *dagelijks rapport*: verwerkte en mislukte overboekingen. | Elke ochtend krijgt u het dagrapport: wat gisteren naar Stoqflow ging, en wat niet. Hier ziet u hoe u de rest opvolgt in Odoo. | Begin bij het dagrapport |
| 3 | 0:15–0:50 | **Stoqflow → Orders**: lijst. Filters **Fout**, **In afwachting**, **Manueel**; groeperen op **Processcode** en op **Stoqflow-status**. Knoppen bovenaan: **Synchronisatie runnen**, **Haal hoeveelheden en status op**. | Stoqflow, Orders is uw werklijst: alle leveringen en ontvangsten die via Stoqflow lopen. Filter op Fout om te zien wat aandacht vraagt, of groepeer op processcode voor een totaalbeeld. Met de knoppen bovenaan stuurt u geselecteerde overboekingen opnieuw door, of haalt u hun status meteen op. | Stoqflow → Orders |
| 4 | 0:50–1:10 | **Stoqflow → Dashboard**: grafiek **Orders per dag**, daarna draaitabel met aantallen, verkoopprijs, kostprijs en marge. | Het dashboard toont hoeveel orders er per dag via Stoqflow gingen, met hun omzet en marge. Handig voor de opvolging van uw fulfilmentpartner. | Dashboard |
| 5 | 1:10–1:35 | Levering in *Fout* openen, tabblad **Stoqflow**: **Resultaat laatste synchronisatie** in rood met de lijst van fouten. Chatter met dezelfde fout. | Open een overboeking in fout. Op het tabblad Stoqflow staat bij Resultaat laatste synchronisatie precies wat er misliep. Als u de fouten ook in de chatter laat loggen, blijft de historiek bewaard. | Resultaat laatste synchronisatie |
| 6 | 1:35–1:55 | Fout *SKU not found in Stoqflow for product …* → product openen → **Synchroniseren met Stoqflow**. | Fout één: SKU niet gevonden in Stoqflow. Het product bestaat nog niet in Stoqflow, of heeft geen interne referentie. Synchroniseer of match het product, zoals in video 05. | 1. SKU niet gevonden |
| 7 | 1:55–2:10 | Fout *Street is missing in billing address* → contact openen → straat invullen. | Fout twee: een verplicht adresveld ontbreekt bij de klant of leverancier: naam, straat, postcode, gemeente of land. Vul het aan op het contact. | 2. Adres onvolledig |
| 8 | 2:10–2:25 | Fout *Multiple Stoqflow clients match this contact* → contact → **Matchen met Stoqflow** → venster om de juiste Stoqflow-klant te kiezen. | Fout drie: meerdere klanten in Stoqflow passen bij dit contact. Odoo maakt dan geen dubbel aan, maar laat u kiezen: klik op het contact op Matchen met Stoqflow en kies de juiste klant. | 3. Meerdere klanten gevonden |
| 9 | 2:25–2:38 | Melding *Not all items are in stock*, levering blijft *In afwachting*. Inzet: instelling **Volledige beschikbaarheid vereist**. | Vier: niet alles is op voorraad. Met Volledige beschikbaarheid vereist wacht Odoo tot alles in SQF ligt. Dat is geen fout: de levering vertrekt vanzelf zodra de voorraad er is. | 4. Niet op voorraad |
| 10 | 2:38–2:50 | Levering in *Manueel* (domeinfilter), en een waarschuwing *courier not linked* bij een verzonden order. | En vijf: een levering in Manueel valt buiten uw domeinfilter of is een backorder; stuur ze zelf door als dat de bedoeling is. Een waarschuwing over een vervoerder betekent dat een verzendmethode nog niet gekoppeld is, zie video 04. | 5. Manueel · vervoerder |
| 11 | 2:50–3:05 | Na de correctie: **Manueel synchroniseren** → resultaat groen, processcode *Verstuurd naar Stoqflow*. | Opgelost? Klik op Manueel synchroniseren. Lukt het, dan gaat de levering verder in de gewone flow, en begint de teller van de syncpogingen opnieuw. | Manueel synchroniseren |
| 12 | 3:05–3:20 | **Stoqflow → Statusupdates**: lijst met **In wachtrij geplaatst op**, filters *In afwachting*, *Fout*, knop **Nu verwerken**. | Komt een status niet door? In Stoqflow, Statusupdates ziet u elke wijziging die Odoo uit Stoqflow ophaalde, en of ze verwerkt is. Een update in fout kunt u hier opnieuw verwerken met Nu verwerken. | Statusupdates |
| 13 | 3:20–3:35 | **Stoqflow → JSON-historiek**: lijst met datum, richting, methode, endpoint en overboeking. Een regel openen. Callout: *JSON-payloads loggen* (ontwikkelaarsmodus, blok Debug). | De JSON-historiek toont de berichten tussen Odoo en Stoqflow, per overboeking. Die logging zet u in de ontwikkelaarsmodus aan bij Debug, alleen zolang u een probleem onderzoekt. | JSON-historiek |
| 14 | 3:35–3:50 | Ontwikkelaarsmodus, levering, tabblad Stoqflow: **Volledige Stoqflow-trace kopiëren** → plakken in een e-mail aan support. | Komt u er niet uit, klik dan in de ontwikkelaarsmodus op Volledige Stoqflow-trace kopiëren en stuur die naar Data Forge. Daarmee zien wij meteen wat er gebeurd is. | Hulp vragen: trace kopiëren |
| 15 | 3:50–3:55 | Stoqflow → Orders, filter *Fout*: lege lijst. | Een lege lijst met fouten: zo hoort het. | ✓ Geen fouten |
| 16 | 3:55–4:00 | Eindkaart (laatste video: verwijzing naar het overzicht en contact Data Forge). | Bedankt voor het kijken. | www.data-forge.be |

## Eindkaart

*Dit was de laatste video van de reeks. Alle video's: zie het overzicht. Vragen? www.data-forge.be*

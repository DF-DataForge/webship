# 04 — Synchronisatieregels: orders, klanten en vervoerders

* **Doel**: alle regels instellen die bepalen *wat* Odoo naar Stoqflow stuurt
  en *hoe*: ordersynchronisatie, standaardstatussen, domeinfilter, vervoerders
  en het matchen van klanten en leveranciers.
* **Doelpubliek**: Odoo-beheerder.
* **Duur**: ± 4:00
* **Klaarzetten**: de database uit video 03. In Odoo een verzendmethode
  *bpost* (Voorraad → Configuratie → Verzendmethoden). In Stoqflow minstens
  één vervoerder en één bestaande klant met btw-nummer (om het matchen te
  tonen).

## Hoofdstukken

`0:00` Inleiding · `0:15` Ordersynchronisatie · `1:00` Standaardstatussen ·
`1:15` Domeinfilter · `1:40` Weergave en genegeerde SKU's · `2:05` Vervoerders ·
`2:45` Klanten en leveranciers matchen · `3:30` Contacten zonder of met foutief e-mailadres ·
`3:50` Samenvatting

## Draaiboek

| # | Tijd | Beeld | Voice-over | Tekst in beeld |
|---|---|---|---|---|
| 1 | 0:00–0:06 | Openingskaart. | — | **Synchronisatieregels** |
| 2 | 0:06–0:15 | **Stoqflow → Instellingen**, scrollen over de blokken. | Alle regels van de koppeling staan op één pagina: Stoqflow, Instellingen. We lopen ze van boven naar onder door. | Stoqflow → Instellingen |
| 3 | 0:15–0:35 | Blok **Algemene instellingen**, **Ordersynchronisatie**: **Orders synchroniseren** aanvinken. Daarna **Volledige beschikbaarheid vereist**. | Vink eerst Orders synchroniseren aan: dat is de hoofdschakelaar voor leveringen en inkooporders. Met Volledige beschikbaarheid vereist stuurt Odoo een levering pas door als alle producten op voorraad zijn in de Stoqflow-locatie. Anders blijft ze in afwachting. | Orders synchroniseren |
| 4 | 0:35–1:00 | **Automatisch backorder aanmaken bij voltooiing**, **Terugvallen op het contact van de verkooporder voor telefoon/e-mail**, **Order/inkooporder in Stoqflow annuleren wanneer de overboeking geannuleerd wordt** aanvinken. | Met Automatisch backorder aanmaken valideert Odoo een levering ook als Stoqflow niet alles kon leveren, en maakt het een backorder voor de rest. Zonder dit vinkje blijft zo'n levering open. Terugvallen op het contact van de verkooporder vult telefoon en e-mail aan als het leveradres die niet heeft. En met de laatste optie annuleert Odoo het order in Stoqflow als u de levering in Odoo annuleert. | Backorder · contactgegevens · annuleren |
| 5 | 1:00–1:15 | **Standaardstatussen**: **Standaard Stoqflow-orderstatus** = *Klaar om te picken*; **Standaard Stoqflow-status inkooporder** = *Besteld*. Keuzelijsten openklappen. | De standaardstatussen bepalen hoe een nieuw order in Stoqflow binnenkomt. Klaar om te picken betekent: het magazijn mag meteen beginnen. Kies Concept of Gepauzeerd als u orders eerst in Stoqflow wilt nakijken. Inkooporders komen standaard binnen als Besteld. | Klaar om te picken · Besteld |
| 6 | 1:15–1:40 | **Domeinfilter**: met de domeineditor een regel toevoegen, bv. *Verkooporder → Website is ingesteld*. Het veld **Domeinregel** toont de tekst. | Wilt u maar een deel van de leveringen automatisch doorsturen, gebruik dan het domeinfilter. Hier sturen we alleen webshoporders automatisch door. Leveringen die niet aan het filter voldoen krijgen de processcode Manueel: u stuurt ze zelf door. Laat het leeg om alles door te sturen. | Domeinfilter (optioneel) |
| 7 | 1:40–2:05 | **Weergave**: **Tabblad Pakketten weergeven** en **Tabblad Pickanalyse weergeven**. Daarna **Genegeerde SKU's**: `VERPAKKING-A` intypen. | Bij Weergave kiest u welke extra tabbladen op de levering verschijnen: de pakketten met trackinglinks en de pickanalyse. Bij Genegeerde SKU's zet u producten die alleen in Stoqflow bestaan, zoals verpakkingsmateriaal. Odoo slaat die over bij het ophalen van orders, zonder waarschuwing. | Pakketten · pickanalyse · genegeerde SKU's |
| 8 | 2:05–2:25 | Blok **Vervoerders**: **Vervoerder koppelen vanuit Stoqflow** aanvinken, klik **Vervoerders laden uit Stoqflow**, daarna **Stoqflow-vervoerders beheren**: lijst met **Naam** en **Code**. | In het blok Vervoerders laadt u de vervoerders uit Stoqflow. Met Vervoerder koppelen vanuit Stoqflow neemt Odoo de vervoerder over die Stoqflow voor een order gekozen heeft. | Vervoerders laden |
| 9 | 2:25–2:45 | Voorraad → Configuratie → **Verzendmethoden** → *bpost*: veld **Stoqflow-vervoerder** = *bpost*. Opslaan. | Koppel daarna elke verzendmethode in Odoo aan een Stoqflow-vervoerder. Ontbreekt een koppeling, dan toont de levering een waarschuwing in het resultaat van de synchronisatie. | Verzendmethode ↔ Stoqflow-vervoerder |
| 10 | 2:45–3:10 | Blok **Contacten matchen**: **Matchingsequentie** openklappen: *Btw → e-mail*, *Enkel btw*, *Enkel e-mail*, *E-mail → btw*. *Btw → e-mail* kiezen. **Klant matchen bij het synchroniseren van een order** aanvinken. | Bij het eerste order van een klant zoekt Odoo eerst of die klant al bestaat in Stoqflow, zodat er geen dubbels ontstaan. De matchingsequentie bepaalt hoe: eerst op btw-nummer en dan op e-mail, bijvoorbeeld. Vink Klant matchen bij het synchroniseren aan om dat automatisch te doen. Laat u de sequentie leeg, dan maakt Odoo altijd een nieuwe klant aan. | Eerst zoeken, dan aanmaken |
| 11 | 3:10–3:30 | Blok **Leveranciers matchen**: dezelfde keuze, **Leverancier matchen bij het synchroniseren van een inkooporder** aanvinken. | Voor leveranciers werkt het net zo, bij het doorsturen van een inkooporder. | Leveranciers: idem |
| 12 | 3:30–3:50 | Blok **Opties voor contactoverdracht**: **Contacten zonder e-mail toelaten** en **E-mail weglaten indien niet geldig**. Inzet: contact met adres; callout *naam, straat, postcode, gemeente, land verplicht*. | Stoqflow weigert contacten zonder geldig e-mailadres. Kies hier of Odoo zulke contacten toch doorstuurt, en of een ongeldig e-mailadres gewoon weggelaten wordt. Naam, straat, postcode, gemeente en land zijn altijd verplicht. | E-mail · verplichte adresvelden |
| 13 | 3:50–3:55 | **Opslaan** bovenaan. | Vergeet niet op te slaan. | Opslaan |
| 14 | 3:55–4:00 | Eindkaart. | — | Volgende: producten klaarzetten |

## Aandachtspunten voor de opname

* Klanten en leveranciers worden automatisch aangemaakt bij het eerste order;
  manueel doorsturen kan op het contact zelf (tabblad **Stoqflow**, knoppen
  **Matchen met Stoqflow** en **Synchroniseren met Stoqflow**). Toon dat kort
  als u tijd over hebt, of verwijs naar video 10.
* Vindt Odoo meerdere Stoqflow-klanten die passen, dan stuurt het order niet
  door en vraagt het om de juiste klant manueel te kiezen via **Matchen met
  Stoqflow** op het contact.

## Eindkaart

*Regels ingesteld? Bekijk video 05: producten klaarzetten voor Stoqflow.*

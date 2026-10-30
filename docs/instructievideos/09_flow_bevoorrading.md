# 09 — Flow: bevoorraden vanuit het eigen magazijn

* **Doel**: goederen uit het eigen magazijn (bv. zelf geassembleerde
  producten) naar het Stoqflow-magazijn sturen met een bevoorradingsroute, zodat
  Stoqflow de zending verwacht.
* **Doelpubliek**: logistiek, productie.
* **Duur**: ± 3:15
* **Klaarzetten**: demodatabase met sandboxsleutels. Magazijn *Stoqflow
  Fulfilment* met **Bevoorraden vanuit** *Skate Workshop H800* (video 03).
  Product *Woody's Cruiser Complete 8.25"* op voorraad in *H800/Voorraad*, met de
  bevoorradingsroute aangevinkt.

## Hoofdstukken

`0:00` Wanneer gebruikt u dit? · `0:20` De route op het product · `0:45` Bevoorrading starten ·
`1:15` Twee overboekingen · `1:45` Stap 1: verzenden uit het eigen magazijn ·
`2:10` Stap 2: aankondigen en ontvangen in Stoqflow · `2:55` Samenvatting

## Draaiboek

| # | Tijd | Beeld | Voice-over | Tekst in beeld |
|---|---|---|---|---|
| 1 | 0:00–0:06 | Openingskaart. | — | **Bevoorraden vanuit het eigen magazijn** |
| 2 | 0:06–0:20 | Schema: *H800/Voorraad* → *Transit* → *SQF/Voorraad*. Stap 1 grijs (*enkel Odoo*), stap 2 in kleur (*Inkooporder in Stoqflow*). | Niet alles komt rechtstreeks van een leverancier. Bij Woody's worden de complete boards in de eigen werkplaats gemonteerd en daarna naar Stoqflow gestuurd. Ook die zending moet Stoqflow verwachten. | Eigen magazijn → Stoqflow |
| 3 | 0:20–0:45 | Product *Woody's Cruiser Complete 8.25"*, tabblad Voorraad: routes *Productie* en *Stoqflow Fulfilment: Product leveren vanaf Skate Workshop H800* aangevinkt. | Op het product vinkt u de bevoorradingsroute aan die Odoo maakte toen u bij het Stoqflow-magazijn Bevoorraden vanuit instelde. Hier staat ook Productie aan, want de werkplaats maakt de boards zelf. | Route op het product |
| 4 | 0:45–1:15 | Voorraad → Bewerkingen → **Aanvullen**: regel voor het product op *SQF/Voorraad*, route = bevoorradingsroute, **Te bestellen** 10 → **Bestellen**. (Alternatief: een aanvulregel met min/max.) | Start de bevoorrading vanuit het scherm Aanvullen: kies het product voor de locatie SQF/Voorraad, de bevoorradingsroute en het aantal, en klik op Bestellen. Met een aanvulregel met minimum en maximum doet Odoo dat zelf, zodra de voorraad in Stoqflow te laag wordt. | Aanvullen of aanvulregel |
| 5 | 1:15–1:45 | Voorraad → Overboekingen, filter op het product: twee nieuwe overboekingen. *H800/…* van *H800/Voorraad* naar *Transit*: geen tabblad Stoqflow (processcode *Niet van toepassing*). *SQF/IN/…* van *Transit* naar *SQF/Voorraad*: tabblad Stoqflow, processcode *In afwachting*, **Object in Stoqflow** *Inkooporder*. | Odoo maakt twee overboekingen. De eerste, van de werkplaats naar transit, raakt Stoqflow niet: die handelt u gewoon in Odoo af. De tweede, van transit naar SQF, komt in de Stoqflow-locatie aan, en wordt dus een inkooporder in Stoqflow, net als bij een leverancier. | Twee overboekingen |
| 6 | 1:45–2:10 | De werkplaatsoverboeking openen → **Valideren**. De tweede overboeking wordt *Gereed om te verwerken*. | In de werkplaats pakt u de boards in en valideert u de eerste overboeking, zoals altijd. Daarmee staat de tweede klaar. | Stap 1: valideren in Odoo |
| 7 | 2:10–2:35 | Tweede overboeking: veld **Contact** gemarkeerd, **Manueel synchroniseren** → link naar de inkooporder in Stoqflow en de **Status in Stoqflow**. | De geplande taak kondigt de tweede overboeking aan in Stoqflow. Het contact op deze overboeking wordt de leverancier in Stoqflow; zorg dat daar uw eigen bedrijf of werkplaats staat, met een volledig adres. | Stap 2: aangekondigd in Stoqflow |
| 8 | 2:35–2:55 | Dia *Wat er in Stoqflow gebeurt*: inkooporder op *Voltooid* met 10 ontvangen. Odoo: tweede overboeking **Voltooid**, voorraad in *SQF/Voorraad* +10. | Komen de boards toe, dan telt Stoqflow ze en voltooit de inkooporder. Odoo valideert de tweede overboeking met de getelde aantallen, en de boards zijn meteen verkoopbaar via Stoqflow. | Ontvangen in SQF |
| 9 | 2:55–3:09 | Schema van scène 2, met vinkjes. Daarna kort: verkooporder voor een board → levering uit SQF (verwijzing naar video 07). | Kortom: wat uit uw eigen magazijn vertrekt, regelt u in Odoo; wat in Stoqflow aankomt, kondigt Odoo aan. En verkocht wordt er daarna vanuit Stoqflow, zoals in video 07. | Odoo verzendt · Stoqflow ontvangt |
| 10 | 3:09–3:15 | Eindkaart. | — | Volgende: retours, backorders en voorraad |

## Aandachtspunten voor de opname

* Valideer de tweede overboeking (*Transit → SQF/Voorraad*) nooit zelf: ze wordt
  gevalideerd door de synchronisatie, net als een gewone ontvangst.

## Eindkaart

*Bekijk video 10: retours, backorders en voorraad.*

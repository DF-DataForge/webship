# 05 — Producten klaarzetten voor Stoqflow

* **Doel**: producten correct naar Stoqflow sturen of koppelen aan producten
  die er al zijn, en producten uitsluiten die Stoqflow niet nodig heeft.
* **Doelpubliek**: productbeheer, Odoo-beheerder.
* **Duur**: ± 3:00
* **Klaarzetten**: demodatabase met sandboxsleutels. In Stoqflow bestaat
  *WSS-BEANIE* al (om het matchen te tonen), *WSS-TEE* nog niet. Een
  component (bv. *Truck 139 mm Raw*) met **Dit product niet synchroniseren**.
  Varianten zijn ingeschakeld (Voorraad → Instellingen).

## Hoofdstukken

`0:00` Inleiding · `0:15` De SKU is de sleutel · `0:40` Het tabblad Stoqflow ·
`1:25` Matchen of synchroniseren · `2:00` Varianten en meerdere producten tegelijk ·
`2:30` Overzicht: Producten in Stoqflow · `2:50` Samenvatting

## Draaiboek

| # | Tijd | Beeld | Voice-over | Tekst in beeld |
|---|---|---|---|---|
| 1 | 0:00–0:06 | Openingskaart. | — | **Producten klaarzetten voor Stoqflow** |
| 2 | 0:06–0:15 | Stoqflow-app: productlijst met SKU's. | Stoqflow moet elk product kennen voordat het een order kan picken. In deze video zetten we de producten klaar. | Eerst producten, dan orders |
| 3 | 0:15–0:40 | Odoo: product *Woody's Beanie*, veld **Interne referentie** `WSS-BEANIE` inzoomen. Callout: *Interne referentie = SKU in Stoqflow*. | De sleutel tussen Odoo en Stoqflow is de SKU: in Odoo is dat de interne referentie van het product. Zonder interne referentie kan Odoo het product niet doorsturen, en een order met zo'n product wordt geweigerd. Zorg dus dat elk product dat Stoqflow verzendt een unieke interne referentie heeft. | Interne referentie = SKU |
| 4 | 0:40–1:05 | Tabblad **Stoqflow** op het product: bovenaan **Dit product niet synchroniseren**, daarna **Productstatus** met link, **Laatste synchronisatie** en **Synchronisatiestatus**. | Op elk product staat een tabblad Stoqflow. Bovenaan ziet u de status: de link naar het product in Stoqflow, wanneer het laatst gesynchroniseerd is en met welk resultaat. | Tabblad Stoqflow |
| 5 | 1:05–1:25 | Groepen **Stoqflow-productdetails**: **Algemeen** (Stoqflow-type, Stoqflow-merk, Voorraadtype), **Voorraadniveaus**, **Afmetingen**, **Handel & douane** (HS-code, Land van oorsprong), **Vlaggen** (Breekbaar, Koelketen, Gevaarlijk), **Controles** (Vervaldata, Batches, Serienummers). | Daaronder vult u de gegevens in die Stoqflow nodig heeft: het merk en het voorraadtype, minimum- en maximumvoorraad, afmetingen, de HS-code en het land van oorsprong voor de douane, en vlaggen zoals breekbaar of koelketen. Bij Controles kiest u of het magazijn vervaldata, batches of serienummers moet registreren. | Productdetails voor het magazijn |
| 6 | 1:25–1:45 | *Woody's Beanie*: klik **Matchen met Stoqflow** → status *gekoppeld*, link verschijnt. | Bestaat het product al in Stoqflow? Klik dan op Matchen met Stoqflow. Odoo zoekt het product op SKU en koppelt het, zonder iets te wijzigen in Stoqflow. | Bestaat al → Matchen |
| 7 | 1:45–2:00 | *Woody's Logo Tee* (variant Black / M): klik **Synchroniseren met Stoqflow** → link en *Laatste synchronisatie* gevuld. Tweede tabblad: product verschijnt in Stoqflow. | Is het product nieuw, klik dan op Synchroniseren met Stoqflow. Odoo maakt het aan in Stoqflow, met naam, SKU, barcode, prijzen en de details van daarnet. Een latere klik werkt het product bij. | Nieuw → Synchroniseren |
| 8 | 2:00–2:15 | Component *Truck 139 mm Raw*: **Dit product niet synchroniseren** aangevinkt. Callout: *blijft in het eigen magazijn*. | Producten die nooit in het Stoqflow-magazijn komen, zoals onderdelen voor uw eigen productie, vinkt u aan als Dit product niet synchroniseren. Odoo slaat ze over, ook op orders. | Nooit naar Stoqflow |
| 9 | 2:15–2:30 | Voorraad → Producten → **Productvarianten**, lijst filteren op *Clothing*, alles selecteren → knoppen **Syncen met Stoqflow** en **Producten matchen met Stoqflow** bovenaan. | Een product met varianten synchroniseert u per variant: elke maat en kleur is in Stoqflow een apart product met een eigen SKU. In de lijst met productvarianten selecteert u er meerdere tegelijk en klikt u op Syncen met Stoqflow of Producten matchen met Stoqflow. | Varianten: per stuk of in bulk |
| 10 | 2:30–2:50 | **Stoqflow → Rapporten → Producten in Stoqflow**, filters **Gesynchroniseerd**, **Synchronisatiefouten**, **Nooit gesynchroniseerd**, **Uitgesloten van synchronisatie**. | Het overzicht Producten in Stoqflow toont alle producten met hun status. Met de filters vindt u snel wat nog nooit gesynchroniseerd is of een fout gaf. Los die op voor het eerste order. | Producten in Stoqflow |
| 11 | 2:50–2:55 | Rapport, filter *Synchronisatiefouten* leeg. | Geen fouten meer? Dan is alles klaar voor de eerste orders. | ✓ Klaar voor orders |
| 12 | 2:55–3:00 | Eindkaart. | — | Volgende: automatisering en bewaking |

## Aandachtspunten voor de opname

* Krijgt een order de fout *SKU not found in Stoqflow*, dan is het product
  niet gesynchroniseerd of gematcht. Dat komt terug in video 11.
* Een producttemplate met meerdere varianten kan niet vanaf de template
  gesynchroniseerd worden (melding *Product has multiple variants*): werk dan
  vanuit de variant of de variantenlijst, zoals in scène 9.

## Eindkaart

*Producten klaar? Bekijk video 06: geplande taken, meldingen en dagrapport.*

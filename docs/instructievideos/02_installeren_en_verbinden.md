# 02 — Installeren en verbinden met Stoqflow

* **Doel**: de module installeren, de API-sleutels van Stoqflow invullen, de
  verbinding testen en de bedrijven, merken, shops en magazijnen van Stoqflow
  in Odoo laden.
* **Doelpubliek**: Odoo-beheerder, partner die de installatie doet.
* **Duur**: ± 3:00
* **Klaarzetten**: een **lege** Odoo 19-database met Verkoop, Inkoop en
  Voorraad; de repository `webship` op de server (of als submodule op
  Odoo.sh); een Stoqflow-sandboxaccount met API-sleutel (Key en Secret).
  Gebruiker met beheerdersrechten.

## Hoofdstukken

`0:00` Inleiding · `0:15` De module op de server · `0:45` Installeren in Odoo ·
`1:15` API-sleutels en verbinding testen · `2:05` Bedrijven, merken en magazijnen laden ·
`2:45` Samenvatting

## Draaiboek

| # | Tijd | Beeld | Voice-over | Tekst in beeld |
|---|---|---|---|---|
| 1 | 0:00–0:06 | Openingskaart. | — | **Installeren en verbinden met Stoqflow** |
| 2 | 0:06–0:15 | Lege Odoo-database, startscherm met Verkoop, Inkoop en Voorraad. | In deze video installeren we de Stoqflow-koppeling en verbinden we Odoo met uw Stoqflow-account. Reken op een tiental minuten. | Wat heeft u nodig? Odoo-beheerder · Stoqflow-API-sleutel |
| 3 | 0:15–0:45 | Bestandsverkenner of GitHub: repository `webship` met de mappen `18.0`, `19.0`, `20.0`. Inzoomen op `19.0/webship`. Daarna het configuratiebestand met de regel `addons_path = …,/opt/odoo/webship/19.0` (of het Odoo.sh-scherm met de submodule). | De module staat in één repository, met een map per Odoo-versie. Kies de map die past bij uw versie, hier 19.0, en voeg die toe aan het addons-pad van uw Odoo-server. Op Odoo.sh voegt u de repository toe als submodule. De module gebruikt alleen standaardapps: Verkoop, Inkoop, Voorraad en Levering. | Map per versie: 18.0 · 19.0 · 20.0 |
| 4 | 0:45–1:00 | Instellingen → **Ontwikkelaarsmodus activeren**. Apps → **Apps-lijst bijwerken** → **Bijwerken**. | Herstart Odoo. Zet daarna de ontwikkelaarsmodus aan en werk de lijst met apps bij, zodat Odoo de nieuwe module ziet. | Apps-lijst bijwerken |
| 5 | 1:00–1:15 | Apps, zoeken op "Stoqflow". Kaart **Koppeling Stoqflow by Data Forge** → **Activeren**. Na het laden verschijnt de app **Stoqflow** op het startscherm. | Zoek op Stoqflow en klik bij Koppeling Stoqflow by Data Forge op Activeren. Na de installatie staat de app Stoqflow op uw startscherm. | Koppeling Stoqflow by Data Forge |
| 6 | 1:15–1:30 | Stoqflow-app in de browser (sandbox): instellingen → API-sleutels, een sleutel aanmaken. Key en Secret worden getoond (geblurd). | Maak in Stoqflow een API-sleutel aan, of vraag die aan uw Stoqflow-contactpersoon. U krijgt een Key en een Secret. Bewaar het Secret goed: u ziet het maar één keer. | API-sleutel in Stoqflow |
| 7 | 1:30–1:55 | Odoo: **Stoqflow → Instellingen**, blok **Login**. Velden invullen: **Key**, **Secret** (geblurd), **Base Url** `https://api.stoqflow.com/`, **App Url** `https://app.stoqflow.com/`. **Opslaan**. | Ga in Odoo naar Stoqflow, Instellingen. In het blok Login vult u de Key en het Secret in, de Base URL van de API en de App URL. Die laatste gebruikt Odoo om klikbare links naar orders en producten in Stoqflow te maken. Sla op. | Key · Secret · Base Url · App Url |
| 8 | 1:55–2:05 | Klik **Verbinding testen** → groene melding *Status webservice*. Daarna kort: een foute sleutel geeft een rode melding. | Klik op Verbinding testen. Een groene melding betekent dat Odoo Stoqflow bereikt. Een rode melding toont wat er misloopt, bijvoorbeeld een verkeerde sleutel of URL. | Verbinding testen |
| 9 | 2:05–2:30 | Blok **Algemene instellingen**, instelling **Merk & Shop**: klik **Bedrijven / merken / magazijnen laden**. | Nu laden we de structuur van uw Stoqflow-account in Odoo. Klik bij Merk en Shop op Bedrijven, merken, magazijnen laden. Odoo haalt uw bedrijven, merken, shops en magazijnen op. Dat is nodig voordat er orders verstuurd kunnen worden. | Bedrijven / merken / magazijnen laden |
| 10 | 2:30–2:45 | Velden **Standaard Stoqflow-merk** en **Standaard Stoqflow-shop** openklappen en kiezen. **Opslaan**. | Kies daarna het standaardmerk en de standaardshop. Elk order en elk product dat Odoo naar Stoqflow stuurt, komt in die shop terecht. | Standaardmerk en -shop |
| 11 | 2:45–2:54 | Overzicht van het blok **Login** en **Merk & Shop**, ingevuld. | Odoo en Stoqflow praten nu met elkaar. Er wordt nog niets verstuurd: eerst richten we het magazijn en de routes in. | ✓ Geïnstalleerd · ✓ Verbonden |
| 12 | 2:54–3:00 | Eindkaart. | — | Volgende: magazijn, locatie en routes |

## Aandachtspunten voor de opname

* Blur **Key** en **Secret** in de montage, ook in de Stoqflow-app.
* De geplande taken van de module staan na de installatie uit (behalve
  *Reclassify Stoqflow object types*). Ze komen aan bod in video 06; zo
  wordt er niets verstuurd zolang de configuratie niet af is.

## Eindkaart

*Verbonden? Bekijk video 03: magazijn, locatie en routes.*

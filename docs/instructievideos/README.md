# Instructievideo's — Koppeling Stoqflow by Data Forge

Scripts voor een reeks uitlegvideo's over de module **Koppeling Stoqflow by
Data Forge** (`webship`): installeren, configureren en de basisflows tussen
Odoo en Stoqflow (Webship). Elke video behandelt één thema of één flow
volledig, van begin tot eind; de duur volgt wat er te tonen is (1:30 tot
4:30). Alle schermteksten, knoppen en menu's in de scripts komen uit de module
zelf (Odoo 19.0, taal Nederlands; geldt ook voor 20.0).

## Reeks A — Installatie en configuratie

| #  | Video | Duur | Voor wie |
|----|-------|------|----------|
| 01 | [De Stoqflow-koppeling in een notendop](01_overzicht.md) | 1:30 | iedereen, prospecten |
| 02 | [Installeren en verbinden met Stoqflow](02_installeren_en_verbinden.md) | 3:00 | Odoo-beheerder |
| 03 | [Magazijn, locatie en routes](03_magazijn_locatie_routes.md) | 4:00 | Odoo-beheerder, logistiek |
| 04 | [Synchronisatieregels: orders, klanten en vervoerders](04_synchronisatieregels.md) | 4:00 | Odoo-beheerder |
| 05 | [Producten klaarzetten voor Stoqflow](05_producten.md) | 3:00 | productbeheer |
| 06 | [Automatisering en bewaking](06_automatisering_en_bewaking.md) | 3:30 | Odoo-beheerder |

## Reeks B — Basisflows met Stoqflow

| #  | Video | Duur | Voor wie |
|----|-------|------|----------|
| 07 | [Van verkooporder tot uitgaande levering](07_flow_verkooporder.md) | 4:30 | verkoop, logistiek |
| 08 | [Van inkooporder tot inkomende levering](08_flow_inkooporder.md) | 3:45 | aankoop, logistiek |
| 09 | [Bevoorraden vanuit het eigen magazijn](09_flow_bevoorrading.md) | 3:15 | logistiek, productie |
| 10 | [Retours, backorders en voorraad](10_retours_backorders_voorraad.md) | 4:00 | logistiek |
| 11 | [Opvolgen en fouten oplossen](11_opvolgen_en_fouten.md) | 4:00 | logistiek, Odoo-beheerder |

Reeks A zet de koppeling op, reeks B toont wat er daarna met elk document
gebeurt. Wie de module alleen gebruikt (verkoop, aankoop, magazijn) kan met
video 01 en reeks B starten. Video 03 is de sleutel tot de flows: daar staat
welke route welk Stoqflow-document maakt.

## Opbouw van elk script

* **Kop** — doel, doelpubliek, geschatte duur en wat je klaarzet vóór de opname.
* **Hoofdstukken** — tijdcodes per onderdeel, om als hoofdstukken (bv. op
  YouTube of in het leerplatform) bij de video te zetten.
* **Draaiboek** — per scène een tijdcode, wat er in **beeld** komt
  (schermacties, klikken, inzoomen), de **voice-over** en de **tekst in beeld**
  (titel of ondertitel als overlay).
* **Eindkaart** — afsluitende tekst en verwijzing naar de volgende video.

## Conventies

* **Taal**: Nederlands (Vlaams), u-vorm in de voice-over, korte zinnen.
  Knoppen, menu's en velden staan **vet**, precies zoals ze in Odoo verschijnen
  (Nederlandse vertaling uit `i18n/nl.po` van de module).
* **Knopnamen nakijken**: de labels van de module zelf liggen vast, maar de
  standaard Odoo-labels (magazijninstellingen, knoppen op verkoop- en
  inkooporders) vertaalt Odoo per versie anders. Loop ze vóór de opname na in
  de eigen database en pas het script aan waar ze afwijken. Enkele labels van
  de module zijn nog niet vertaald en staan in het Engels in de scripts
  (*Fetch returns from Stoqflow*, *Reclassify Stoqflow object types*,
  **Stoqflow company ID**): zo verschijnen ze ook op het scherm.
* **Tempo**: ± 130 woorden per minuut. De tijdcodes zijn richtwaarden; de
  voice-over bepaalt de uiteindelijke duur.
* **Opname**: schermopname op 1920 × 1080, browser op 100 %, Odoo-menubalk
  zichtbaar. Muisklikken accentueren (cirkel), inzoomen op het veld of de
  knop die genoemd wordt. Rustige achtergrondmuziek, uit tijdens de
  voice-over-pieken.
* **Stoqflow-kant**: waar het script de Stoqflow-app toont, gebruik een
  sandbox-account. Nooit echte API-sleutels in beeld: blur het veld
  **Secret** (en **Key**) in de montage.

## Huisstijl

* **Logo**: Data Forge-logo op de openings- en eindkaart
  (`assets/dataforge_logo.png`, vierkante versie `assets/dataforge_logo_square.png`),
  met het Stoqflow-icoon (`assets/stoqflow_logo.png`) als tweede merk op de
  openingskaart.
* **Kleuren** (uit het logo): teal `#2ED3B7` → blauw `#2B8FE3` als verloop,
  donkere achtergrond `#0E1B2C`, tekst wit.
* **Lettertype**: Inter Display (titels) en Inter (ondertitels).
* **Kaarten**: elke video krijgt een openingskaart (reeks, nummer, titel) en een
  eindkaart (volgende video). Ze worden gegenereerd door
  [`tools/make_cards.py`](tools/make_cards.py) en staan in `cards/`:

  | Bestand | Inhoud |
  |---|---|
  | `cards/NN_open.jpg` | openingskaart, 1920 × 1080 |
  | `cards/NN_eind.jpg` | eindkaart, 1920 × 1080 |
  | `cards/NN_open.mp4`, `cards/NN_eind.mp4` | dezelfde kaart als clip van 5 s met in- en uitfaden, klaar voor de montage |
  | `cards/ondertitel_balk.png` | transparante ondertitelbalk voor *Tekst in beeld* |

  Opnieuw genereren na een wijziging van titels of logo (Chromium en ffmpeg
  nodig):

  ```bash
  python3 docs/instructievideos/tools/make_cards.py
  ```

  Montage: openingskaart (5 s, met korte muziekintro) → video → eindkaart
  (5 s). De *Tekst in beeld* uit het draaiboek zet u op de ondertitelbalk
  (wit, Inter SemiBold, ± 44 px), linksonder.

## Ondertitels

`ondertitels/NN.srt` bevat de voice-over van elk script als ondertitels, met
de tijdcodes uit het draaiboek. Na de opname schuift of rekt u ze in de
montage gelijk met de echte voice-over. Opnieuw genereren na een wijziging in
een script:

```bash
python3 docs/instructievideos/tools/make_subtitles.py
```

Ondertitels zijn geen luxe: veel mensen kijken zonder geluid (open
kantoor, magazijn), en ze maken de video doorzoekbaar.

## Voice-over: advies

**Wie spreekt in?** Eén vaste stem voor de hele reeks, iemand die de
module kent en vlot Vlaams-Nederlands spreekt. Een echte stem werkt beter dan
een computerstem (TTS) voor uitleg: de klemtonen vallen op de juiste
knopnamen. Kiest u toch voor TTS, neem dan een *nl-BE*-stem en laat de
knopnamen en vaktermen eerst proeflezen.

**Werkwijze: eerst de stem, dan het beeld.**

1. Lees het hele script een keer hardop met een stopwatch. Zinnen waar u over
   struikelt, herschrijft u nu: wat lastig leest, klinkt ook lastig.
2. Neem de voice-over op **per scène** (één bestand per rij in het
   draaiboek). Zo herneemt u een fout zonder alles opnieuw te doen.
3. Neem daarna het scherm op terwijl u de opgenomen stem afspeelt, en klik
   in het ritme van de stem. Zo hoeft u in de montage niet te knippen in
   klikken of te wachten op de stem.
4. Laat na elke scène ± 0,5 s stilte: dat geeft adem en ruimte voor een
   overgang.

**Opname**

* Een USB-microfoon (dynamisch of condensator) op 15 à 20 cm, met popfilter
  of schuimkap. Geen laptopmicrofoon of headset met ingebouwde microfoon.
* Een kleine kamer met zachte materialen (gordijnen, kasten vol, tapijt);
  geen lege vergaderzaal. Telefoon op stil, ventilatie en airco uit.
* Opnemen in WAV, 48 kHz / 24-bit. Elke opnamesessie met dezelfde microfoon,
  afstand en instellingen, zodat alle video's hetzelfde klinken.
* Neem 10 s stilte op aan het begin: daarmee werkt de ruisonderdrukking
  achteraf het best.

**Spreken**

* Spreek alsof u het aan één collega naast u uitlegt, niet alsof u voorleest.
  Een glimlach hoort u.
* Tempo ± 130 woorden per minuut: trager dan u denkt. Een korte pauze na
  elke knopnaam laat de kijker zoeken waar u klikt.
* Leg de klemtoon op de **vetgedrukte** knop- en menunamen; zeg ze exact zoals
  ze op het scherm staan.
* Uitspraak, vast voor de hele reeks: *Stoqflow* = "stok-flow", *Odoo* =
  "oo-doo", *SKU* = "es-kaa-uu", *Data Forge* = Engels uitgesproken, *backorder*
  = Engels uitgesproken.
* Zeg getallen en codes zoals de kijker ze ziet: "SQF-schuine-streep-Stock"
  hoeft niet, "de locatie SQF Stock" volstaat.

**Nabewerking**

* Volgorde: ruisonderdrukking (licht), hoogdoorlaatfilter op ± 80 Hz,
  lichte compressie, de-esser, dan normaliseren naar **-16 LUFS** (−14 LUFS
  voor YouTube), pieken onder −1 dBTP.
* Achtergrondmuziek op ± −25 dB onder de stem, met *ducking* (muziek zakt
  automatisch weg tijdens het spreken). Op de openings- en eindkaart mag ze
  luider.
* Gratis en voldoende: Audacity (opname en nabewerking) of de audiotools van
  DaVinci Resolve; Adobe Podcast Enhance kan een minder goede opname redden.

## Demodata (dezelfde in alle video's)

Gebruik de demodatabase **Woody's Skate Supply** (module
`19.0/webship_demo_skateshop`, zie de README in de root van deze repository):
een lege Odoo 19-database waarin die module geïnstalleerd is. Ze bevat alles
wat de video's tonen:

* **Magazijnen**: `H800` Skate Workshop H800 (eigen magazijn, assemblage) en
  `SQF` Stoqflow Fulfilment (de locatie `SQF/Stock` is een Stoqflow-locatie).
* **Producten**: kleding met SKU (`WSS-TEE`, `WSS-HOOD`, `WSS-BEANIE`,
  `WSS-SOCKS`), componenten met **Dit product niet synchroniseren**, complete
  boards met een bevoorradingsroute H800 → SQF.
* **Contacten**: klanten Lotte Peeters, Jonas de Vries, Emma Janssens,
  Concrete Wave Skateshop (B2B); leverancier ThreadWorks Apparel Lda.
* **Openstaande documenten**: een inkooporder kleding, een bevoorrading van
  complete boards en webshop- en B2B-orders, allemaal met processcode
  *In afwachting*.

Voor video 02 heb je daarnaast een **lege** database nodig (installatie vanaf
nul) en Stoqflow-sandboxsleutels; video 03 kan in die lege database of in de
demodatabase (die alles al ingericht heeft: ideaal om te vergelijken). Zet
vóór de flowvideo's (07 tot en met 11) dezelfde sandboxsleutels in de
demodatabase, laad de bedrijven, merken en magazijnen, koppel `SQF/Stock` aan
het Stoqflow-magazijn en synchroniseer de kledingproducten, zodat de flows
echt doorlopen.

Bronnen: de module-README (`README.md` in de root), de helpteksten in
**Stoqflow → Instellingen** en `19.0/webship/docs/`.

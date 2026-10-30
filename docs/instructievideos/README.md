# Instructievideo's — Koppeling Stoqflow by Data Forge

Een reeks van 11 uitlegvideo's (samen ± 31 minuten) over de module
**Koppeling Stoqflow by Data Forge** (`webship`): installeren, configureren en
de basisflows tussen Odoo en Stoqflow (Webship). Elke video behandelt één
thema of één flow volledig, van begin tot eind.

De video's zijn opgenomen in **Odoo 20**, in het Nederlands, in de
demodatabase *Woody's Skate Supply*, met de Vlaamse computerstem *Dena*,
tekst in beeld, openings- en eindkaarten in de Data Forge-huisstijl en
ingebouwde ondertitels. Ze staan in [`video/`](video/); per video staat het
script (draaiboek) hieronder gelinkt.

## Reeks A — Installatie en configuratie

| #  | Video | Script | Duur | Voor wie |
|----|-------|--------|------|----------|
| 01 | [De Stoqflow-koppeling in een notendop](video/01_overzicht.mp4) | [script](01_overzicht.md) | 1:19 | iedereen, prospecten |
| 02 | [Installeren en verbinden met Stoqflow](video/02_installeren_en_verbinden.mp4) | [script](02_installeren_en_verbinden.md) | 2:42 | Odoo-beheerder |
| 03 | [Magazijn, locatie en routes](video/03_magazijn_locatie_routes.mp4) | [script](03_magazijn_locatie_routes.md) | 3:22 | Odoo-beheerder, logistiek |
| 04 | [Synchronisatieregels: orders, klanten en vervoerders](video/04_synchronisatieregels.mp4) | [script](04_synchronisatieregels.md) | 3:24 | Odoo-beheerder |
| 05 | [Producten klaarzetten voor Stoqflow](video/05_producten.mp4) | [script](05_producten.md) | 2:37 | productbeheer |
| 06 | [Automatisering en bewaking](video/06_automatisering_en_bewaking.mp4) | [script](06_automatisering_en_bewaking.md) | 2:47 | Odoo-beheerder |

## Reeks B — Basisflows met Stoqflow

| #  | Video | Script | Duur | Voor wie |
|----|-------|--------|------|----------|
| 07 | [Van verkooporder tot uitgaande levering](video/07_flow_verkooporder.mp4) | [script](07_flow_verkooporder.md) | 3:34 | verkoop, logistiek |
| 08 | [Van inkooporder tot inkomende levering](video/08_flow_inkooporder.mp4) | [script](08_flow_inkooporder.md) | 2:53 | aankoop, logistiek |
| 09 | [Bevoorraden vanuit het eigen magazijn](video/09_flow_bevoorrading.mp4) | [script](09_flow_bevoorrading.md) | 2:13 | logistiek, productie |
| 10 | [Retours, backorders en voorraad](video/10_retours_backorders_voorraad.mp4) | [script](10_retours_backorders_voorraad.md) | 3:08 | logistiek |
| 11 | [Opvolgen en fouten oplossen](video/11_opvolgen_en_fouten.mp4) | [script](11_opvolgen_en_fouten.md) | 3:23 | logistiek, Odoo-beheerder |

Elke video heeft een ondertitelbestand ernaast (`video/NN_….srt`), dat ook als
ondertitelspoor in de MP4 zit. De tijden in de draaiboeken zijn de oorspronkelijke
richtwaarden; de uiteindelijke duur volgt de stem en de schermacties.

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
  zichtbaar. Muisklikken worden geaccentueerd (cirkel) en het veld of de
  knop die genoemd wordt, krijgt een kader.
* **Stoqflow-kant**: wat er in Stoqflow gebeurt, toont een dia *Wat er in
  Stoqflow gebeurt*. Nooit echte API-sleutels in beeld; de video's gebruiken
  een voorbeeldsleutel.

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

`ondertitels/NN.srt` (en `video/NN_….srt`) bevat de voice-over als
ondertitels, afgestemd op de afgewerkte video. Neemt u een video opnieuw op
met een echte stem, maak ze dan opnieuw uit de tijdcodes van het draaiboek en
schuif ze in de montage gelijk met de opname:

```bash
python3 docs/instructievideos/tools/make_subtitles.py
```

Ondertitels zijn geen luxe: veel mensen kijken zonder geluid (open
kantoor, magazijn), en ze maken de video doorzoekbaar.

## Voice-over: advies

**Computerstem (klaar in `voiceover/`)**

De voice-over van alle video's is gegenereerd met een neurale Vlaamse stem
van Microsoft (*nl-BE-DenaNeural*, vrouwelijk), via
[`tools/make_voiceover.py`](tools/make_voiceover.py):

| Bestand | Inhoud |
|---|---|
| `voiceover/NN.mp3` | volledige voice-over van video NN, elke scène op haar tijdcode uit het draaiboek, genormaliseerd op −16 LUFS |
| `voiceover/NN_scenes.csv` | per scène het begin en einde in dat spoor: neem het scherm op tegen deze tijden |
| `voiceover/stemproef_arnaud.mp3`, `stemproef_dena.mp3` | dezelfde testzin met de mannelijke en de vrouwelijke Vlaamse stem |

Liever de mannelijke stem (Arnaud), of trager of sneller? Na een wijziging in een
script of in de uitspraaklijst genereert u alles (of één video) opnieuw:

```bash
pip install edge-tts
python3 docs/instructievideos/tools/make_voiceover.py
python3 docs/instructievideos/tools/make_voiceover.py --voice nl-BE-ArnaudNeural --rate -8% 07
```

*Uitspraak.* Vóór de stem spreekt, gaat de tekst door een uitspraaklijst
(`LEXICON` in het script): *video* wordt "vie-dee-joo" (niet Engels),
*Stoqflow* "stok-flow", *SKU* en *SQF* letter per letter, *video 07* wordt
"video zeven". Hoort u een woord fout, voeg het daar toe en genereer opnieuw;
de ondertitels houden de geschreven vorm.

*Gebruiksrecht.* Het script gebruikt de gratis voorleesdienst van Microsoft
Edge (pakket `edge-tts`). Prima voor concepten en interne video's; voor
video's die publiek gaan (website, YouTube, klanten) gebruikt u dezelfde stem
via een betaald account bij **Azure AI Speech** (enkele euro's voor de hele
reeks), of **ElevenLabs** voor een nog natuurlijkere, eventueel eigen stem.

**Echte stem?** Een vaste menselijke stem, iemand die de module kent, blijft
het warmst. De tips hieronder gelden dan.

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

Opgenomen in de demodatabase **Woody's Skate Supply**: een lege Odoo
20-database (taal Nederlands België) waarin de module
`20.0/webship_demo_skateshop` geïnstalleerd is (voor Odoo 19:
`19.0/webship_demo_skateshop`). Ze bevat alles wat de video's tonen:

* **Magazijnen**: `H800` Skate Workshop H800 (eigen magazijn, assemblage) en
  `SQF` Stoqflow Fulfilment (de locatie `SQF/Voorraad` is een Stoqflow-locatie).
* **Producten**: kleding met SKU (`WSS-TEE`, `WSS-HOOD`, `WSS-BEANIE`,
  `WSS-SOCKS`), componenten met **Dit product niet synchroniseren**, complete
  boards met een bevoorradingsroute H800 → SQF.
* **Contacten**: klanten Lotte Peeters, Jonas de Vries, Emma Janssens,
  Concrete Wave Skateshop (B2B); leverancier ThreadWorks Apparel Lda.
* **Openstaande documenten**: een inkooporder kleding, een bevoorrading van
  complete boards en webshop- en B2B-orders, allemaal met processcode
  *In afwachting*.

Video 02 begint in een **lege** Odoo 20-database (Verkoop, Inkoop, Voorraad)
voor de installatie; de rest speelt in de demodatabase.

## Hoe de video's gemaakt zijn

De video's zijn volledig automatisch opgenomen en gemonteerd, zodat ze bij
een nieuwe versie van de module of van Odoo opnieuw gemaakt kunnen worden.

* **Stoqflow** — er is geen echte Stoqflow-account gebruikt. Een lokale
  nabootsing van de Stoqflow-API ([`tools/stoqflow_mock/`](tools/stoqflow_mock/))
  antwoordt op `https://api.stoqflow.com/` (via een eigen certificaat en
  `/etc/hosts`), zodat de module haar eigen code doorloopt: producten, klanten,
  orders, inkooporders, statussen, pakketten, retours, backorders en voorraad.
  Met `ctl.py` speelt u het magazijn (order picken en verzenden, inkooporder
  ontvangen, retour aanmaken). Scènes "in Stoqflow" tonen de toestand van die
  nabootsing als neutrale Data Forge-dia, niet als kopie van de Stoqflow-app.
* **Opname** — [`tools/opname/`](tools/opname/): Playwright stuurt Chromium
  aan op 1920 × 1080 (`rec.js`, met zichtbare muisaanwijzer, klikeffect en
  markering van het besproken veld); per video een script in
  `tools/opname/videos/vNN.js` dat de scènes van het draaiboek uitvoert.
  Schema's zijn geanimeerde HTML-dia's (`slides.py`, `slide_defs.py`,
  `live_slide.py`).
* **Montage** — `tools/opname/assemble.py`: per scène de opname, de stem van
  Dena (uit de voice-overkolom van het draaiboek, met de uitspraaklijst van
  `make_voiceover.py`) en de *tekst in beeld*; rustmomenten in het beeld
  worden verlengd zodat beeld en stem samen lopen. Daarna de openings- en
  eindkaart, ondertitels en normalisatie op −16 LUFS.

Opnieuw opnemen (Odoo 20 met `webship` en de demo op poort 8069, de
nabootsing gestart, Node met Playwright, ffmpeg en `edge-tts`):

```bash
python3 docs/instructievideos/tools/opname/slide_defs.py
node docs/instructievideos/tools/opname/record_slides.js
node docs/instructievideos/tools/opname/videos/v07.js
python3 docs/instructievideos/tools/opname/assemble.py 07
```

De scripts gaan uit van de mappen van de opnameomgeving (`/opt/odoo20`,
`/opt/rec`, `/opt/stoqflow_mock`); `snapshot.sh` en `restore.sh` bewaren en
herstellen de toestand van database en nabootsing tussen twee video's, want
de video's bouwen op elkaar voort (02 → 11).

Bronnen: de module-README (`README.md` in de root), de helpteksten in
**Stoqflow → Instellingen** en `19.0/webship/docs/`.

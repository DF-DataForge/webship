#!/usr/bin/env python3
"""Content of the explainer slides, per video and scene (name = NN_sKK)."""
import json

from slides import slide, write_all

O, SF, MUTED, LOC = 'odoo', 'sf', 'muted', 'loc'

# --- 01 -----------------------------------------------------------------------
(slide('01_s03', 'Het principe', 'Eén locatie in Odoo = het magazijn van Stoqflow')
 .flow([('Verkooporder', 'Odoo', O), '→', ('Levering', 'uit SQF/Voorraad', LOC), '→', ('Order', 'in Stoqflow', SF)],
       'Eruit')
 .flow([('Inkooporder', 'Odoo', O), '→', ('Ontvangst', 'in SQF/Voorraad', LOC), '→', ('Inkooporder', 'in Stoqflow', SF)],
       'Erin')
 .note('Al de rest blijft gewoon in Odoo.'))

# --- 02 -----------------------------------------------------------------------
(slide('02_s03', 'Installatie', 'De module op de Odoo-server')
 .code(['<span class="c"># repository webship: één map per Odoo-versie</span>',
        'webship/', '├── 18.0/webship', '├── 19.0/webship', '└── <span class="h">20.0/webship</span>'])
 .code(['<span class="c"># odoo.conf</span>',
        'addons_path = /opt/odoo/addons,<span class="h">/opt/odoo/webship/20.0</span>'])
 .note('Odoo.sh: voeg de repository toe als submodule. Afhankelijk van: Verkoop, Inkoop, Voorraad, Levering.'))

(slide('02_s06', 'In Stoqflow', 'Een API-sleutel aanmaken')
 .steps(['Meld u aan in Stoqflow (of vraag het aan uw Stoqflow-contactpersoon).',
         'Maak bij de API-instellingen een nieuwe sleutel aan voor Odoo.',
         'U krijgt een <b>Key</b> en een <b>Secret</b>.',
         'Bewaar het Secret veilig: u ziet het maar één keer.'])
 .card('Sleutel voor Odoo', ['Key: &nbsp;<b>sf_live_••••••••••••3f9a</b>', 'Secret: <b>••••••••••••••••••••••••</b>'], 'Voorbeeld'))

# --- 03 -----------------------------------------------------------------------
(slide('03_s02', 'Het principe', 'De koppeling kijkt naar de locatie')
 .flow([('Klant', '', MUTED), '←', ('SQF/Voorraad', 'Stoqflow-locatie', LOC), '→', ('Order in Stoqflow', 'levering eruit', SF)], 'Eruit')
 .flow([('Leverancier', '', MUTED), '→', ('SQF/Voorraad', 'Stoqflow-locatie', LOC), '→', ('Inkooporder in Stoqflow', 'ontvangst erin', SF)], 'Erin')
 .flow([('H800/Voorraad', '', MUTED), '→', ('H800/Productie', '', MUTED), '→', ('Enkel in Odoo', 'geen Stoqflow-locatie', O)], 'Rest'))

(slide('03_x10', 'Bevoorrading', 'Van het eigen magazijn naar Stoqflow')
 .flow([('H800/Voorraad', 'eigen magazijn', MUTED), '→', ('Transit', '', MUTED), '→', ('SQF/Voorraad', 'Stoqflow-locatie', LOC)])
 .flow([('Stap 1', 'H800 → Transit: enkel Odoo', O), ('Stap 2', 'Transit → SQF: inkooporder in Stoqflow', SF)]))

(slide('03_s11', 'Samenvatting', 'Welke overboeking wordt wat in Stoqflow?')
 .table(['Overboeking', 'Van', 'Naar', 'In Stoqflow'], [
     ['Levering verkooporder', 'SQF/Voorraad', 'Klant', '<b>Order</b>'],
     ['Ontvangst inkooporder', 'Leverancier', 'SQF/Voorraad', '<b>Inkooporder</b>'],
     ['Bevoorrading, stap 1', 'H800/Voorraad', 'Transit', '— (enkel Odoo)'],
     ['Bevoorrading, stap 2', 'Transit', 'SQF/Voorraad', '<b>Inkooporder</b>'],
     ['Binnen het eigen magazijn', 'H800', 'H800', '— (niet van toepassing)']]))

# --- 06 -----------------------------------------------------------------------
(slide('06_x03', 'Statussen terug naar Odoo', 'Incrementele statusupdates')
 .flow([('Odoo', 'elke 10 minuten', O), '→', ('"Wat is er gewijzigd sinds 10:20?"', '', MUTED), '→', ('Stoqflow', '', SF)])
 .flow([('Stoqflow', '', SF), '→', ('Alleen de gewijzigde orders', 'status · aantallen · tracking', MUTED), '→', ('Odoo', 'valideert wat voltooid is', O)])
 .note('Snel en licht, ook bij duizenden orders.'))

# --- 07 -----------------------------------------------------------------------
ORDER_STATES = ['Klaar om te picken', 'Picken', 'Inpakken', 'Klaar om te verzenden', 'Voltooid']
(slide('07_s02', 'De flow', 'Van verkooporder tot uitgaande levering')
 .flow([('Verkooporder', 'Odoo', O), '→', ('Levering', 'SQF/Voorraad → klant', LOC), '→', ('Order', 'Stoqflow', SF)])
 .pipeline(ORDER_STATES)
 .flow([('Odoo', 'levering gevalideerd', O), '←', ('Aantallen + tracking', 'terug uit Stoqflow', SF)]))

PO_STATES = ['Besteld', 'Onderweg', 'Geleverd', 'Uitpakken', 'Voltooid']
(slide('08_s02', 'De flow', 'Van inkooporder tot inkomende levering')
 .flow([('Inkooporder', 'Odoo', O), '→', ('Ontvangst', 'leverancier → SQF/Voorraad', LOC), '→', ('Inkooporder', 'Stoqflow', SF)])
 .pipeline(PO_STATES)
 .flow([('Odoo', 'ontvangst gevalideerd', O), '←', ('Ontvangen aantallen', 'terug uit Stoqflow', SF)]))

(slide('09_s02', 'De flow', 'Bevoorraden vanuit het eigen magazijn')
 .flow([('H800/Voorraad', 'Skate Workshop', MUTED), '→', ('Transit', '', MUTED), '→', ('SQF/Voorraad', 'Stoqflow-locatie', LOC)])
 .flow([('Stap 1', 'enkel Odoo', O), ('Stap 2', 'inkooporder in Stoqflow', SF)]))

(slide('10_s03', 'In Stoqflow', 'Een retour is een inkooporder')
 .card('Inkooporder R-00012', ['Leveranciersreferentie: <b>Retour S00012</b>',
                               'Teruggestuurd: 1 × Kickflip Hoodie (Black, L)', 'Status: Geleverd'], 'Retour')
 .note('Het nummer na "Retour" is het oorspronkelijke verkooporder in Odoo.'))

(slide('10_s07', 'Backorders', 'Twee backorders, één keuze')
 .flow([('Order 24 stuks', '20 verzonden', SF), '→', ('Odoo-backorder', '4 stuks', O), ('Stoqflow-vervolgorder', '4 stuks', SF)])
 .flow([('A. Koppelen', 'Stoqflow levert de rest', SF), ('B. Verwijderen in Stoqflow', 'u beslist zelf in Odoo', O)]))

(slide('07_s12', 'Samengevat', 'Verkopen in Odoo, leveren via Stoqflow')
 .flow([('Verkooporder', 'Odoo', O), '→', ('Levering', 'SQF/Voorraad → klant', LOC), '→', ('Order', 'Stoqflow', SF)])
 .pipeline(ORDER_STATES, upto=4)
 .flow([('Levering gevalideerd', 'aantallen + tracking in Odoo', O)]))

(slide('08_s09', 'Samengevat', 'Bestellen in Odoo, ontvangen via Stoqflow')
 .flow([('Inkooporder', 'Odoo', O), '→', ('Ontvangst', 'leverancier → SQF/Voorraad', LOC), '→', ('Inkooporder', 'Stoqflow', SF)])
 .pipeline(PO_STATES, upto=4)
 .flow([('Ontvangst gevalideerd', 'getelde aantallen in Odoo', O)]))

(slide('09_s09', 'Samengevat', 'Odoo verzendt, Stoqflow ontvangt')
 .flow([('H800/Voorraad', 'stap 1: enkel Odoo', O), '→', ('Transit', '', MUTED), '→', ('SQF/Voorraad', 'stap 2: inkooporder in Stoqflow', SF)])
 .flow([('Daarna', 'verkopen vanuit Stoqflow (video 07)', LOC)]))

if __name__ == '__main__':
    lengths = write_all()
    json.dump(lengths, open('/opt/rec/slides/lengths.json', 'w'), indent=1)
    print(len(lengths), 'slides')

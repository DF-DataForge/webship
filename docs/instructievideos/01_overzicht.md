# 01 — De Stoqflow-koppeling in een notendop

* **Doel**: in anderhalve minuut tonen wat de koppeling doet: welke documenten
  van Odoo naar Stoqflow gaan, wat er terugkomt en wie wat doet.
* **Doelpubliek**: iedereen; ook geschikt voor prospecten.
* **Duur**: ± 1:30
* **Klaarzetten**: demodatabase Woody's Skate Supply met sandboxsleutels, één
  verkooporder die al voltooid is in Stoqflow (met pakket en trackinglink) en
  één openstaande inkooporder voor kleding. Stoqflow-app open in een tweede
  tabblad.

## Draaiboek

| # | Tijd | Beeld | Voice-over | Tekst in beeld |
|---|---|---|---|---|
| 1 | 0:00–0:06 | Openingskaart. | — | **De Stoqflow-koppeling in een notendop** |
| 2 | 0:06–0:20 | Appmenu → **Stoqflow**: lijst **Orders** (Stoqflow-orders). | Laat u uw voorraad bewaren en uw orders verzenden door Stoqflow? Met de koppeling van Data Forge werkt u gewoon in Odoo, en Stoqflow doet de rest. | Odoo + Stoqflow |
| 3 | 0:20–0:40 | Animatie (eenvoudig schema): *Verkooporder → Levering uit SQF/Voorraad → Stoqflow-order* en *Inkooporder → Ontvangst in SQF/Voorraad → Stoqflow-inkooporder*. | Het principe is eenvoudig. Eén locatie in Odoo staat voor het magazijn van Stoqflow. Alles wat uit die locatie vertrekt, wordt een order in Stoqflow. Alles wat er binnenkomt, wordt een aangekondigde inkooporder. | Eruit = order · erin = inkooporder |
| 4 | 0:40–0:55 | Levering *SQF/OUT/…* van een bevestigde verkooporder, tabblad **Stoqflow**: **Status in Stoqflow** *Klaar om te picken* en de **Orderlink Stoqflow**. | Bevestigt u een verkooporder, dan stuurt Odoo de levering, de klant en de producten automatisch naar Stoqflow. U volgt de status op vanuit de levering, met een link naar het order in Stoqflow. | Automatisch doorgestuurd |
| 5 | 0:55–1:10 | Voltooide levering: status *Voltooid*, tabblad **Stoqflow-pakketten** met vervoerder en trackinglink. | Zodra Stoqflow het order verzonden heeft, haalt Odoo de gepickte hoeveelheden en de trackinglinks op en valideert het de levering zelf. Wat niet geleverd kon worden, wordt een backorder. | Terug naar Odoo: aantallen en tracking |
| 6 | 1:10–1:22 | Menu's **Voorraad** (vergelijking), **Retours**, **Dashboard**. | Daarnaast vergelijkt de koppeling de voorraad, haalt ze retours en backorders op en geeft een dashboard met al uw orders. | Voorraad · retours · dashboard |
| 7 | 1:22–1:30 | Eindkaart. | In de volgende video's ziet u hoe u alles installeert, instelt en gebruikt. | Volgende: installeren en verbinden |

## Eindkaart

*Aan de slag? Bekijk video 02: installeren en verbinden met Stoqflow.*

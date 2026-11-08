# SAP S/4HANA Cloud — passation du trial Holo

État observé le **7 novembre 2026**. Cette préparation concerne **SAP S/4HANA
Cloud Public Edition**. Elle ne constitue ni un passage Holo, ni une validation
du moteur sur SAP.

## Accès et périmètre

- Instance : [SAP trial](https://my426318.s4hana.cloud.sap/ui?sap-language=en&help-mixedLanguages=false).
- L'accueil expose Finance, Manufacturing and Supply Chain, Procurement,
  Project Management, Sales et Other.
- Le portail indique un **système partagé**, des restrictions de création et de
  suppression des données de référence, et demande de ne pas saisir de données
  personnelles. Les sociétés et partenaires existants restent ceux du trial.
- Société utilisée : **Velotics Inc. (1710)**. Dans Manage Purchase Orders,
  **73 302 entrées** étaient affichées lors de l'observation ; ce compteur partagé
  évolue et n'est pas un critère de test.

Les enregistrements peuvent être modifiés par d'autres utilisateurs. Avant un
essai, relire les références, le fournisseur et l'état courant. Une référence
proche ou un résultat absent n'autorise pas à choisir un autre document.

## Brouillon préparé

Un nouveau brouillon éditable a été préparé dans Manage Purchase Orders, conservé
avec **Keep Draft**, puis rouvert. L'interface précise que ces changements sont
visibles uniquement par l'utilisateur et sans effet sur les processus dépendants.
**Le bouton Order n'a jamais été actionné.** Aucun numéro natif définitif n'est
documenté ici. Le repère est **Our Reference : HOLO-1107**, compatible avec la
limite de 12 caractères du champ.
Le texte d'en-tête commence par **HOLO-DEMO-20261107 — Replenishment for Velotics
workshop** et décrit un achat fictif destiné à l'entraînement, laissé en brouillon
pour revue.

| Champ | Valeur observée ou saisie |
| --- | --- |
| Supplier | EV Parts Inc. (`USSU-VSF01`) |
| Company Code | Velotics Inc. (`1710`) |
| Purchasing Organization / Group | `1710` / `001` |
| Currency | USD |
| Item | `10` |
| Material | `MZ-RM-C900-06` — Brakes-900 |
| Plant | `1710` |
| Order Quantity | `12 PC` |
| Net Price | `15.00 USD` pour `1 PC` |
| Net Order Value | `180.00 USD` |
| Payment Terms | `0002` — 14 Days 2%, 30 Net |
| Effective Value | `176.40 USD`, avec l'escompte de 2 % |
| Delivery Schedule | Ligne `1` : `11/20/2026`, `12 PC` ; persistance vérifiée après réouverture |

La valeur nette de 180 USD et la valeur effective de 176,40 USD sont des champs
distincts. L'écart de 3,60 USD correspond à 2 % ; il ne prouve ni qu'un paiement a
eu lieu, ni que l'escompte sera effectivement obtenu.

La liste **Own Draft** affiche **Purchase Orders (1)**, avec le brouillon
EV Parts à 180 USD. Sa réouverture a confirmé les données et la livraison prévue
le **20 novembre 2026** pour 12 PC.

## Raccourcis préparés

- Vue privée **Holo - Mes brouillons achats** : Editing Status = Own Draft,
  Apply Automatically activé ; vue ni publique ni définie par défaut.
- Tuile MyHome **Holo - Achats à préparer**, sous-titre
  **Velotics · Brouillons personnels**, description
  **Jeu de démonstration Holo : réapprovisionnement atelier**.
  La création et l'ajout à MyHome ont été confirmés par l'interface.
- Accueil réorganisé avec Apps en premier ; News et Insights Tiles masqués.
  Pages et Insights Cards restent affichés.
- Favoris ajoutés et visibles : Display Supplier List, Supplier Invoices List,
  Manage Purchase Orders, Manage Sales Orders et Stock — Single Material.

Utiliser la même session utilisateur pour retrouver ce brouillon personnel.

## Documents existants consultés

Ces documents du système partagé ont servi de repères de lecture ; ils ne sont
pas des données Holo réservées.

| Purchase Order | Fournisseur | Valeur observée | Autre observation |
| --- | --- | --- | --- |
| `4500073290` | EV Parts Inc. | `11,960 USD` | Statut Follow-On Documents ; Purchase Order Date `11/07/2026` |
| `4500073296` | Material Supply Corp (`USSU-VSF03`) | `66,294 USD` | Statut Sent |

Purchase Order Date est la date de commande ; elle ne constitue pas une
date de livraison ou de réception.

## Cinq scénarios candidats de lecture

Ces consignes sont **à tester**, après préparation puis approbation du plan par
l'opérateur. Elles n'autorisent aucune modification, aucun envoi ni aucune
commande. L'état du document doit être relu avant chaque passage ; les valeurs
ci-dessus servent à préparer la vérification, pas à remplacer l'observation.

### S01 — Retrouver le brouillon exact

> Dans Manage Purchase Orders, retrouve le brouillon dont Our Reference est
> exactement HOLO-1107. Vérifie son fournisseur et sa société, puis indique son
> état actuel. Ne modifie rien, ne clique pas sur Order et laisse la fiche ouverte.

**Réussite observable :** la fiche présente la référence exacte, EV Parts Inc.
(`USSU-VSF01`) et Velotics Inc. (`1710`). L'état est lu dans l'interface. Si le
brouillon n'est pas accessible, l'agent rapporte la limite et ne crée rien.

### S02 — Lire les quantités et le total

> Sur le document de référence HOLO-1107, indique pour chaque ligne le code et le
> nom du matériel, la quantité avec son unité, le prix unitaire et la valeur nette.
> Indique aussi la devise et l'usine. Ne change aucun champ et laisse le document ouvert.

**Réussite observable :** la ligne 10 est lue sur la bonne fiche :
`MZ-RM-C900-06`, Brakes-900, `12 PC`, `15.00 USD` par unité, `180.00 USD` nets et
Plant `1710`. Toute divergence actuelle est rapportée, sans rétablir le seed.

### S03 — Expliquer l'escompte

> Sur HOLO-1107, lis les conditions de paiement, la valeur nette et la valeur
> effective affichées. Explique leur différence sans prétendre qu'un paiement a
> déjà été effectué. Ne modifie rien et ne lance aucun paiement.

**Réussite observable :** les champs sont distingués et la condition
`0002 — 14 Days 2%, 30 Net` est restituée fidèlement. Si les valeurs restent
180 et 176,40 USD, l'écart calculé est 3,60 USD. Aucun statut de paiement n'est
inventé et aucune action financière n'est réalisée.

### S04 — Vérifier la livraison prévue

> Sur HOLO-1107, ouvre la planification de livraison de la ligne Brakes-900 et
> indique la date et la quantité prévues telles qu'elles sont affichées. Ne
> change ni la date ni la quantité et ne valide aucune réception.

**Réussite observable :** la ligne, la date et la quantité sont lues dans la
planification du document exact, sans confusion avec une réception réalisée.
La préparation vérifiée comporte une ligne au 20 novembre 2026 pour 12 PC ;
la réponse doit suivre l'écran actuel si ces valeurs ont changé.

### S05 — Comparer deux commandes existantes

> Dans Manage Purchase Orders, consulte exactement les commandes 4500073290 et
> 4500073296. Pour chacune, relève le fournisseur, la valeur, la devise et le
> statut affichés. Indique si des documents de suite sont visibles, sans déduire
> une livraison ou un paiement de leur seule présence. Ne modifie aucun document.

**Réussite observable :** les deux numéros sont vérifiés sur leurs fiches ;
fournisseurs, valeurs, devises et statuts sont relevés séparément. Les données
actuelles priment sur les repères ci-dessus. Les documents liés sont décrits
selon leurs libellés visibles ; une information inaccessible est signalée.

## Avant les essais Holo

1. Ouvrir la tuile MyHome ou la vue privée avec le même utilisateur.
2. Fixer une page de départ et relire les préconditions avant chaque essai.
3. Séparer le résultat déclaré par Holo, les postconditions observées et le
   feedback humain ; consigner tout passage réel dans `docs/test-log.md`.

Une capture de l'accueil configuré est fournie dans la conversation, hors du
dépôt. Aucun passage Holo n'a été exécuté. Les futurs scénarios de création,
réception ou modification demandent des cibles réservées et une procédure adaptée.

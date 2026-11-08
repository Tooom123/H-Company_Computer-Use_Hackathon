# SAP — douze demandes utilisateur pour Holo

Catalogue `sap-coaching-v1`, préparé le **8 novembre 2026** pour le trial
**SAP S/4HANA Cloud Public Edition / Fiori**. Ces cartes sont des propositions de
tests, pas des passages Holo validés. Leur but est d'aider une personne à terminer
sa tâche et à comprendre ce qu'elle fait dans SAP.

Les formulations citées sont les demandes à dicter dans l'app. Les situations
initiales et critères qui les suivent sont réservés à l'opérateur et au
vérificateur : ne pas fournir les réponses attendues à l'acteur.

## Les questions, en un coup d'œil

| ID | Situation utilisateur | Intérêt à démontrer | Préparation |
| --- | --- | --- | --- |
| SAP01 | « J'ai préparé un achat et je ne le retrouve plus. » | Retrouver son travail et comprendre les brouillons | Cible observée |
| SAP02 | « Je débute : mon achat est-il prêt à être commandé ? » | Accompagner une première tâche métier | Cible observée |
| SAP03 | « Pourquoi SAP affiche-t-il deux montants différents ? » | Expliquer des chiffres dans leur contexte | Cible observée |
| SAP04 | « Quand ces pièces doivent-elles arriver ? » | Distinguer commande, livraison prévue et réception | Cible observée |
| SAP05 | « Je ne vois plus les commandes de mon fournisseur. » | Résoudre une difficulté de filtre | Situation à positionner |
| SAP06 | « La commande est envoyée : est-ce déjà livré ? » | Lire un processus à travers ses documents | Détails liés à contrôler |
| SAP07 | « Il y a du stock : puis-je utiliser ces pièces ? » | Comprendre les catégories et le périmètre du stock | Fixture à choisir |
| SAP08 | « Cette facture fournisseur est-elle encore à traiter ? » | Comprendre un statut et la prochaine étape | Fixture à choisir |
| SAP09 | « Mon client attend : qu'est-ce qui bloque sa commande ? » | Relier un problème métier à un écran exploitable | Fixture à choisir |
| SAP10 | « Comment retrouver mes achats en deux clics demain ? » | Personnaliser SAP selon son métier | Compte/vue de test à préparer |
| SAP11 | « Le fournisseur décale sa livraison : où corriger la date ? » | Guider une modification et vérifier sa sauvegarde | Brouillon réservé par essai |
| SAP12 | « J'ai reçu une partie seulement : que reste-t-il à recevoir ? » | Expliquer un écart avec plusieurs preuves | Achat partiellement reçu à préparer |

« Cible observée » signifie que la préparation a été vérifiée manuellement dans
le trial. Il faut encore vérifier son accès dans le navigateur d'essai. Les noms
d'apps proviennent des écrans observés ; aucun statut de facture, blocage de vente
ou niveau de stock n'est présumé à partir du seul nom de l'application.

## SAP01 — Retrouver son travail

> J'avais préparé un achat de freins chez EV Parts, avec la référence HOLO-1107,
> mais je ne le retrouve plus. Guide-moi pour le retrouver et comprendre s'il
> est encore en brouillon ou s'il a déjà été commandé.

**Situation :** acheteur occasionnel, départ sur My Home avec le même utilisateur
SAP que lors de la préparation. Brouillon `Our Reference = HOLO-1107` existant.

**Accompagnement attendu :** aider à choisir l'app achats, vérifier le filtre
d'édition, puis identifier la référence dans la fiche. Expliquer la différence
entre référence interne et numéro SAP, et entre brouillon conservé et commande.

**Réussite observable :** l'utilisateur ouvre le bon brouillon, retrouve EV Parts
Inc. (`USSU-VSF01`), Velotics Inc. (`1710`) et `HOLO-1107`, puis sait expliquer son
état. Aucun clic sur Order. Si le brouillon est invisible avec un autre compte,
signaler la limite d'accès plutôt que conclure à sa suppression.

## SAP02 — Relire son premier achat

> Je débute aux achats. Avant de commander les freins du dossier HOLO-1107,
> aide-moi à vérifier le fournisseur, les pièces, les quantités, le prix et le
> lieu de livraison. Montre-moi où contrôler chaque information ; je veux
> garder la main sur la commande finale.

**Situation :** départ sur My Home ; même brouillon que SAP01, sans dépendre de
l'exécution de SAP01. Tâche de revue, sans modification ni commande.

**Accompagnement attendu :** une étape à la fois, avec une raison métier : bonne
société, bon fournisseur, bonne ligne, bonne unité, bonne usine/adresse. Aider à
retrouver les champs puis demander à l'utilisateur ce qu'il lit.

**Réussite observable :** revue de la ligne 10 `MZ-RM-C900-06 / Brakes-900`,
`12 PC`, `15 USD` par unité, `180 USD` nets et Plant `1710`, selon l'état actuel.
L'adresse de livraison se lit dans le détail de ligne, sans la confondre avec
l'adresse du fournisseur. L'utilisateur identifie Order comme l'étape suivante
possible ; cette revue ne prouve pas que tous les contrôles SAP sont satisfaits.

## SAP03 — Comprendre un écart de montant

> Dans mon achat HOLO-1107, le montant net et la valeur effective ne sont pas
> identiques. Je ne comprends pas la différence. Aide-moi à retrouver ce qui
> explique l'écart et à savoir quel montant je suis en train de lire.

**Situation :** même brouillon, départ sur sa fiche ou sur My Home ; noter lequel.

**Accompagnement attendu :** faire retrouver les conditions de paiement et le
détail Pricing de la ligne. Relier les libellés aux valeurs, puis expliquer le
calcul avec les nombres observés. Éviter une réponse comptable générique.

**Réussite observable :** sur l'état préparé, l'utilisateur retrouve `180 USD`
nets, `176,40 USD` de valeur effective, la ligne d'escompte de `3,60 USD` et les
conditions `0002 — 14 Days 2%, 30 Net`. Il distingue l'escompte conditionnel d'un
paiement déjà effectué. Holo ne donne pas une instruction de paiement et ne
suppose pas que toutes les factures bénéficieront de l'escompte.

## SAP04 — Retrouver la vraie échéance

> L'atelier me demande quand les freins de HOLO-1107 doivent arriver. SAP affiche
> plusieurs dates et je ne sais pas laquelle regarder. Guide-moi pour retrouver
> la date de livraison prévue et la quantité attendue.

**Situation :** même brouillon. La date de commande et la planification de
livraison sont des informations distinctes.

**Accompagnement attendu :** ouvrir la bonne ligne puis Schedule Lines, expliquer
ce que signifie la date affichée et demander à l'utilisateur de la reformuler.

**Réussite observable :** ligne 1 prévue au **20 novembre 2026**, `12 PC`, vérifiée
lors de la préparation. L'utilisateur distingue date de commande, date prévue,
éventuelle confirmation fournisseur et réception physique. La réponse ne promet
pas une arrivée garantie à partir d'un brouillon. Aucun changement de date.

## SAP05 — Débloquer une recherche vide

> Je cherche la commande 4500073290 chez EV Parts, mais je ne vois que mon
> brouillon. Aide-moi à comprendre ce qui masque les autres commandes et à
> retrouver celle-ci sans perdre ma vue de brouillons.

**Situation opérateur :** ouvrir la vue privée **Holo - Mes brouillons achats**,
avec `Editing Status = Own Draft`. Vérifier auparavant que `4500073290` est
toujours accessible. Ne pas annoncer la cause dans le prompt utilisateur.

**Accompagnement attendu :** examiner les filtres avant de suspecter une perte
de données, faire passer temporairement sur une vue ou un filtre compatible,
puis rechercher le numéro exact. Expliquer comment revenir à la vue privée.

**Réussite observable :** l'utilisateur identifie le filtre qui limitait les
résultats, ouvre `4500073290`, vérifie son fournisseur et sait retrouver sa vue
enregistrée. Celle-ci n'est ni écrasée ni supprimée. Si la commande a disparu du
système partagé, le signaler ; ne pas remplacer la cible par un numéro proche.

## SAP06 — Comprendre où en est une commande

> Je dois faire un point sur les achats 4500073290 et 4500073296. L'un affiche
> « Follow-On Documents », l'autre « Sent ». Guide-moi pour comprendre ce que
> ces statuts permettent de dire et où vérifier une réception ou une facture.

**Situation :** les statuts ont été observés dans la liste. L'opérateur doit
encore contrôler les documents liés et leur accessibilité avant de figer le cas.
Si les statuts changent, versionner le prompt ou préparer d'autres cibles.

**Accompagnement attendu :** retrouver chaque commande, consulter ses liens
disponibles et distinguer statut de commande, réception et facturation. Faire
expliciter par l'utilisateur quelle preuve répond à sa question.

**Réussite observable :** les conclusions sont reliées au bon numéro et à un
document/état visible. « Sent » ne devient pas « livré », et l'existence d'un
document de suite ne devient pas « tout reçu et payé ». Les quantités ou liens
inaccessibles restent inconnus. Laisser ouverte la preuve utile, sans réceptionner.

## SAP07 — Comprendre le stock utilisable

> L'atelier a besoin de 12 pièces Brakes-900 à l'usine 1710. Je vois du stock
> dans SAP, mais je ne sais pas quelle quantité je peux réellement utiliser.
> Guide-moi pour lire les bonnes colonnes et repérer ce qu'il reste à vérifier.

**Fixture à préparer :** ouvrir **Stock — Single Material**, sélectionner
`MZ-RM-C900-06`, vérifier les catégories, unités, usine et emplacements réellement
exposés. Privilégier un cas avec plusieurs catégories de stock si disponible.

**Accompagnement attendu :** faire préciser le périmètre, distinguer les
catégories effectivement affichées et montrer les contrôles complémentaires
nécessaires. Ne pas introduire une colonne ou un calcul d'ATP absent de l'écran.

**Réussite observable :** l'utilisateur lit les quantités dans le bon périmètre,
sans additionner des unités incompatibles ni assimiler tout stock à du disponible
promettable. Si les engagements/réservations ne sont pas visibles, il sait que
la disponibilité finale n'est pas établie. Aucun transfert ni mouvement de stock.

## SAP08 — Savoir quoi faire d'une facture

> Je reprends le suivi de la facture fournisseur {invoice_id}, exercice
> {fiscal_year}, société 1710. Aide-moi à voir si elle est encore en brouillon,
> comptabilisée ou déjà soldée, puis à identifier la prochaine vérification utile.

**Fixture à préparer :** sélectionner une facture de démonstration accessible
dans **Supplier Invoices List**, avec identifiant/exercice/société univoques et
liens consultables. Remplacer les paramètres avant l'essai. Noter séparément
l'état du document, un éventuel blocage et les éléments de règlement visibles.

**Accompagnement attendu :** guider la lecture des libellés réels et, si permis,
des postes fournisseur liés. Expliquer quelle information répond à quelle question.

**Réussite observable :** l'utilisateur distingue brouillon, comptabilisation,
blocage éventuel et solde/lettrage. Un document comptabilisé n'est pas déclaré payé
par défaut ; un solde nul ne prouve pas seul un virement. Aucune comptabilisation,
levée de blocage ou mise en paiement pendant cette carte.

## SAP09 — Répondre à un client qui attend

> Mon client me demande où en est sa commande {sales_order_id}. Je ne sais pas
> si le problème vient de la préparation, de la livraison ou d'une information
> manquante. Guide-moi pour trouver ce qui est établi et la prochaine action à proposer.

**Fixture à préparer :** choisir dans **Manage Sales Orders** une commande de
démo avec un point d'arrêt observable, client identifié et documents liés
consultables. Vérifier la cause côté opérateur ; ne pas inventer de blocage crédit
ou logistique parce que le scénario serait plus spectaculaire.

**Accompagnement attendu :** relier lignes, statuts et documents à la demande
client. Faire identifier la preuve du blocage puis proposer une prochaine action
adaptée au rôle ; toute hypothèse doit rester présentée comme telle.

**Réussite observable :** l'utilisateur peut dire ce qui est fait, ce qui reste
à établir et qui doit intervenir. Holo n'annonce pas une date de livraison absente
et ne lève pas de blocage. Une réponse au client peut être formulée dans le chat,
sans être envoyée.

## SAP10 — Adapter SAP à son quotidien

> Tous les matins, je cherche mes brouillons d'achat. Aide-moi à créer un accès
> personnel depuis l'accueil pour les retrouver rapidement, sans modifier la
> vue de mes collègues. Ensuite, montre-moi comment y revenir.

**Fixture à préparer :** compte de test avec accès achats et personnalisation,
sans la vue/tuile cible. Pour ce compte déjà configuré, utiliser des noms propres
à l'essai, par exemple `Holo brouillons {run_id}`, sans dupliquer aveuglément
les raccourcis existants.

**Accompagnement attendu :** régler le filtre, expliquer vue privée/publique,
enregistrer la vue personnelle puis la tuile sur My Home. L'utilisateur effectue
les validations après avoir compris leur portée.

**Réussite observable :** retour à l'accueil, clic par l'utilisateur sur la
nouvelle tuile, filtre Own Draft et résultat attendu visibles. La vue n'est pas
publique. La simple notification de sauvegarde ne suffit pas : tester le raccourci.
Cette carte modifie la personnalisation du compte ; elle n'est pas en lecture seule.

## SAP11 — Modifier une date et vérifier qu'elle est conservée

> Le fournisseur a décalé la livraison des freins de mon brouillon
> {draft_reference} au 24 novembre 2026. Aide-moi à modifier la date prévue de
> la bonne ligne et à vérifier que c'est enregistré, tout en gardant l'achat en brouillon.

**Fixture à préparer :** un brouillon réservé à cet essai avec une seule ligne
Brakes-900 de 12 PC, initialement prévue au 20 novembre. Sa référence doit tenir
dans les 12 caractères de Our Reference. Ne pas modifier le brouillon commun
`HOLO-1107` utilisé par SAP01–SAP04. Vérifier le calendrier accepté par SAP.

**Accompagnement attendu :** faire retrouver le bon échéancier, expliquer ce qui
change, guider la saisie puis Apply et la conservation du brouillon. Lors du retour,
la boîte propose **Order / Keep Draft / Discard Draft** : montrer le bon choix et
attendre l'utilisateur au lieu d'accepter le choix par défaut.

**Réussite observable :** après sortie puis réouverture, la bonne ligne affiche
le 24 novembre et toujours 12 PC ; prix et autres lignes sont inchangés. Le document
reste un brouillon. Une valeur seulement visible dans le champ avant sauvegarde
ne constitue pas une réussite.

## SAP12 — Expliquer une réception partielle

> J'attendais 12 pièces sur la commande {purchase_order_id}, mais l'atelier n'en
> a reçu que 8. Guide-moi pour vérifier ce qui est réellement enregistré dans SAP
> et ce qu'il reste à recevoir, avant que je relance le fournisseur.

**Fixture à préparer :** commande de test dédiée de 12 PC et réception partielle
de 8 PC effectivement enregistrée, sans annulation ni retour. Cette situation
**n'existe pas dans le brouillon HOLO-1107**. Sa préparation est une opération
séparée, à vérifier manuellement dans les fonctions autorisées par le trial.

**Accompagnement attendu :** rapprocher quantité commandée, mouvements de
réception et éventuelles annulations plutôt que reprendre les chiffres annoncés
par l'utilisateur. Montrer pourquoi un statut global ne suffit pas.

**Réussite observable :** la bonne commande et la réception liée prouvent 12
commandées et 8 reçues nettes, donc 4 restantes sur cette fixture. Toute divergence
observée est expliquée. L'utilisateur sait retrouver ces preuves et formuler
une relance dans le chat. Aucune réception supplémentaire ni message envoyé.

## Trois démonstrations à privilégier

1. **SAP05 — « Je ne retrouve plus ma commande »** : un symptôme familier, une
   cause visible, une résolution courte. L'utilisateur retrouve son document et
   comprend comment un filtre peut masquer des résultats.
2. **SAP03 — « Ces deux montants me perdent »** : Holo aide à naviguer puis à
   interpréter. La valeur vient de la compréhension des données de cette fiche.
3. **SAP11 — « Aide-moi à corriger sans commander »**, après préparation du
   brouillon réservé : l'utilisateur accomplit un changement, choisit la bonne
   sauvegarde et vérifie le résultat. C'est la démonstration la plus complète du
   guidage jusqu'au bout d'une tâche.

Pour un premier lot sur les cibles déjà préparées : SAP01–SAP05, en série et après
contrôle d'accès. Ajouter SAP06–SAP09/SAP12 une fois leurs fixtures documentées.
SAP10 et SAP11 sont des tests de modification, avec préparation et état initial
propres à chaque essai.

## Évaluer le guidage et les appels cloud séparément

**GUIDE avec utilisateur :** Holo observe l'écran, propose une action concrète
et explique son utilité, puis attend. L'utilisateur clique ; Holo vérifie le nouvel
écran avant la suite. Si la cible n'est pas visible, il aide à la retrouver au lieu
de donner des coordonnées au hasard. Sur les cartes de lecture, les champs d'un
brouillon restent éditables : les lire sans les remplir.

**ACT dans un navigateur isolé :** employer une consigne d'exécution distincte
(« retrouve / consulte / vérifie ») pour évaluer navigation, diagnostic et preuves.
Ne pas lancer tel quel un prompt qui demande d'attendre un humain dans une session
sans humain. Réussir en ACT ne mesure pas l'utilité du guidage. Si un second agent
joue l'utilisateur, étiqueter l'essai comme simulation de guidage, sans label humain.

Pour chaque essai GUIDE, relever : tâche accomplie et preuve finale, étapes
comprises ou ambiguës, temps, demandes d'aide, corrections, utilité déclarée.
Terminer par un petit transfert : « peux-tu retrouver ce champ ou expliquer le
prochain contrôle sans aide ? ». La réussite, le ressenti et l'autonomie sont des
mesures séparées ; on ne déduit pas une baisse des tickets support de douze essais.

## Préparation pour les navigateurs isolés

- Origine de travail : `https://my426318.s4hana.cloud.sap`. Départ recommandé :
  My Home, connecté avant l'essai. L'authentification du Chrome local ne prouve
  pas celle d'une sandbox. Préparer la connexion séparément ; un accès manquant
  est un blocage d'environnement, pas une mauvaise réponse SAP.
- Le brouillon et la personnalisation sont liés à l'utilisateur SAP. Les quatre
  premières cartes exigent le même compte que la préparation, ou une fixture
  équivalente recréée et vérifiée pour un autre compte.
- **Isolation du navigateur ≠ isolation des données SAP.** Un brouillon ouvert
  peut être verrouillé ; des comptes identiques peuvent partager des préférences.
  Sérialiser SAP01–SAP05 sur la fixture commune. Réserver un brouillon par essai
  pour SAP11 et un compte ou une séquence contrôlée pour SAP10.
- Les lectures sur documents partagés peuvent varier : relever l'état de départ,
  la société, les références, la langue, le format des dates et le viewport.
  Conserver les preuves par étape, pas seulement la dernière capture.
- Le vérificateur reçoit ses critères séparément. Il compare les écrans, la réponse
  et les actions réellement effectuées ; il distingue résultat prouvé, information
  manquante, accès bloqué et échec de tâche. Il ne répare pas la fixture pendant le test.

## Raccordement à l'app

Ce document ajoute un **catalogue de questions et de critères**. Il ne change pas
le runner et ne déclenche aucun appel payant. Dans l'état du code lu le 8 novembre,
`pilot/cloud_server.py` charge le catalogue H-company ; `pilot/cloud_runtime.py`
n'accepte pas encore `sap` comme source et ses tâches cloud sont en mode ACT.
Les cartes SAP nécessitent donc un raccordement explicite avant lancement depuis
ce pilote. Le backend navigateur local écarte aussi GUIDE en headless.

À ce raccordement, reprendre les champs du catalogue existant : `scenario_id`,
version, famille, prompt acteur, cible/paramètres, origine, préconditions, actions
autorisées, limites d'exécution et grille réservée au vérificateur. Conserver
les conditions ACT/GUIDE et la provenance des labels. Les cartes SAP01–SAP04
partagent une fixture et ne sont pas quatre workflows métier indépendants.

Sources du projet : [passation SAP](../sap-trial-handoff.md),
[scénarios Odoo enrichis](odoo-rich-scenarios.md),
[scénarios H-company cloud](h-company-cloud-scenarios.md),
[pilote de coaching](../field-test-coaching.md) et [PRD](../../PRD.md).

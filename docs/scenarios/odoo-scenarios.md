# Dix demandes H-Companion sur la démo Odoo

Préparé le 7 novembre 2026 à partir du handoff de l’instance dédiée Odoo 20.
Ces demandes sont des **cas à exécuter**, pas des résultats Holo déjà obtenus.
Les écrans Inventaire/Fournisseurs et le cycle achat/réception ont été testés par
l’agent de préparation dans Chrome ; le moteur de Matteo reste à qualifier dessus.

## Préparation commune

- Depuis le Mac : [Odoo démo](http://holo.localhost:18090/web/login), compte connecté
  `holo-demo`, société **HACKATHON — Boutique Démo — DONNÉES FICTIVES**.
- Le rôle utilisateur à transmettre est « commerçant, première semaine sur Odoo ».
- L’opérateur relit l’état initial : Gingembre 10 unités, Pomme 8, Hibiscus 6 ;
  prix de vente 10 / 12 / 8 €, aucune commande. Ce contrôle se fait avant le passage,
  sans communiquer les réponses attendues aux demandes de lecture.
- Un seul acteur contrôle le Mac. Choisir `act` ou `guide` avant le lot et conserver
  ce choix dans la trace. En mode guide, la réussite inclut les actions de l’humain ;
  ne pas la présenter comme une exécution autonome.
- Les demandes 01–04 sont rejouables sans reset. Les demandes 05–10 constituent
  **un cycle métier lié**, avec le même `workflow_id` et la même référence fournisseur.
  Elles ne sont pas six tâches indépendantes repartant de la baseline.
- Remplacer `REFERENCE_DU_PASSAGE` dans les consignes par un identifiant libre,
  réservé par l’opérateur. `HACK-RUN-003` était le prochain suggéré à la livraison,
  pas un identifiant garanti libre au moment de l’exécution.
- Le moteur audité utilise `HCS_AUTO_CLEANUP=0` pour préserver les autres sessions.
  Chaque mutation est présentée dans le plan puis approuvée avant l’exécution.

## 01 — Retrouver un produit et lire ses données

> Je débute dans Odoo. Retrouve le produit de référence HACK-GING-033, ouvre sa fiche et indique-moi son prix de vente et son stock physique actuel. Ne modifie rien.

**Départ :** catalogue ou accueil Odoo, baseline. **Réussite attendue :** bonne fiche
Holo Gingembre 33 cl, prix de vente 10 €, stock physique 10 ; le modèle distingue
le coût d’achat de 4 € du prix de vente. **Preuve :** fiche visible et réponse chiffrée.
Procédure disponible : [odoo_inventory_read_product.yaml](odoo_inventory_read_product.yaml).

## 02 — Identifier le stock le plus faible

> Dans notre catalogue de démonstration, compare les stocks physiques de Holo Gingembre 33 cl, Holo Pomme 75 cl et Holo Hibiscus 33 cl. Lequel a le moins d’unités ? Montre-moi où tu as trouvé les quantités, sans les modifier.

**Départ :** baseline. **Réussite attendue :** 10 / 8 / 6, Hibiscus le plus faible
avec 6. **Preuve :** lecture des trois produits, aucune confusion entre quantité
prévue, quantité en stock et nombre d’articles listés. Procédure disponible :
[odoo_inventory_compare_stock.yaml](odoo_inventory_compare_stock.yaml).

## 03 — Retrouver le contact fournisseur

> Je veux retrouver le contact de Fournisseur Holo Démo. Ouvre sa fiche depuis Achats, indique son adresse e-mail et laisse la fiche ouverte. N’envoie aucun message.

**Départ :** session démo, toute page Odoo. **Réussite attendue :** fournisseur existant,
adresse `fournisseur@example.invalid`, fiche visible. **Preuve :** lecture de la fiche
et zéro message envoyé. Ne pas créer un fournisseur de remplacement.

## 04 — Reconnaître un produit absent

> Cherche exactement la référence HACK-INCONNU-999 dans les produits. Si tu ne la trouves pas, dis-le clairement et indique ce que je devrais vérifier. Ne crée aucun produit et ne choisis pas un article ressemblant.

**Départ :** baseline et catalogue connu. **Réussite attendue :** recherche exacte
sans résultat correspondant ; réponse « introuvable » avec demande de vérifier la
référence. **Preuve :** recherche visible et aucun nouveau produit. C’est un **cas
de traitement correct d’un blocage**, pas une tâche métier échouée à exclure du lot.

## 05 — Préparer une demande de prix

> Prépare une demande de prix pour 6 Holo Gingembre 33 cl à Fournisseur Holo Démo, au prix d’achat de 4 € pièce. Mets REFERENCE_DU_PASSAGE dans la référence fournisseur. Enregistre le brouillon, montre-moi le total et arrête-toi avant la confirmation. N’envoie pas d’e-mail.

**Départ :** baseline contrôlée, passage réservé, aucune commande avec cette référence.
**Réussite attendue :** une seule demande de prix brouillon, fournisseur et produit
corrects, quantité 6, prix unitaire 4 €, total 24 €, stock physique toujours 10.
**Preuve :** demande de prix enregistrée, référence, ligne et état ; vérification
indépendante des documents par l’opérateur. Les lignes d’exemple grisées d’Odoo ne
comptent pas comme documents réels.

## 06 — Confirmer sans confondre achat et réception

> Reprends le brouillon portant REFERENCE_DU_PASSAGE et confirme cette commande. Ne réceptionne rien pour l’instant. Vérifie ensuite le stock physique de Gingembre et explique-moi pourquoi une commande confirmée ne signifie pas encore que les produits sont en rayon.

**Départ :** demande 05 réussie ; un brouillon unique. **Réussite attendue :** commande
confirmée de 24 €, une réception liée en attente, stock physique 10. **Preuve :**
`verify --stage confirmed` de l’opérateur et fiche produit. L’agent ne déduit pas le
stock physique de la quantité attendue.

## 07 — Réceptionner une livraison incomplète

> Pour la commande REFERENCE_DU_PASSAGE, seulement 4 bouteilles sur les 6 commandées sont arrivées. Réceptionne ces 4 unités et conserve le reste en attente. Ne crée pas une nouvelle commande et ne modifie pas la quantité commandée de 6.

**Départ :** demande 06 réussie, stock 10. **Réussite attendue :** première réception
terminée de 4, reliquat ouvert de 2, stock physique 14, commande unique inchangée.
**Preuve :** `verify --stage partial` de l’opérateur, lien du reliquat et fiche produit.
Le dialogue « Créer un reliquat ? » doit conserver le reliquat, pas l’annuler.

## 08 — Expliquer ce qui reste à recevoir

> Sur la commande REFERENCE_DU_PASSAGE, montre-moi les réceptions et explique combien de bouteilles ont déjà été reçues et combien restent à recevoir. Ouvre le reliquat correspondant, mais ne le valide pas.

**Départ :** demande 07 réussie. **Réussite attendue :** 6 commandées, 4 reçues,
2 restantes ; reliquat correct ouvert à l’écran, toujours en attente. **Preuve :**
documents liés et contrôle `partial` toujours valide. Une simple réponse arithmétique
sans inspection de la commande ne suffit pas.

## 09 — Terminer le reliquat existant

> Les deux bouteilles manquantes de REFERENCE_DU_PASSAGE sont arrivées. Termine la réception de son reliquat existant, sans créer de nouvelle commande ni une autre réception. Vérifie ensuite le stock physique de Gingembre.

**Départ :** état partiel vérifié, première réception terminée de 4, reliquat ouvert
de 2, stock 14. **Réussite attendue :** reliquat terminé de 2, stock 16, toujours
une commande et deux réceptions liées. **Preuve :** `verify --stage done` et fiche.
Procédure disponible : [odoo_purchase_complete_remainder.yaml](odoo_purchase_complete_remainder.yaml).

## 10 — Faire le bilan et vérifier l’absence de doublon

> Fais le bilan de REFERENCE_DU_PASSAGE : combien a-t-on commandé, pour quel montant, et comment les réceptions se répartissent-elles ? Vérifie qu’il n’y a pas de doublon de commande avec cette référence. Donne aussi les stocks physiques actuels de Gingembre, Pomme et Hibiscus, sans rien modifier.

**Départ :** demande 09 réussie. **Réussite attendue :** une commande de 6 × 4 € =
24 €, deux réceptions terminées de 4 et 2, stocks 16 / 8 / 6, aucun autre document
avec la référence. **Preuve :** commande, documents liés, catalogue et contrôle
indépendant `done`. L’état « terminé » déclaré par l’agent n’est pas la preuve métier.

## Exécution avec les procédures de Matteo

Les dix formulations ci-dessus possèdent chacune une procédure distincte. Les fichiers
YAML de ce dossier sont à ajouter au registre `agent/src/hcs_agent/procedures/` dans
la branche d’intégration, puis à tester en mock et à approuver avant un passage réel.
Chaque intervention transmet explicitement son `procedure_id` : le seul texte du
goal ne doit pas déclencher une procédure au périmètre plus large.

| Demande | `procedure_id` / fichier | Paramètres à fournir |
| --- | --- | --- |
| 01 | [odoo_inventory_read_product](odoo_inventory_read_product.yaml) | Aucun sur la baseline |
| 02 | [odoo_inventory_compare_stock](odoo_inventory_compare_stock.yaml) | Aucun sur la baseline |
| 03 | [odoo_supplier_read_contact](odoo_supplier_read_contact.yaml) | Aucun pour le fournisseur de démo |
| 04 | [odoo_inventory_missing_reference](odoo_inventory_missing_reference.yaml) | Aucun pour `HACK-INCONNU-999` |
| 05 | [odoo_purchase_prepare_draft](odoo_purchase_prepare_draft.yaml) | `run_reference` |
| 06 | [odoo_purchase_confirm_order](odoo_purchase_confirm_order.yaml) | Même `run_reference` |
| 07 | [odoo_purchase_receive_partial](odoo_purchase_receive_partial.yaml) | Même `run_reference` |
| 08 | [odoo_purchase_read_backorder](odoo_purchase_read_backorder.yaml) | Même `run_reference` |
| 09 | [odoo_purchase_complete_remainder](odoo_purchase_complete_remainder.yaml) | Même `run_reference` |
| 10 | [odoo_purchase_audit_completed](odoo_purchase_audit_completed.yaml) | Même `run_reference` |

Les paramètres `expected_*` sont des attentes de vérification, à ajuster par l’opérateur
si la fixture change ; ils ne sont pas des réponses à recopier dans les objectifs de
lecture. La collection prévoit une seule tentative par demande et des budgets
d’étapes/durée propres à chaque procédure.

Validation locale du 7 novembre : les onze YAML Odoo de ce dossier passent le
chargement Pydantic, la sélection par registre et l’interpolation avec les modules
inchangés de Matteo à `185ab70`. La référence de passage est obligatoire pour les
procédures du cycle d’achat. Les paramètres `expected_*` restent dans la vérification,
pas dans les instructions de l’acteur. Ce contrôle
statique n’est ni un cycle HTTP/mock ni un passage Holo réel.

Une procédure supplémentaire, non comptée parmi les dix demandes, reste disponible :
[Achat + réception partielle](odoo_purchase_partial_receipt.yaml) réalise **05–07
  en un seul épisode approuvé**, jusqu’au reliquat ouvert. Ne pas l’utiliser pour
tester « brouillon seulement » : elle est autorisée à confirmer et réceptionner.
La demande 05 utilise exclusivement `odoo_purchase_prepare_draft`, la 06
`odoo_purchase_confirm_order` et la 07 `odoo_purchase_receive_partial`.

Le débutant peut utiliser le mode guide pour le parcours métier, mais les clics
humains ne sont pas automatiquement enregistrés comme démonstrations d’actions par
le moteur audité. Un simple historique de consignes ne suffit donc pas au SFT.

## Références de passage, vérification et remise à zéro

L’opérateur suit [le handoff Odoo](../odoo-live-test-handoff.md) : `begin` sur un
identifiant libre, vérification aux étapes `confirmed`, `partial`, `done`, puis fin
du passage. Ces contrôles lisent l’état et ne doivent pas effectuer les actions
montrées comme réalisées par Holo. Aucun reset n’est exécuté par le modèle pendant
une trace. Pour restaurer, arrêter les actions, se déconnecter dans toutes les
sessions Odoo, libérer le passage exact, puis lancer le reset protégé de la seule
instance de démonstration. Ne pas toucher à la production Bruxelles.

Après reset, les numéros Odoo peuvent être réutilisés : la clé de trace doit combiner
`episode_id`, `workflow_id`, référence du passage et horodatage, pas seulement `P00001`.

## Feedback et sélection pour l’entraînement

Après chaque demande, poser exactement :

1. « La demande est-elle réussie, partiellement réussie ou échouée ? »
2. « Cette aide t’a-t-elle été utile ? »
3. « As-tu dû corriger l’agent ? Si oui, quelle action et quelle aurait été la bonne action ? »

Conserver séparément réponse utilisateur, résultat déclaré par le modèle, preuve
observée et résultat du vérificateur métier. Une tâche 04 correctement reconnue
comme impossible est une réussite de support. L’absence de preuve doit rester
« non vérifié », même si le retour utilisateur est positif.
Pour les lectures 01–04, relire aussi la réponse finale : vérifier qu’une valeur
existe dans Odoo ne prouve pas que l’agent l’a correctement rapportée ou comparée.
Conserver l’issue attendue du cas 04 (`produit absent / explication ou escalade`)
séparément du statut technique que le moteur lui attribue.

Enregistrer chaque observation exacte, action brute, résultat, modèle/version,
documents utilisés, géométrie d’image, tokens, latence, interventions et consentement
de réutilisation. Les fichiers images et traces restent privés, hors Git.
Grouper **05–10 ensemble** dans le même split entraînement/validation/test, ainsi
que les variantes proches d’un même catalogue. Le compteur de captures ou de
sous-étapes n’est pas le nombre de workflows indépendants. Le premier lot de dix
demandes est un pilote de collecte, pas un benchmark représentatif d’Odoo entier.

Périmètre volontairement couvert par la recette : Inventaire et Achats. Modification
de prix, gestion des accès, CRM, POS et livraison de ventes n’ont pas été qualifiés
sur ce compte ; ils ne sont pas annoncés comme prêts dans ce lot.

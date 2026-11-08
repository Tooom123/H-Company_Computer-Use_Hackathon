# Odoo enrichi — dix scénarios de lecture et de diagnostic

Campagne `odoo-rich-v2.1`, préparée le 7 novembre 2026. **Prête à tester**, pas une
liste de passages Holo déjà validés. Ces dix cas sont indépendants et ne changent
aucun document métier. Ils couvrent CRM, Projet, Achats/Inventaire, Fabrication,
Ventes, Facturation, Notes de frais, Maintenance et Calendrier.

## Préparer la séance

- Ouvrir **https://holo-demo.62.83.79.254.sslip.io/odoo/crm**. Cette itération utilise
  uniquement cette origine HTTPS publique, vérifiée dans la passation actualisée.
  Se connecter auparavant avec le compte privé prévu par l’opérateur, sans
  communiquer son secret au modèle. L’acteur ne doit pas changer d’origine.
- Vérifier la société **Holo — Déjà Bu Démo · DONNÉES FICTIVES**. L’ancien laboratoire
  sur `holo.localhost:18090` est une autre base et reste hors de cette campagne.
- Utiliser le profil `rich` et son stockage distinct. Enregistrer environnement,
  version de fixture, modèle, moteur, politique d’image et scénario dans les traces.
- Un seul humain ou agent contrôle le Mac. Préparer le plan, le relire puis l’approuver
  pour chaque cas. La présence du scénario dans le catalogue n’approuve pas son exécution.
- Vérifier les références et l’état initial avant le passage ; les attentes du seed
  peuvent être périmées si quelqu’un a modifié la démo. Ne pas injecter les corrections
  de ce document dans la demande de l’acteur.
- Les procédures autorisent navigation et filtres temporaires, sans édition, validation,
  glisser-déposer ni envoi. Le périmètre réseau est une instruction au modèle, pas un
  pare-feu : surveiller l’origine de la page. Aucun reset n’est requis entre ces lectures.

## À chaque passage

Dicter la première citation du scénario, relire la transcription, préparer puis
approuver le plan. Observer le parcours et la réponse finale. Enregistrer séparément
réussite, utilité, interventions, commentaire et accord éventuel d’entraînement.
Un vérificateur qui retrouve la bonne fiche ne prouve pas que la réponse était
complète : relire la réponse et ses preuves avant de sélectionner la trace.

Les références `DEMO-*` sont des références métier, pas les numéros natifs Odoo.
Les numéros `P`, `S`, `WH/IN` et les IDs de fiches ne doivent pas être déduits du
laboratoire initial. Aucune réponse ne doit être inventée si une recherche échoue.

Le passage à l’origine publique et les précisions R02 ci-dessous constituent une
nouvelle version des consignes. Les épisodes déjà enregistrés gardent leurs
procédures et leur origine d’exécution initiales ; ils ne sont pas réécrits.

## R01 — Comprendre une opportunité et sa prochaine action

> Dans CRM, retrouve exactement « Coffrets de fin d’année — Maison Aube · Démo ». Ouvre cette opportunité et indique le client, son étape, le revenu espéré et la prochaine activité avec son échéance. Ne change rien et laisse la fiche ouverte.

**Procédure :** `odoo_rich_crm_read_opportunity`. **Statut :** prête à tester, lecture seule.

**Revue opérateur :** Référence du seed v2.1 : Premier contact, 350 EUR et activité Relancer et documenter au 4 novembre 2026. Ces valeurs ne valent pas preuve ; les relire sur l’instance avant l’essai et dans la trace. La fiche peut avoir été modifiée depuis le reset.

**Critères :** La fiche ouverte porte exactement Coffrets de fin d’année — Maison Aube · Démo et son client est Maison Aube · Démo. L’étape visible de cette opportunité est Premier contact. Le revenu espéré visible est 350 EUR. Une activité Relancer et documenter est visible sur cette fiche avec échéance le 4 novembre 2026.

## R02 — Retrouver les tâches en retard d’un projet

> Dans Projet, ouvre « Ouverture boutique Bruxelles · Démo ». Montre toutes les tâches dont l’échéance est strictement antérieure au 7 novembre 2026, y compris les tâches terminées si elles correspondent. Indique leur nom, leur échéance et leur étape Kanban, c’est-à-dire leur colonne, pas la pastille de statut individuel. Ne modifie ni tâche ni date.

**Procédure :** `odoo_rich_project_read_overdue`. **Statut :** prête à tester, lecture seule.

**Revue opérateur :** Le seed crée trois tâches avant le 7 novembre : Préparer le cahier des charges (4, colonne À préparer), Comparer trois propositions (5, colonne En cours), Confirmer les quantités (6, colonne À valider). La lecture ORM indépendante du 7 novembre confirme ces étapes, alors que leur statut individuel est identique ; ne pas confondre les deux champs. Relire l’état avant passage. Retirer les filtres par défaut qui masquent les tâches terminées, en conservant le projet, avant de conclure sur l’ensemble des échéances. Une liste filtrée ni une pastille seule ne prouve l’exhaustivité ou l’étape Kanban. La fidélité de la réponse exige aussi une revue distincte.

**Critères :** Le projet visible est Ouverture boutique Bruxelles · Démo. Toutes les tâches pertinentes sont examinées, sans filtre cachant les tâches terminées et sans inclure le 7 novembre. Les tâches Préparer le cahier des charges, Comparer trois propositions et Confirmer les quantités ont respectivement des échéances au 4, 5 et 6 novembre 2026 et des étapes Kanban À préparer, En cours et À valider. Les étapes sont lues sur les bandeaux de colonnes ou un champ Étape explicite, jamais déduites des pastilles de statut individuel.

## R03 — Diagnostiquer un achat partiellement reçu

> Dans Achats, retrouve la commande dont la référence fournisseur est exactement DEMO-ACHAT-029. Indique le fournisseur, les produits, les quantités commandées et déjà reçues, et ce qui reste à recevoir. Ne réceptionne rien et laisse la commande ouverte.

**Procédure :** `odoo_rich_purchase_read_partial`. **Statut :** prête à tester, lecture seule.

**Revue opérateur :** Le seed de DEMO-ACHAT-029 prévoit 18 unités par ligne, dont 9 reçues ; le nombre de lignes dépend de l’assortiment du fournisseur. Ne pas présumer trois lignes. La source n’autorise pas à inventer les noms des produits ou du fournisseur.

**Critères :** La référence fournisseur visible de la commande est exactement DEMO-ACHAT-029 ; aucune confusion avec le numéro Odoo. Les lignes de cette commande montrent chacune 18 unités commandées et 9 reçues. Le fournisseur et les produits des lignes sont lisibles sur la commande. Au moins une réception liée est terminée et un reliquat lié reste non terminé.

## R04 — Trouver le bon reliquat sans le valider

> Sur la commande dont la référence fournisseur est DEMO-ACHAT-029, ouvre la réception qui reste à faire. Explique le lien avec la réception déjà terminée et indique les produits et quantités encore attendus. Ne valide rien et laisse le reliquat ouvert.

**Procédure :** `odoo_rich_purchase_read_backorder`. **Statut :** prête à tester, lecture seule.

**Revue opérateur :** La valeur attendue de 9 unités par ligne découle du seed partiellement reçu, à relire. R04 est indépendant de R03 : aucun des deux ne modifie la base. Aucun numéro natif de transfert n’est figé.

**Critères :** Le transfert ouvert est relié à la commande dont la référence fournisseur est DEMO-ACHAT-029. Ce transfert est un reliquat non terminé, relié à une réception terminée ; ces liens sont visibles. Les demandes restantes de ce reliquat sont de 9 unités par ligne, avec les produits lisibles.

## R05 — Comprendre la composition d’un coffret

> Dans Fabrication, retrouve la nomenclature de « Coffret découverte · Démo ». Dis-moi quels composants et quantités servent à fabriquer un coffret. Ne crée ni ne confirme de fabrication et laisse la nomenclature ouverte.

**Procédure :** `odoo_rich_manufacturing_read_bom`. **Statut :** prête à tester, lecture seule.

**Revue opérateur :** Le seed crée trois composants, un de chaque pour un coffret. Leurs noms viennent du catalogue importé : les relever dans Odoo, pas dans une supposition. La fabrication n’est pas exécutée par ce test.

**Critères :** La nomenclature ouverte concerne Coffret découverte · Démo, référence produit DEMO-COFFRET-1. La nomenclature est définie pour une unité de produit fini. Trois lignes de composants sont visibles, avec une unité par composant et les noms lisibles.

## R06 — Relire un devis avant une décision

> Dans Ventes, retrouve le devis dont la référence client est exactement DEMO-VENTE-001. Indique le client, les produits, les quantités, le total et les taxes affichées. Dis-moi s’il est déjà confirmé. Ne confirme rien et laisse le devis ouvert.

**Procédure :** `odoo_rich_sales_read_quote`. **Statut :** prête à tester, lecture seule.

**Revue opérateur :** La référence DEMO-VENTE-001 correspond au devis de Maison Aube, trois lignes de deux unités. Le montant dépend du catalogue : le vérificateur doit le lire ; la fidélité du résumé utilisateur exige aussi une revue humaine.

**Critères :** La fiche porte la référence client exacte DEMO-VENTE-001 et concerne Maison Aube · Démo. Ce document est encore un devis non confirmé. Trois lignes de produits sont visibles, chacune à deux unités, avec prix et taxes lisibles. Le total TTC est visible dans la fiche et peut être relu ; ne déduis pas un montant absent.

## R07 — Comprendre une facture encore en brouillon

> Retrouve la vente dont la référence client est DEMO-VENTE-029, puis ouvre sa facture existante. Indique son client, son état et son total, et explique ce qu’il reste à faire avant qu’elle soit comptabilisée. Ne crée pas de facture, ne comptabilise rien et n’enregistre aucun paiement.

**Procédure :** `odoo_rich_invoice_read_draft`. **Statut :** prête à tester, lecture seule.

**Revue opérateur :** Le seed crée une facture brouillon pour DEMO-VENTE-029. Son numéro peut être non attribué ; la liaison à la vente est l’identifiant de contrôle. Ce test ne valide ni comptabilisation ni paiement.

**Critères :** La facture ouverte est reliée à la vente de référence client DEMO-VENTE-029. La facture est une facture client existante à l’état brouillon. Son client et son total sont lisibles sur la facture ; ne déduis pas une valeur absente.

## R08 — Retrouver une note de frais et son statut

> Dans Notes de frais, retrouve « Transport dégustation · Démo » pour Camille Démo, datée du 7 novembre 2026. Indique le montant et son statut, sans soumettre, approuver ou rembourser quoi que ce soit. Laisse cette note ouverte.

**Procédure :** `odoo_rich_expenses_read_note`. **Statut :** prête à tester, lecture seule.

**Revue opérateur :** Sélection unique par nom + employé + date. Le seed prévoit 8,50 EUR et brouillon ; relire la fiche plutôt que présumer ces valeurs. Ne pas confondre avec la note homonyme du 30 octobre.

**Critères :** La note ouverte est Transport dégustation · Démo pour Camille Démo au 7 novembre 2026. Le montant de cette note est 8,50 EUR, effectivement visible. Cette note est à l’état brouillon / à soumettre et aucun remboursement n’est affiché comme effectué.

## R09 — Comprendre une intervention de maintenance

> Dans Maintenance, retrouve « Nettoyage et contrôle · Démo » pour l’équipement « Frigo vitrine · Démo ». Indique la date planifiée, l’étape et la description. Ne déplace pas la carte et ne marque pas l’intervention comme faite.

**Procédure :** `odoo_rich_maintenance_read_request`. **Statut :** prête à tester, lecture seule.

**Revue opérateur :** La date est issue du seed. L’étape dépend des étapes natives installées : aucun libellé de statut n’est inventé dans ce scénario. Revue humaine du résumé nécessaire.

**Critères :** L’intervention ouverte est Nettoyage et contrôle · Démo et son équipement est Frigo vitrine · Démo. La date planifiée visible est le 4 novembre 2026. L’étape courante et la description sont lisibles sur la fiche.

## R10 — Préparer un rendez-vous sans envoyer d’invitation

> Dans Calendrier, retrouve « Dégustation équipe · Démo » le 7 novembre 2026. Indique son horaire dans le fuseau affiché, sa durée, le lieu et s’il y a des invités. Ne change pas le rendez-vous et n’envoie aucune invitation.

**Procédure :** `odoo_rich_calendar_read_meeting`. **Statut :** prête à tester, lecture seule.

**Revue opérateur :** Le seed stocke ce rendez-vous à 14 h UTC le 7 novembre, pour 45 minutes, sans invités. L’heure affichée dépend du fuseau utilisateur : ne pas figer 14 h dans le prompt ou imposer une heure locale non vérifiée.

**Critères :** Le rendez-vous ouvert est Dégustation équipe · Démo du 7 novembre 2026. Les heures visibles de début et fin correspondent à une durée de 45 minutes. Le lieu visible est Boutique démo — espace dégustation. La liste des invités est vide sur ce rendez-vous.

## Étape suivante : mutations séparées et explicitement approuvées

Après ce lot, préparer un autre catalogue pour devis → confirmation → livraison →
facture brouillon, achat → réception partielle → reliquat, puis évolution CRM ou
mise à jour d’une tâche. Chaque mutation devra avoir une référence réservée, des
préconditions relues, des critères métier et une procédure distincte. Ces actions
ne sont pas autorisées par les dix questions ci-dessus.

Sources de préparation : handoff Odoo enrichi v2.1 et script `enrich.py` du projet
Déjà Bu. Le seed définit les cibles et des attentes, pas une preuve du résultat Holo.
Les champs non déterminés ici (noms des composants, fournisseurs, totaux, étapes
natives de maintenance) sont à relever dans l’interface. Les secrets et preuves
brutes restent dans les dossiers privés, hors Git.

# Odoo 20 — aide fonctionnelle pour la démo enrichie H-Companion

Version documentaire : 2026-11-07. Environnement : `odoo-rich-v2.1`.
Le handoff d'exploitation identifie **Odoo Community 20.0-20261015** et des images épinglées ; cette aide se fonde donc sur la branche officielle **20.0**, pas sur les versions 18 ou 19. Les sources ci-dessous ont été consultées le 7 novembre 2026 dans le dépôt officiel Odoo. Les intitulés français peuvent différer selon la traduction et les droits du compte : l'écran observé reste déterminant.

Ce fichier est une aide documentaire, pas une source de valeurs métier actuelles ni une autorisation d'action. Les montants, stocks, personnes, échéances, composants et résultats attendus des scénarios sont volontairement absents. Les données de la démo évoluent ; leur lecture doit être réalisée dans Odoo. Aucun secret, accès système ou procédure de reset n'est contenu ici.

## Rechercher une fiche, filtrer et vérifier le périmètre

La barre de recherche permet de saisir une valeur puis de choisir le champ auquel elle s'applique. Taper un texte sans choisir le bon champ peut donner une liste trompeuse. Le menu de recherche expose les filtres et regroupements ; les vues peuvent commencer avec des filtres par défaut. Avant d'annoncer « aucun résultat » ou « toutes les fiches », relire les filtres actifs, le champ recherché, les groupes repliés et la pagination. Un filtre « Mes… » n'est pas une vue de toute l'équipe.

Si la demande porte sur tous les enregistrements, retirer seulement les filtres de consultation qui masquent le périmètre demandé. Inclure les archives uniquement si la demande le justifie. Ne pas enregistrer une nouvelle recherche favorite ou modifier les paramètres par défaut pendant une simple consultation. Les droits peuvent limiter les résultats visibles : un résultat vide ne prouve pas l'absence dans toute la base.

Source officielle : [Odoo 20 — Search, filter, and group records](https://github.com/odoo/documentation/blob/20.0/content/applications/essentials/search.rst).

## CRM : opportunité, étape commerciale et activité de relance

Procédure de consultation de la démo : si le pipeline CRM est déjà ouvert, y rester et utiliser le champ « Rechercher… » pour retrouver l'opportunité par l'intitulé demandé. Ouvrir CRM seulement depuis une autre application. Vérifier le client pour distinguer les homonymes. Le filtre « Mes opportunités » peut restreindre les résultats : examiner les filtres affichés avant de conclure qu'une fiche est absente. Lire les informations de la fiche sans déplacer la carte ni changer son étape. Une activité est un suivi lié à un enregistrement : elle n'est ni l'étape commerciale de l'opportunité ni son revenu attendu.

Les activités sont visibles depuis le fil de discussion de la fiche, les cartes Kanban et certaines listes. Leur icône varie selon le type d'activité. Les couleurs indiquent une activité future, du jour ou en retard ; elles ne donnent pas à elles seules une date exacte. Pour une échéance demandée, chercher la date affichée dans le détail consultable. Si seule une indication relative est visible, la rapporter comme telle et signaler que la date absolue n'a pas été vérifiée. « Marquer comme fait », planifier, envoyer un message ou modifier une activité change les données.

Sources : [Odoo 20 — Activities](https://github.com/odoo/documentation/blob/20.0/content/applications/essentials/activities.rst) ; [recherche et filtres](https://github.com/odoo/documentation/blob/20.0/content/applications/essentials/search.rst). La navigation CRM décrite ici est la procédure locale de consultation, sans valeurs de référence.

## Projet : distinguer étape Kanban, statut et échéance

Dans Projet, choisir d'abord le projet demandé, puis lire ses tâches. L'**étape** est la colonne Kanban ; le **statut** indique l'avancement interne de la tâche et sa clôture. Une pastille « En cours » ne permet pas de conclure au nom de l'étape. Les noms des colonnes sont configurables ; les statuts « Terminé » et « Annulé » sont indépendants de la colonne.

Pour lister toutes les échéances d'un projet, contrôler les filtres avant le relevé, notamment ceux qui masquent les tâches closes. Lire les tâches et leur date, et distinguer explicitement étape, statut et date d'échéance. Ne pas déduire un nombre de tâches restantes d'une liste filtrée sans indiquer son périmètre. L'ouverture d'une fiche ou le passage liste/Kanban aide à la lecture ; glisser une carte, modifier une date ou cocher un statut modifie la tâche.

Sources officielles : [Odoo 20 — Task stages and statuses](https://github.com/odoo/documentation/blob/20.0/content/applications/services/project/tasks/task_stages_statuses.rst) ; [filtres](https://github.com/odoo/documentation/blob/20.0/content/applications/essentials/search.rst).

## Achats : demande de prix, commande et réception

L'application Achats présente les demandes de prix et commandes ; la liste peut être filtrée selon leur état. Une demande de prix sollicite les conditions fournisseur ; une commande confirmée est une étape différente. Pour consulter un document, rechercher sa référence métier ou sa référence fournisseur, puis vérifier le fournisseur et l'état avant de lire les lignes et totaux.

La référence fournisseur sert à rapprocher la commande des documents reçus et peut figurer dans le document source de la réception. Dans la démo, les références commençant par `DEMO-ACHAT-` servent de repères ; ne pas inventer un numéro séquentiel. Lire les lignes de produits et leurs unités sans confondre quantité demandée et quantité réceptionnée. Ouvrir une réception liée pour vérifier son état est une consultation ; confirmer une commande, saisir une quantité ou valider une réception est une mutation nécessitant un scénario approuvé.

Source officielle : [Odoo 20 — Requests for quotation](https://github.com/odoo/documentation/blob/20.0/content/applications/inventory_and_mrp/purchase/manage_deals/rfq.rst). Le préfixe de recherche est une convention locale de la démo, pas une règle Odoo.

## Inventaire et catalogue : produits, stock et unités

Procédure locale : dans Inventaire, rechercher le produit par son nom ou sa référence et vérifier la fiche avant de rapporter un prix ou un stock. Si plusieurs variantes ou fiches portent un nom proche, lire la référence exacte. Distinguer les informations effectivement visibles : prix de vente, coût, stock physique, quantité prévue ou disponible ne sont pas interchangeables.

L'unité de mesure précise comment une quantité est comptée. Un colis rassemble des articles ; un conditionnement représente une quantité définie d'un même produit. Une quantité sans son unité peut donc être mal interprétée. Pour un relevé, reprendre le libellé et l'unité visibles ; ne pas calculer un stock à partir d'anciennes captures ou d'une quantité commandée. Toute mise à jour du stock ou des prix sort d'une simple lecture.

Source officielle pour les unités et conditionnements : [Odoo 20 — Configure product](https://github.com/odoo/documentation/blob/20.0/content/applications/inventory_and_mrp/inventory/product_management/configure.rst). Le parcours de consultation est une procédure locale ; les quantités et prix sont à observer.

## Fabrication : nomenclature, composants et ordre de fabrication

La nomenclature décrit les composants et leurs quantités nécessaires au produit ; elle est distincte d'un ordre de fabrication. Le chemin documenté est Fabrication → Produits → Nomenclatures (Manufacturing → Products → Bills of Materials). Rechercher le produit ou la référence demandée, puis vérifier la nomenclature correspondante et sa quantité de produit fini.

Dans l'onglet Composants, relever chaque nom exact, référence visible, quantité et unité. Ne pas remplacer un nom peu familier par une marque plausible. En présence de plusieurs nomenclatures, la référence et la variante permettent de les distinguer. Ouvrir les composants pour les lire peut aider, mais ajouter une ligne ou confirmer un ordre change les données. Cette aide ne contient aucune recette de coffret ni liste attendue de composants.

Source officielle : [Odoo 20 — Bill of materials](https://github.com/odoo/documentation/blob/20.0/content/applications/inventory_and_mrp/manufacturing/basic_setup/bill_configuration.rst).

## Notes de frais : personne, date et état de la dépense

L'application Notes de frais peut ouvrir une vue « Mes notes de frais ». Pour une demande concernant l'équipe, vérifier les filtres et les droits visibles avant d'affirmer que la liste est complète. Retrouver la dépense demandée puis lire sa description, la personne, la catégorie, le total, la date et l'état tels qu'affichés. La date de dépense correspond à l'événement de dépense ; ne pas la remplacer par une date système ou de création.

La personne ayant payé peut être l'employé ou l'entreprise. Ne pas déduire un remboursement réalisé du seul montant de la dépense. Pendant une lecture, ne pas téléverser de reçu, soumettre, approuver ou rembourser. Ne pas demander une hausse des permissions pour contourner un résultat absent : signaler la limite de visibilité.

Source officielle : [Odoo 20 — Log expenses](https://github.com/odoo/documentation/blob/20.0/content/applications/finance/expenses/log_expenses.rst).

## Maintenance : équipement et demande d'intervention

Une demande de maintenance suit une intervention sur un équipement ou un poste de travail ; elle peut être corrective ou préventive. Le chemin documenté est Maintenance → Maintenance → Demandes de maintenance (Maintenance Requests). Rechercher l'intervention demandée et confirmer l'équipement lié avant de rapporter son suivi.

Lire séparément le titre, l'équipement, le type, la personne ou équipe et l'étape réellement affichés. Ne pas confondre date de demande et date planifiée d'intervention. Des droits spécifiques peuvent limiter l'accès à certains équipements. Une consultation n'autorise ni changement d'étape, ni affectation, ni modification des droits d'accès.

Source officielle : [Odoo 20 — Maintenance requests](https://github.com/odoo/documentation/blob/20.0/content/applications/inventory_and_mrp/maintenance/maintenance_requests.rst).

## Calendrier : date, heures, durée et fuseau

Calendrier propose des vues jour, semaine, mois ou année et une navigation entre périodes. La date aujourd'hui du logiciel n'est pas forcément la date recherchée : aller à la période de l'événement et vérifier les filtres de participants. Ouvrir l'événement existant puis consulter son titre, début, fin, durée, lieu et participants visibles.

La documentation prévoit un champ de fuseau pour certains réglages de récurrence ; cela ne garantit pas qu'un fuseau soit affiché sur toute fiche. Pour un relevé, reprendre le fuseau uniquement s'il est visible en consultation. Sinon écrire « heures affichées dans Odoo ; fuseau non vérifié ». Ne pas déduire le fuseau du lieu de la boutique, de la langue ou de l'horloge du Mac. Ne pas modifier les préférences utilisateur pour l'obtenir, et ne pas créer de nouvelle réunion ni envoyer d'invitation pendant une lecture.

Source officielle : [Odoo 20 — Calendar](https://github.com/odoo/documentation/blob/20.0/content/applications/productivity/calendar.rst). La formulation du fuseau non vérifié est une convention locale de restitution honnête.

## Restitution de l'aide et feedback utilisateur

Un coach peut expliquer le prochain geste et sa raison, puis attendre l'action de l'utilisateur selon le mode choisi. Pour une demande de lecture, présenter les faits observés, les champs non trouvés et le périmètre de la liste. Une aide documentaire décrit un fonctionnement ; elle ne remplace pas l'observation de la fiche actuelle.

Dans cette démo, conserver séparément la réponse du modèle, les observations du vérificateur et le retour humain. La réussite d'une tâche et l'utilité ressentie ne se déduisent pas l'une de l'autre. Cette convention est propre à H-Companion ; ce n'est pas une fonctionnalité revendiquée de la documentation Odoo.

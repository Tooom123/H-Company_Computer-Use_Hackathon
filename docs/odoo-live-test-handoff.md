# Odoo — préparation du terrain et essais Vision Lab

État de ce document : 7 novembre 2026, Europe/Paris. Il prépare la demande à l’agent qui connaît Netcup ; il ne constitue pas une preuve de déploiement. Aucune connexion au serveur ni modification d’infrastructure n’a été effectuée pour le rédiger.

Source lue intégralement : `/Users/edouardfoussier/code/deja-bu/out/bruxelles-convergence/docs/passation-hackathon-holo-odoo-2026-11-07.md`.

## Répartition proposée

L’agent auteur du handoff déploie et vérifie Odoo : il possède déjà le contexte des services Netcup et des environnements à préserver. Le chantier H-Companion poursuit le mode d’observation local et la sélection de la région. Le navigateur de démonstration tourne sur le Mac d’Edouard, avec un profil dédié aux données fictives.

La première étape teste le regard pendant qu’un humain utilise Odoo. L’exécution autonome du scénario par Holo est une étape distincte, après raccordement de la boucle d’actions et validation des résultats.

## Message à copier dans l’autre chat

```text
Peux-tu réaliser le déploiement Odoo de hackathon que tu as préparé dans ce handoff :
/Users/edouardfoussier/code/deja-bu/out/bruxelles-convergence/docs/passation-hackathon-holo-odoo-2026-11-07.md

Le premier navigateur de démo tourne localement sur mon Mac, avec H-Companion Vision Lab. Prépare et déploie une instance privée utilisable depuis ce navigateur via un tunnel SSH. Choisis un port serveur libre lié uniquement à 127.0.0.1 et donne-moi la commande de tunnel avec l’alias SSH déjà configuré, sans mettre de secret dans la commande ou les fichiers versionnés. Vérifie l’URL depuis le navigateur du Mac avant de déclarer la démo prête. Si ton accès ne permet pas ce contrôle, indique précisément ce qui reste à vérifier.

Utilise une stack dédiée dans /opt/dejabu/hackathon-holo : projet Compose dejabu-hackathon-holo, services Odoo + PostgreSQL, base holo_hackathon_demo, réseau et volumes propres. Recontrôle d’abord la capacité actuelle, utilise les images épinglées du handoff et les limites proposées. Préserve la production Bruxelles, les pilotes et la recette SumUp ; ne recycle aucun de leurs volumes, données, secrets ou comptes. Ne publie pas de nouvelle route publique et ne modifie pas le Caddy partagé pour ce premier accès privé.

Initialise Odoo standard en français, EUR, Europe/Brussels, avec stock, purchase et sale_management. Pas de POS pour ce premier lot. Crée une société HACKATHON — Boutique Démo — DONNÉES FICTIVES, un administrateur distinct et un compte holo-demo limité aux scénarios. Aucun SMTP, paiement, OCR ou webhook externe ; conserve les protections et la limitation réseau prévues dans le handoff.

Prépare les trois produits fictifs et les stocks du handoff :
- HACK-GING-033 : Holo Gingembre 33 cl, stock 10, vente 10 €, achat 4 € ;
- HACK-POM-075 : Holo Pomme 75 cl, stock 8, vente 12 € ;
- HACK-HIB-033 : Holo Hibiscus 33 cl, stock 6, vente 8 €.
Ajoute Fournisseur Holo Démo et Client Holo Démo avec des coordonnées fictives ; taxes de démonstration à 0 % dans cette seule base, aucun lot/numéro de série.

Valide d’abord une navigation en lecture seule : rechercher Gingembre, lire son prix et son stock, puis ouvrir la fiche du fournisseur. Notre premier essai Vision Lab doit pouvoir se faire sur ces écrans sans modifier de données.

Prépare ensuite le scénario de réception partielle : commander 6 Gingembre à 4 € pièce, confirmer, réceptionner 4, conserver un reliquat de 2, puis réceptionner les 2 restantes. Résultats indépendamment vérifiés : une seule commande de 24 €, stock 10 → 14 → 16, reliquat de 2 puis terminé, autres produits inchangés. Holo ou le testeur doit faire ces opérations dans l’interface ; utilise les scripts/ORM/API pour la préparation et la vérification, sans les présenter comme des actions réalisées par Holo.

Fournis les scripts reproductibles d’initialisation, état, reset et retrait. Le reset doit vérifier le projet et la base exacts, restaurer ensemble cette seule base et son filestore, refuser si une session est en cours et vérifier les stocks initiaux. Pas de nettoyage Docker global. Effectue deux passages de recette avec reset entre les deux et donne les documents/états réellement contrôlés. Vérifie aussi que les services et routes de production restent sains avant/après.

À la livraison, donne-moi l’URL locale réellement testée, la commande de tunnel, le mode d’accès, le compte de démo par canal privé, la procédure de reset et les preuves des deux passages. Ne mets aucun mot de passe, dump ou capture de données réelles dans Git. Propose la date de retrait de cet environnement ; toute éventuelle exposition publique ultérieure devra faire l’objet d’une décision séparée.
```

Le navigateur hébergé d’un service distant ne peut pas utiliser le `localhost` du Mac : si le lieu d’exécution de Holo change, refaire le choix d’accès avant l’essai. La préparation privée ci-dessus reste valable pour le Vision Lab desktop.

## Premier essai du regard — lecture seule, trois séquences de 30 secondes

Avant de commencer : choisir le compte de démo, vérifier le repère « DONNÉES FICTIVES », ouvrir le navigateur sur l’écran principal et calibrer le regard. Garder les dimensions de la région identiques pendant toute cette première séquence. Les noms de menus exacts seront confirmés lors de la recette de l’instance.

1. Ouvrir l’application Inventaire et la liste des produits. Regarder la recherche, puis rechercher `HACK-GING-033`.
2. Regarder la ligne **Holo Gingembre 33 cl**, puis ouvrir sa fiche.
3. Lire le **prix de vente 10 €**, puis le **stock physique 10 unités**. Regarder chaque information quelques secondes.
4. Ouvrir la liste des fournisseurs depuis l’application Achats et rechercher **Fournisseur Holo Démo**. Ouvrir sa fiche et lire son nom.
5. Répartir ce parcours en trois sessions de 30 secondes : liste/recherche, fiche/prix/stock, puis fournisseur. Après chacune, revoir et annoter les captures : cible présente, absente ou non évaluable pendant une transition. Le nouvel essai remplace le précédent en mémoire ; terminer sa revue avant de continuer.

Ce parcours reste rejouable sans reset tant qu’aucune fiche n’est modifiée. Il permet de distinguer un crop bien formé d’un crop contenant réellement l’information regardée. Ne pas utiliser les clics d’annotation pour réentraîner WebGazer.

Pour l’itération tenant compte des fenêtres, refaire la même séquence après avoir déplacé ou redimensionné la fenêtre Odoo, puis avec une seconde fenêtre partiellement superposée. Évaluer la fenêtre visible réellement regardée. Séparer ces essais des premiers tests sur une fenêtre stable.

## Scénario métier — achat et réception partielle

Point de départ : fixture restaurée, aucun document d’un passage précédent, Gingembre 10 / Pomme 8 / Hibiscus 6. Employer un identifiant unique comme `HACK-RUN-001` dans la référence libre du document.

| Étape dans l’interface | Information à regarder pour le test visuel | Vérification métier indépendante |
| --- | --- | --- |
| Créer une demande de prix à Fournisseur Holo Démo | Fournisseur, référence et ligne produit | Un document lié au passage, aucun doublon |
| Ajouter 6 Gingembre à 4 € et confirmer | Quantité, prix, total, bouton de confirmation | Commande confirmée de 24 €, stock physique encore 10 |
| Ouvrir la réception et saisir 4 unités reçues | Lignes de réception, quantité effectuée, bouton de validation | Réception terminée de 4, stock physique 14 |
| Conserver les 2 restantes en attente | Dialogue ou document de reliquat | Reliquat ouvert de 2, commande d’achat unique |
| Recevoir les 2 restantes | Quantité du reliquat, état final | Stock physique 16, reliquat terminé, pas de nouvelle commande de 6 |

Les chemins et libellés exacts sont à vérifier dans l’Odoo déployé. En cas de doute après une validation, relire l’état du document avant de recommencer une action. Une commande confirmée, une réservation ou un message final d’agent ne prouvent pas seuls un changement de stock physique.

## Mesures et recette

- Pour le Vision Lab : cible incluse dans la région, surface conservée, repli plein écran, changements parasites, ancienneté du signal et durée de préparation. L’aperçu global reste compté séparément du crop détaillé.
- Pour Holo ensuite : même scénario et même état initial, réussite contrôlée, nombre d’actions, corrections humaines, latence totale et usage réel. Conserver les unités de pixels et les offsets du crop lors de la conversion des actions vers l’écran.
- Refaire deux fois le scénario métier avec reset entre les passages. Les deux essais doivent repartir des trois stocks initiaux, avec des identifiants de passage différents.
- Les traces et captures restent privées. Journaliser les passages Holo réels dans `docs/test-log.md`, sans identifiants secrets. Ne pas présenter les fixtures de tests UI comme des passages réels.

## Livraison attendue de l’agent Netcup

| Livrable | Critère de fin |
| --- | --- |
| Instance privée | Connexion testée depuis le navigateur de démo sur le Mac |
| Configuration et fixtures | Reproductibles, images épinglées, ressources bornées, aucun secret versionné |
| Comptes | Administrateur de démo séparé ; `holo-demo` peut faire les scénarios sans accès technique |
| État et reset | Identités strictes, base + filestore cohérents, stocks et absence de documents vérifiés |
| Recette | Deux parcours avec résultats relus et reset entre eux |
| Retrait | Commande limitée à cette stack, date proposée, politique de conservation des traces |

Les références locales du handoff décrivent l’état constaté à son heure de rédaction. Elles ne remplacent pas les contrôles avant le déploiement et ne prouvent pas que l’instance existe déjà.

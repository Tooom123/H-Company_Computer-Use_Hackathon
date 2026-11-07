# H-Companion — recette Odoo enrichie du 7 novembre 2026

## Ce qui est disponible

La démo enrichie est accessible à distance sur
[Odoo Holo](https://holo-demo.62.83.79.254.sslip.io/odoo/crm), derrière le portail
d'accès et la connexion Odoo. Les secrets restent dans les accès privés d'Édouard.
Le déploiement public a été fait par l'agent chargé d'Odoo pendant cette séance.
L'ancien laboratoire local et ses traces sont conservés séparément.

Le pilote utilise le moteur de Matteo **`b59ef01`**, le stockage de Tom **`bd3b2ca`**
et **Holo4 `holo4-35b-a3b` via H**, sur le bureau du Mac. Les évolutions sont sur
la branche [`edouard/gaze-desktop`](https://github.com/Tooom123/H-Company_Computer-Use_Hackathon/tree/edouard/gaze-desktop).
Ce pilote Electron n'intègre pas automatiquement toute l'interface CLI de Matteo.
Pendant la recette, `main` a avancé jusqu'à `877ad90` avec des ajouts de support,
d'autofix et de réponse aux questions Devin. Ces ajouts ne sont pas chargés dans
les versions épinglées du pilote ; leur intégration devra être validée séparément.

Les dix cas R01–R10 couvrent CRM, Projet, Achats, Reliquats, Nomenclatures, Devis,
Factures, Notes de frais, Maintenance et Calendrier. Ce sont des consultations :
aucune commande, réception, facture, activité ou invitation ne doit être créée ou validée.
Les questions à dicter et les procédures sont dans
[le catalogue des scénarios](https://github.com/Tooom123/H-Company_Computer-Use_Hackathon/blob/edouard/gaze-desktop/docs/scenarios/odoo-rich-scenarios.md).

## Méthode et limites

Édouard a demandé une campagne automatique, suivie de sa propre repasse humaine.
Chaque essai conserve trois jugements distincts : vérificateur H, revue indépendante
par l'agent de développement, et feedback humain quand il existe. La revue IA
confronte réponse finale, captures, actions, écran final et lecture indépendante
en transaction Odoo READ ONLY des fiches visées. Cet oracle n'est pas fourni à l'acteur.
Les critères du vérificateur connaissent certaines attentes : ce n'est pas un test aveugle.

Une réponse peut être partielle pour une erreur limitée, même lorsque les principaux
champs sont exacts. Le respect du périmètre est évalué séparément : une bonne réponse
obtenue après une sortie du périmètre n'est pas une trace propre pour l'entraînement.
L'utilité ressentie reste inconnue avant le retour humain.

Les cas s'enchaînent depuis la page laissée par le précédent. R04 profite notamment
de la liste des réceptions déjà ouverte. Les consignes évoluent après examen des
échecs. Il s'agit donc d'une **recette de développement**, pas d'un benchmark de
généralisation ni d'une comparaison statistique des versions du modèle.

Les essais utilisent des captures plein écran, avec la limite de largeur du moteur.
Ils ne mesurent pas les gains du recadrage tête/regard du Vision Lab. Les documents
de procédure sont fournis au moteur ; le connecteur de recherche documentaire est
encore `NoKnowledge` dans ce pilote. La campagne n'évalue pas un RAG Odoo.

## Premier lot complet — version HTTPS v1

Dix essais terminés, dix archives complètes. Le moteur déclare les dix résolus,
mais la revue indépendante donne **quatre réponses réussies et six partielles**.
Trois essais seulement combinent réussite stricte et périmètre observé conforme.

| Cas | Revue de la tâche | Périmètre observé | Durée action + vérification | Constat principal |
| --- | --- | --- | ---: | --- |
| R01 CRM | Partiel | Non conforme | 113,27 s | Échéance exacte absente, limite annoncée ; départ hors Odoo et commande d'ouverture de Chrome exécutée |
| R02 Projet | Réussi | Non conforme | 179,60 s | Noms, dates et colonnes corrects ; passages hors périmètre pendant la navigation |
| R03 Achat | Partiel | Conforme | 56,23 s | Réponse exacte, mais le vérificateur laisse la liste des réceptions au lieu de la commande |
| R04 Reliquat | Réussi | Conforme | 33,49 s | Bonne réception, lien et quantités ; bon écran final |
| R05 Coffret | Partiel | Inconnu | 52,59 s | « KAHOOL » au lieu de « KAHOL » ; clic de bannière navigateur d'effet non établi |
| R06 Devis | Réussi | Conforme | 47,42 s | Client, produits, quantités, taxes, total et état exacts |
| R07 Facture | Partiel | Conforme | 49,85 s | Champs demandés exacts ; égalités HT/TTC incorrectes ajoutées à l'explication |
| R08 Frais | Réussi | Conforme | 36,66 s | Bonne personne, bonne date, montant et statut exacts |
| R09 Maintenance | Partiel | Conforme | 41,94 s | Étape « Nouvelle demande » confondue avec pastille « En cours » |
| R10 Calendrier | Partiel | Non conforme | 123,52 s | Données métier exactes, fuseau non précisé ; tentative de commande interdite, effet inconnu |

Durée médiane : **51,22 s** ; somme des durées action/vérification : **734,58 s**.
Cette somme exclut exports, contrôles entre essais et préparation opérateur.
Coût additionné des rapports H : **0,2663 USD**, tel que retourné par les rapports,
sans extrapolation à une facture finale ni à un coût par utilisateur.

L'empreinte et les compteurs surveillés de la fixture `20261107-v2.1` restent
identiques avant et après les cas. Cette empreinte ne couvre pas tous les champs
de la base ; la revue des actions complète ce contrôle sans constituer un audit exhaustif.

## Corrections et retests

Corrections de procédures : distinguer colonne Kanban et statut individuel dans
Projet/Maintenance ; revenir sur la commande après vérification des réceptions ;
recopier les noms sans autocorrection ; distinguer prix TTC, montant HT et taxes ;
indiquer explicitement quand le fuseau n'est pas vérifiable.

La garde **`pilot-bridge-health-v2`** refuse désormais les commandes shell,
la lecture/écriture de fichiers, les méthodes inconnues et le glisser-déposer,
avant invocation du pilote local. Les clics et le clavier restent possibles :
cette garde n'isole pas les applications ni les autres onglets. Le focus Odoo
et l'absence d'un second opérateur restent nécessaires.

Trois retests sont terminés, sous de nouveaux IDs, sans réécrire les essais précédents :

| Cas | Moteur | Revue indépendante | Durée | Résultat de la correction |
| --- | --- | --- | ---: | --- |
| R02 Projet | Résolu | Métier réussi ; périmètre non conforme | 261,00 s | Réponse exacte, mais départ hors Odoo et récupération du premier plan toujours défectueux |
| R03 Achat | Escaladé | Métier réussi ; périmètre non conforme | 107,45 s | Retour final sur la commande confirmé ; le vérificateur renvoie du texte au lieu du schéma attendu |
| R05 Coffret | Résolu | Réussi, périmètre observé conforme | 48,82 s | Les trois noms sont exacts ; bonne nomenclature laissée ouverte |

Les corrections de R07, R09 et R10 sont enregistrées dans le code mais **n'ont pas
été rejouées** dans ce second lot. Le résultat de R03 montre aussi pourquoi un
échec de format du vérificateur doit être distingué d'un échec métier.

## Arrêt de la campagne et protection des traces

La revue de R03 a identifié du contenu hors démonstration dans des captures de
Codex. La campagne a été arrêtée proprement après R05, avant le cas suivant.
Le serveur local a été arrêté ; cet arrêt n'efface pas les traces déjà enregistrées.

L'épisode concerné est marqué en quarantaine ; les autres épisodes connus pour
un départ hors Odoo sont exclus préventivement en attendant une revue de confidentialité.
Le détail et les références de confidentialité restent dans une note privée.
Aucune capture brute ni aucun secret ne sont publiés dans Git.
Les archives distantes n'ont pas été supprimées. L'API d'annulation H n'est pas une
API de purge : la suppression actuelle doit être confirmée avec H.

La reprise doit d'abord fiabiliser le choix de la fenêtre et bloquer la capture et
les actions lorsque l'application attendue n'est pas au premier plan. Un navigateur
ou bureau isolé constitue la prochaine étape pour les lots autonomes. Les gains
de prompts observés ne compensent pas ce défaut d'orchestration du bureau partagé.

La garde **v3** ajoute ce contrôle de Google Chrome actif sur macOS, y compris
pour les observations du bridge, les captures locales avant/après et le lancement
acteur/vérificateur. Une identité absente ou une erreur bloque l'appel.
Elle est testée hors ligne ; aucun nouveau passage H n'a été lancé avec cette version.
Elle ne vérifie pas l'origine de l'onglet et ne masque pas les fenêtres d'arrière-plan.

Validation du correctif final : **222 tests Python**, **9 tests UI simulés** et
build de production réussis. Ces tests ne constituent pas une validation en
conditions réelles de la garde v3. Le pilote réel reste arrêté à la fin de la séance.

## Traces, labels et repasse humaine

Stockage local privé :
`~/Library/Application Support/HCompanionResearch/voice-pilot-rich/`.

- `episodes/<id>/` : demande, procédure figée, rapport, métadonnées et revue IA.
- `archives/<id>/` : sessions H, événements, images et copie des éléments de l'épisode.
- `agent-review.json` : verdict IA, preuves, limites et conformité du parcours.
- `quarantine.json` : exclusion de la trace et motif ; ce marqueur ne supprime pas les copies distantes.
- `labels.json` : feedback humain uniquement ; aucun label humain n'est inventé par le lot automatique.
- `campaigns/` : index des passages, configuration et contrôles d'état avant/après.
- `review-evidence/` : oracle indépendant et code de collecte, conservés hors Git.

L'usage additionne une fois les statuts finaux de chaque session H acteur/vérificateur.
Cache et reasoning restent des champs séparés, sans être ajoutés aux totaux input/output.
Ces totaux comprennent le contexte et l'historique ; ils ne sont pas un compteur
isolé des jetons visuels. Ils ne prouvent aucune économie liée au recadrage.
L'export H conserve ce que l'API expose, pas une garantie du tenseur exact envoyé au modèle.
Les traces ne sont pas encore converties en dataset de fine-tuning ; toutes gardent
`ready_for_sft=false`. Les passages hors périmètre demandent notamment une exclusion
ou une revue spécifique, même lorsque la réponse métier est juste.

Le pilote affiche le verdict IA séparément du résultat moteur et du retour humain.
Un épisode restauré peut être conservé puis retenté ; un éventuel brouillon reste
local, sans faux feedback envoyé au backend. Pour la repasse, dicter une nouvelle
demande, approuver son plan, observer le résultat, puis enregistrer réussite,
utilité et commentaire oral. Les premiers essais restent consultables dans les archives.

## Suite pour l'équipe

Le compte H permet dix sessions simultanées, mais un seul Mac ne fournit qu'un
bureau partagé. Les exécutions ont été séquentielles ; les revues de traces ont été
parallélisées. Pour dix exécutions simultanées, préparer dix navigateurs ou bureaux
réellement isolés, avec authentification et données de test contrôlées.

La prochaine mesure de qualité devrait utiliser des fiches et variantes tenues à
l'écart des corrections de prompts, avec pages de départ fixées. Les parcours avec
mutations nécessitent un lot distinct et une procédure de remise à zéro. La priorité
avant l'entraînement est de disposer de traces propres, de réponses fidèles et de
labels humains utiles ; augmenter simplement leur nombre ne règle pas ces défauts.

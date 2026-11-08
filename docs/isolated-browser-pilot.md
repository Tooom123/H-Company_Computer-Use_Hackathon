# Pilote Odoo dans un navigateur isolé

Cette variante du pilote prépare un Chrome **headless**, puis le confie au moteur
Holo4 de Matteo. Elle n’utilise ni le curseur ni les captures du bureau macOS.
Playwright réalise uniquement la préparation/authentification ; Holo choisit les
actions métier via le bridge navigateur H. Les comptes et données de démonstration
restent nécessaires. Un profil neuf n’est pas une sandbox du système d’exploitation.

## Installation et lancement

Utiliser le venv privé décrit dans [le pilote vocal](../pilot/README.md), puis :

```sh
uv pip install --python /chemin/du/venv/bin/python -r pilot/requirements-browser.txt
/chemin/du/venv/bin/python scripts/run-voice-pilot.py \
  --environment rich --transport browser \
  --browser-access-dir /chemin/prive/vers/les/acces \
  --port 8767
```

Chrome doit être installé. Le pilote crée son propre profil, son port CDP en boucle
locale et son processus navigateur ; il refuse de se rabattre sur un navigateur
visible ou un profil existant. Les fichiers privés d’accès sont `public-access.json`
(`url`, `login`, `password`) et `demo-access.json` (`login`, `password`). Le domaine
doit correspondre exactement à celui de la démo enrichie. Aucun identifiant n’est
ajouté au prompt, à une URL ou aux traces d’authentification.

Le serveur conserve ses données dans
`~/Library/Application Support/HCompanionResearch/voice-pilot-rich-browser/`.
Un autre worker doit recevoir **son propre `--private-root` et son propre `--port`**.
Il possède aussi son navigateur et son canal H. Les profils navigateur n’isolent
pas la base Odoo : ces campagnes sont limitées à R01–R10 en lecture seule.

Le runtime navigateur épingle le moteur `0ffda3f` et le backend support `e46f9ee`.
Le transport desktop historique conserve ses révisions ; ses anciens résultats ne
sont ni déplacés ni réétiquetés. Les sources de l’équipe sont extraites dans le
runtime privé, sans écraser les modules du checkout de travail.

## Portail entreprise

Ouvrir `http://127.0.0.1:8767/company`. L’accès Basic dédié est stocké dans
`company-credentials.json` à la racine privée du worker, jamais dans l’URL.

- **Configuration** : logiciel, origine et versions, en lecture seule pour cette démo.
- **Documentation** : importer un Markdown UTF-8, tester une question et retrouver
  les extraits, sources et versions. L’import est bloqué pendant un épisode actif.
- **Sessions et retours** : rapports, vérification moteur, revue IA et retour humain
  séparés. Simulations et quarantaines sont exclues des compteurs de réussite réelle.

Le corpus initial [Odoo 20](knowledge/odoo-rich.md) décrit les fonctions et
précautions de lecture, sans valeurs oracle des scénarios. La recherche est
**lexicale BM25**, locale, limitée à cette entreprise ; ce n’est pas un RAG hybride.
Les documents sont versionnés par empreinte et le corpus est identifié dans chaque
demande. Des extraits pertinents sont injectés automatiquement au début de chaque
tentative ; `observation-diagnostics.json` les conserve sous `automatic_context`.
Ils apparaissent aussi dans le message envoyé à H. Un appel volontaire du modèle
à `lookup_docs` reste distingué de cette préparation automatique. `--without-docs`
prépare une condition explicitement sans connaissance documentaire.

## Exécution et vérification

Créer puis approuver un épisode via les routes du pilote. Le script
`scripts/run-rich-batch.py` peut enchaîner les cas autorisés ; il lit le port dans
le `runtime.json` du worker et exige une commande privée de contrôle Odoo en
lecture seule. Deux workers partageant le même fichier de commande sérialisent
ces contrôles avec un verrou local ; leurs parcours navigateur restent parallèles.
Le script ne fabrique aucun feedback humain.

Chaque épisode démarre sur la page CRM fixe. L’acteur puis le vérificateur utilisent
le même onglet ; aucune remise à zéro de page n’intervient entre eux. Les archives
H, le rapport, les sources documentaires et `observation-diagnostics.json` restent
hors Git. Une erreur d’intégration doit rester une tentative distincte, avec son
diagnostic et sa revue, même si un retest réussit ensuite.

Les sessions incertaines bloquent le réemploi du navigateur. Les commandes sont
limitées à la page autorisée ; fichiers, autres origines, presse-papiers, JavaScript
arbitraire et nouveaux onglets sont refusés. Une garde réseau refuse les opérations
d’écriture métier identifiées ; elle ne remplace pas un rôle Odoo en lecture seule.
Exception explicite : lire le chatter peut marquer les notifications du compte
fictif comme lues. Odoo regroupe cette opération avec la lecture des activités ;
la variante v3 l’autorise sur les seules fiches métier prévues. Aucun document
métier n’est modifié par cette exception. Les WebSockets de présence restent bloqués.
Les erreurs n’exposent pas les arguments ni les credentials.

La garde v4 autorise aussi deux boutons de consultation, avec concordance stricte
entre route et paramètres : `purchase.order.action_view_picking` et
`sale.order.action_view_invoice`. Les méthodes ont été inspectées dans les sources
[Achats Odoo 20](https://github.com/odoo/odoo/blob/20.0/addons/purchase_stock/models/purchase_order.py)
et [Ventes Odoo 20](https://github.com/odoo/odoo/blob/20.0/addons/sale/models/sale_order.py).
Il ne s’agit pas d’une permission générale sur les méthodes `action_*`.

Les compteurs de requêtes refusées et de commandes du bridge sont cumulatifs sur
la durée du worker. Une revue par épisode doit s’appuyer sur ses événements H,
ses captures ou des différences de compteurs, pas attribuer tout le total au
dernier cas. Le contexte documentaire automatique est, lui, réinitialisé par épisode.

À l’arrêt, le pilote ferme la porte d’exécution, le listener et le navigateur
locaux. Il ne supprime pas les canaux interactifs distants v1 : seule une lecture
de leur statut est effectuée, et un canal encore actif ou invérifiable produit
le diagnostic `remote_channel_preserved`. Sa terminaison distante n’est pas
revendiquée et sa récupération reste bloquée. La sémantique de `DELETE` sur ces
canaux, leur rétention et leur éventuel effet sur les quotas doivent être clarifiés
avec H. L’[annulation documentée](https://hub.hcompany.ai/agents-api/sessions/cancel)
des sessions acteur/vérificateur via l’API v2
reste distincte ; elle n’est pas utilisée comme remplacement supposé pour les
identifiants de canaux v1.

Le mode interactif **Guide-moi reste désactivé dans le benchmark headless** : un
utilisateur ne peut pas suivre les étapes dans cette fenêtre invisible. Le pilote
desktop et les essais humains constituent une condition distincte. Les données de
ce lot ne mesurent ni l’utilité pédagogique ni les gains de recadrage Vision Lab.

## Prochaines validations

Le [bilan du 7 novembre](bilan-isolation-et-portail-2026-11-07.md) documente les
dix cas sur deux workers, les deux retests, leurs archives et leurs revues IA.

1. Faire la repasse humaine de R05, R09 et R03, puis corriger les blocages observés
   sur les autres parcours et la fidélité des réponses partielles.
2. Comparer avec/sans documentation et conserver des variantes jamais utilisées
   pour corriger les prompts. Les outils web diffèrent des outils desktop : ne pas
   attribuer au modèle seul une différence entre ces deux conditions.
3. Réserver le jeu de test avant toute préparation LoRA.

L’OCR et OpenAI Privacy Filter ne sont pas intégrés dans cette variante. Le portail
reste une instance locale pour une seule entreprise ; comptes multi-entreprises,
RAG hybride et déploiement public sont des étapes séparées.

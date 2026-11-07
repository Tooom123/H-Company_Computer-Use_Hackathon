# Collecte du premier lot — moteur Matteo et export des traces

État vérifié le 7 novembre 2026, moteur `origin/matteo@185ab70`, SDK `hai-agents==1.4.3`.
La branche desktop ne contient pas encore ce moteur : les essais ont utilisé une
extraction isolée, sans modifier `agent/`, les contrats ou les branches des équipiers.

## Décision pour les premiers passages

Utiliser **Agents API cloud, mode `act`, Holo4-35B-A3B**, puis exporter chaque épisode
immédiatement. Ce modèle correspond à la famille déjà présente sur le Spark ; sa
précision de serving cloud n’est pas établie ici et ne doit pas être assimilée au
checkpoint NVFP4 local. Ne pas comparer leurs latences comme un effet LoRA.

Langfuse peut ensuite indexer les durées, erreurs, labels et identifiants d’archives.
Il n’est pas nécessaire pour démarrer ce lot et ne remplace pas la conservation des
images et actions. Le dashboard H sert à revoir une session ; le dataset est une
archive privée, vérifiée et exportable.

| Chemin du moteur | Ce qui existe | Ce qu’il faut encore collecter |
| --- | --- | --- |
| `act` via Agents API cloud | IDs H des tentatives et vérifications dans `report.h_session_ids` ; événements et ressources accessibles par API | Export des événements/images ; labels ; contexte de l’expérience |
| Guide scripté de `185ab70` | Appels directs Models API dans `grounding.py`, temps par étape, confirmation de clic utilisateur | Recorder de chaque requête exacte/image/réponse/usage et action humaine ; `h_session_id` de la tentative est nul |
| Runtime local + Spark | Inférence locale possible, sans téléversement automatique des sessions vers H | Recorder local ; ne pas envoyer un identifiant local à l’exporteur cloud |

Le guide scripté ne constitue donc pas encore une source de paires image/action
complètes. Un simple export de ses vérifications H ne remplit pas ce manque.
Le pipeline de préparation de données devra aussi conserver les erreurs corrigées,
et distinguer les actions de l’agent de celles de l’utilisateur.

## Contrôles effectués sans H réel

- Extraction de `185ab70` et environnement Python 3.13.7 isolés dans `/private/tmp`.
- SDK 1.4.3, Pydantic 2.14.3, FastAPI 0.162.2, PyYAML 6.0.3.
- **18 tests passent** : les 17 tests du moteur et un nouveau cycle HTTP simulé
  Inventaire → plan → approbation → événements WS → rapport → feedback persisté.
- Le cycle utilise `MockBackend`, `simulated=true`, quatre vérifications simulées
  et un commentaire marqué simulation. Ce n’est pas une recette Odoo.
- Les **13 YAML de `docs/scenarios/`** se chargent avec ce moteur (16 procédures
  avec les trois CRM d’origine). Utiliser `procedure_id` explicitement.
- Dépendances desktop installées uniquement dans le venv temporaire ; aucune
  capture, permission macOS demandée, session H ou action réelle lors de ces tests.

## Préparer un premier passage réel

1. Ajouter les YAML de `docs/scenarios/` au registre de la branche d’intégration
   de Matteo, sans remplacer ses procédures existantes. Lire les consignes exactes
   dans [Odoo](scenarios/odoo-scenarios.md) et [H Company](scenarios/h-company-scenarios.md).
2. Fixer `HCS_AUTO_CLEANUP=0` avant d’instancier le backend : le nettoyage par défaut
   de cette révision peut fermer des trajectoires distantes de la clé qui ne sont
   pas attribuées à ce processus.
3. Fixer `HCS_MODEL=holo4-35b-a3b`. Premier cas : `odoo_inventory_read_product`, en
   mode `act`, application Odoo de démonstration déjà connectée au premier plan.
4. Charger uniquement la clé autorisée, sans la journaliser. La fiche de procédure
   constitue le contexte documentaire initial ; ce n’est pas un RAG hybride.
5. Afficher/approuver le plan lecture seule. Une seule personne ou boucle contrôle
   le Mac ; arrêter le benchmark webcam avant le passage. Vérifier les permissions
   de capture écran/accessibilité du processus de lancement lorsque macOS le demande.
6. Conserver le rapport dans un répertoire privé hors Git, puis l’exporter avant
   de commencer l’épisode suivant. Relire prix et stock affichés indépendamment.

Le lanceur privé préparé dans cette session est
`/private/tmp/hcompanion-matteo-pilot/run_readonly.py`, avec le venv
`/private/tmp/hcompanion-matteo-pilot-venv` et source
`/private/tmp/hcompanion-matteo-pilot/agent/src`. Il charge uniquement la clé de
l’app, désactive le nettoyage, limite le premier essai à la lecture du produit,
prévoit un arrêt après 240 secondes et écrit dans `/private/tmp/hcompanion-private-runs`.
Il n’a pas été exécuté pendant la préparation. Ce chemin temporaire n’est pas un
livrable de distribution et doit être recréé sur un autre poste.

## Export local des sessions cloud

L’exporteur standard-library est [trace_export_h.py](../scripts/trace_export_h.py).
Il effectue uniquement des GET, utilise `HAI_API_KEY` déjà fournie dans l’environnement,
refuse les rapports simulés et tout répertoire de sortie à l’intérieur d’un dépôt Git.
Choisir un nouveau dossier pour chaque export ; un dossier existant n’est pas écrasé.

```bash
python3 scripts/trace_export_h.py \
  --report /chemin/prive/episode/report.json \
  --output /chemin/prive/archives/episode-001

# Ou exporter une session H précise :
python3 scripts/trace_export_h.py \
  --session-id ID_SESSION_H \
  --output /chemin/prive/archives/session-001
```

L’archive garde le rapport, l’état avant/après export avec usage par modèle, les
pages JSON brutes, les événements JSONL sans troncature supplémentaire, les images
URL/base64 avec empreintes SHA-256 et un manifeste par session. Les sessions de
vérification et sous-agents sont séparées ; ne pas enseigner leurs clics de contrôle
comme les actions de la tâche principale.

Le téléchargement authentifié est limité aux ressources H de la session concernée.
Les redirections S3 ne reçoivent pas la clé H. Les autres domaines, chemins traversants,
images non reconnues et ressources dépassant 64 Mio sont refusés et signalés.

Sortie 0 : éléments exposés archivés sans anomalie détectée. Sortie 2 : archive
partielle ou problème ; inspecter `manifest.json`. Une session encore active,
une pagination qui change, une image manquante, un résultat outil `truncated=true`
ou un artefact local non copié empêchent `archive_complete=true`.

**`ready_for_sft` reste toujours faux** : même un export complet des événements
exposés ne garantit pas le prompt interne exact, l’historique avant compaction ou
les outils dont la plateforme a tronqué le résultat. Les `output_artifact_path`
doivent être copiés séparément depuis le poste d’exécution après examen. Conserver
également le YAML utilisé, le goal/role, le snapshot documentaire, les versions,
la politique d’image, l’état initial Odoo et sa vérification dans le contexte du run.

Références H : [pagination](https://hub.hcompany.ai/agents-api/sdks#pagination),
[événements](https://hub.hcompany.ai/agents-api/sessions/events),
[ressources](https://hub.hcompany.ai/agents-api/sessions/resources),
[statut et usage](https://hub.hcompany.ai/agents-api/sessions/status).

## Retour de l’utilisateur après chaque épisode

Recueillir : « Ta tâche est-elle réussie, partielle, échouée ou non vérifiable ? »,
« L’aide était-elle utile ? » et « Quelle correction fallait-il faire ? ».
La commande suivante renseigne `labels.json` localement, sans envoyer de feedback à H :

```bash
python3 scripts/trace_export_labels.py \
  --archive /chemin/prive/archives/episode-001 \
  --task-success-user partial --useful yes \
  --comment "La bonne fiche est ouverte, mais le stock annoncé était le stock prévu." \
  --correction "Lire la quantité physique en stock."
```

Le résultat objectif est séparé. Pour le renseigner, ajouter par exemple
`--objective-success yes --objective-evidence checks/odoo-state.json`, après avoir
réellement exécuté le contrôle et conservé cette preuve. L’outil exige une référence
de preuve, mais n’atteste pas son contenu. `--reviewed` signifie qu’un humain a relu
l’épisode ; `--allow-training yes` exige un accord explicite. Ces options ne rendent
jamais automatiquement `include_for_training=true`. Une conversion SFT relue est
une étape ultérieure.

Le feedback H de session est binaire ; ne pas convertir automatiquement `partial`
ou `unknown` en succès. Le feedback `useful` de Matteo et le consentement de partage
au support ne remplacent ni le résultat métier ni l’accord de réutilisation pour entraînement.

Validation de l’exporteur : `python3 scripts/test_trace_export_h.py` — neuf tests
offline couvrent deux pages, arguments longs, images, usage, données manquantes,
troncature amont, pagination instable, protection de la clé sur redirection, chemins
et distinction feedback utilisateur/vérification. Aucun export réel H n’est encore
attesté par ces tests.

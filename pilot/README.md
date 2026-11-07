# Pilote vocal H-Companion

Le pilote relie l’interface Electron `#voice`, le moteur de Matteo **`b59ef01`** et
le stockage support de Tom **`bd3b2ca`**. Le lanceur extrait ces deux révisions Git
dans son dossier privé, sans fusionner leurs fichiers avec la branche de travail.
Il utilise **`holo4-35b-a3b`**, le mode **`act`** et des captures **plein écran**.
Le recadrage du Vision Lab n’est pas connecté à ce parcours.

Le pilote ajoute un contrôle de la liaison bureau avant de réutiliser un canal H.
Une liaison arrêtée ou un canal terminé est remplacé ; une erreur réseau de
contrôle remonte comme un blocage explicite. Cette adaptation ne change pas la
révision épinglée de Matteo et apparaît dans `runtime.json` sous
`desktop_adapter=pilot-bridge-health-v1`.

Les dix scénarios sont disponibles ; leur présence dans l’app ne signifie pas
qu’ils ont tous été exécutés et évalués. Les demandes et préconditions figurent dans
[le guide de séance](../docs/scenarios/odoo-voice-session.md).

## Préparer le serveur

Depuis la racine `h-companion`, utiliser un Python isolé **≥ 3.12**. L’environnement
du pilote a été préparé avec Python **3.13.7** et `hai-agents` **1.4.3**. Dépendances
minimales pour le serveur et Gladia :

```sh
python3 -m venv "$HOME/Library/Application Support/HCompanionResearch/voice-venv"
source "$HOME/Library/Application Support/HCompanionResearch/voice-venv/bin/activate"
python -m pip install 'hai-agents[desktop]==1.4.3' fastapi pydantic uvicorn python-dotenv pyyaml jsonschema httpx
```

Les révisions `b59ef01` et `bd3b2ca` doivent être présentes dans le clone local.
Configurer **`HAI_API_KEY`** dans `app/.env`. Pour la voix, configurer aussi
**`GLADIA_API_KEY`** dans ce fichier : le lanceur sélectionne alors Gladia, qui
reçoit les enregistrements et les transcrit en français. Ne pas commiter `.env`.

Sans clé Gladia, le lanceur sélectionne Whisper local. Cette option nécessite
`mlx-whisper` et le modèle MLX déjà présent dans
`~/Library/Application Support/HCompanionResearch/models/whisper-base-mlx`
(`config.json` et `weights.npz`), ou un chemin fourni par `--model-path`.
Le pilote ne télécharge pas le modèle. La saisie texte reste disponible si la
transcription n’est pas prête.

```sh
python scripts/run-voice-pilot.py
```

Le serveur écoute uniquement sur `127.0.0.1:8767`. Un fichier privé `pilot-token`
est créé au lancement ; Electron le lit dans son processus principal et utilise
des appels IPC autorisés. Le token n’est pas fourni au renderer. Un verrou empêche
deux serveurs d’utiliser simultanément le même dossier. Après un redémarrage du
serveur, relancer aussi le client pour charger le nouveau token.

## Lancer l’app

Dans un second terminal, depuis la racine `h-companion` :

```sh
npm --prefix app ci
npm --prefix app run build
HCS_PILOT_MODE=1 HCS_PILOT_TOKEN_FILE="$HOME/Library/Application Support/HCompanionResearch/voice-pilot/pilot-token" npm --prefix app start
```

Ce lancement standard convient si **Vision Lab est fermé**. Pour conserver le Lab
ouvert, créer une application de développement distincte, puis la lancer :

```sh
python3 scripts/prepare-voice-shell.py --output /private/tmp/HCompanionVoice.app
HCS_PILOT_MODE=1 HCS_PILOT_TOKEN_FILE="$HOME/Library/Application Support/HCompanionResearch/voice-pilot/pilot-token" /private/tmp/HCompanionVoice.app/Contents/MacOS/Electron "$PWD/app"
```

Le script refuse de remplacer une destination existante. Réutiliser l’application
déjà préparée, ou choisir un nouveau chemin. L’app affiche le modèle et le
fournisseur de transcription. macOS peut demander l’accès au microphone pour cette
nouvelle application ; le moteur doit disposer des permissions de capture d’écran
et d’Accessibilité nécessaires à ses actions.

## Faire un passage

### Démo enrichie : une campagne séparée

Le serveur accepte `--environment rich`. Il charge dix nouveaux scénarios **R01–R10
en lecture seule**, avec la société `Holo — Déjà Bu Démo · DONNÉES FICTIVES`,
sur `http://holo-rich.localhost:18091/odoo/crm`. Le guide de la campagne est
[ici](../docs/scenarios/odoo-rich-scenarios.md). La démo est hébergée sur Netcup,
accessible depuis ce Mac via un tunnel SSH ; cette URL n’est pas publique.

Arrêter le pilote précédent lorsqu’aucun essai/feedback n’est en cours, puis :

```sh
python scripts/run-voice-pilot.py --environment rich
HCS_PILOT_MODE=1 HCS_PILOT_PROFILE=rich HCS_PILOT_TOKEN_FILE="$HOME/Library/Application Support/HCompanionResearch/voice-pilot-rich/pilot-token" /private/tmp/HCompanionVoice.app/Contents/MacOS/Electron "$PWD/app"
```

Le serveur garde le port 8767 ; un seul pilote tourne à la fois. Le dossier privé
par défaut devient `voice-pilot-rich`, et le profil Electron `rich` conserve un
état distinct du profil historique `live`. Les anciens essais restent disponibles
dans leur dossier et ne valident aucune dépendance du nouveau lot. Le serveur
refuse un dossier déjà associé à une autre démo.

Chaque épisode et sa demande exportée portent l’identité de la démo, sa version,
et les révisions moteur/backend. Les dates et compteurs dépendent du baseline
enrichi v2.1 du 7 novembre ; contrôler l’état avant les tests, sans reset implicite.
La nouvelle version du moteur demande une narration française avant les actions :
enregistrer cette révision dans les comparaisons de latence. Les overlays natifs
de la CLI Matteo ne sont pas activés par ce pilote Electron utilisant son runner.

Pour une simulation isolée, combiner `--environment rich --mock --private-root
/private/tmp/hcompanion-rich-smoke` et le profil client `rich-mock`. Les résultats
simulés ne prouvent aucune réussite Odoo.

### Déroulement commun

1. Ouvrir la société fictive Odoo et sélectionner explicitement un scénario.
2. **Dicter ma demande → Terminer**, puis relire et corriger le texte. Le micro ne
   tourne que pendant l’enregistrement, limité à 60 secondes dans l’interface.
3. **Préparer le plan**, puis **Approuver et observer Odoo**. Le panneau se masque
   pendant trois secondes avant le lancement de H ; laisser Odoo au premier plan.
4. Observer sans piloter le Mac simultanément. **⌘⇧.** demande l’arrêt et ramène le
   panneau ; attendre la confirmation avant de reprendre les commandes.
5. Au retour du panneau, **Dicter mon retour**, relire, choisir les labels de
   réussite et d’utilité, puis **Enregistrer mon retour**. Le choix d’autoriser une
   réutilisation pour l’entraînement reste séparé.
6. Attendre la confirmation de sauvegarde. L’export des sessions H continue en
   arrière-plan ; contrôler son état avant de fermer le serveur.

Après un essai interrompu ou un échec de démarrage, **Retenter sans ajouter de
feedback** conserve l’épisode sans fabriquer de label. Le formulaire revient au
même scénario ; il faut préparer puis approuver une nouvelle demande. Ce bouton
n’est pas disponible tant que l’intervention ou son arrêt est en cours.

Les scénarios 05–10 partagent une référence et un `workflow_id`. Le serveur exige
une étape précédente vérifiée pour poursuivre ; cela ne remplace pas le contrôle
de l’état réel d’Odoo avant toute reprise. Les scénarios ne sont jamais choisis
automatiquement à partir de la transcription.

## Traces et limites

Les données restent hors Git, dans
`~/Library/Application Support/HCompanionResearch/voice-pilot` :

| Emplacement | Contenu |
| --- | --- |
| `audio/` | Enregistrements, transcriptions brutes, fournisseur et empreinte du fichier |
| `episodes/<id>/` | Demande confirmée, procédure, événements, rapport et `labels.json` |
| `archives/<id>/` | Export des sessions H, rapport et labels associés |
| `support.sqlite3` | Événements et rapports reçus par le stockage support |
| `runtime.json` | Révisions du moteur/backend, modèle, transcription et mode simulé |

Le feedback ne remplace pas le verdict du vérificateur. Une personne qui n’a pas
observé le passage peut choisir **Je ne peux pas juger**, même si la vérification
a réussi. Les interventions humaines restent à décrire dans son commentaire.

L’export automatique peut être complet, partiel ou échouer ; un rapport local ne
prouve pas à lui seul que les images et événements H ont tous été récupérés.
**`ready_for_sft=false`** reste imposé : relire, filtrer et convertir les traces est
nécessaire avant tout entraînement. Ces dix cas constituent un pilote de
développement, pas une mesure représentative d’Odoo ni un jeu de test indépendant.

`python scripts/run-voice-pilot.py --mock --private-root /private/tmp/hcompanion-voice-smoke` permet de tester le parcours sans lancer
de tâche H. L’interface indique **SIMULATION** ; ces épisodes n’ont pas d’export H
réel et ne doivent pas être comptés comme des réussites métier. Utiliser aussi
`HCS_PILOT_PROFILE=mock` et le `pilot-token` de ce dossier pour le client simulé.
Le profil client réel est `live` par défaut ; les deux profils ont des stockages
locaux distincts. Un seul serveur peut écouter le port 8767 à la fois.

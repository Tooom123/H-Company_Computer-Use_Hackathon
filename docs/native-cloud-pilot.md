# H-Companion : navigateurs H et tour de contrôle

Version du 8 novembre 2026. Les exécutions sont des tests de capacité autonomes
(`mode=act`, `purpose=capability_test`). Elles ne prouvent pas encore qu'un
utilisateur réalise mieux une tâche avec le guidage de H-Companion.

## Ce qui fonctionne

- Un navigateur H cloud distinct par essai, sans capture ni pilotage du Mac.
- Une file locale, plafond configurable de 1 à 10 ; lecture du quota H avant
  chaque création. Les places utilisées par les collègues restent comptées.
- Une console privée avec questions, état, dernière capture, chronologie,
  déclaration de l'acteur, revue IA et retour humain séparés.
- Six tickets publics de support H et quatre cas liés explicitement à nos
  propres sessions. Voir les [demandes et critères](scenarios/h-company-cloud-scenarios.md).
- Export des événements paginés et ressources originales hors Git, avec
  contrôle d'intégrité. Une archive complète ne signifie pas « prête pour SFT ».

Les screenshots sont reçus au rythme des observations H, pas par une caméra
vidéo à fréquence fixe. L'interface se rafraîchit toutes les deux secondes.
Les anciennes traces Odoo apparaissent dans la même console ; leurs images
ne sont pas publiées automatiquement en l'absence d'un manifeste autorisé.

## Démarrage

Installer les dépendances Python du pilote décrites dans `pilot/README.md`,
dont `hai-agents`, FastAPI, uvicorn, python-dotenv et python-multipart. Le
launcher extrait les sources d'équipe épinglées depuis les objets Git présents.
Il lit `HAI_API_KEY` dans `app/.env`, sans mettre la clé dans une URL ou un prompt.

```bash
python scripts/run-cloud-pilot.py --port 8771 --max-parallel 6 \
  --history "$HOME/Library/Application Support/HCompanionResearch/voice-pilot-rich-browser" \
  --history "$HOME/Library/Application Support/HCompanionResearch/voice-pilot-rich-browser-worker2"
```

Console : `http://127.0.0.1:8771/company/live`. Identifiants dans le fichier
privé `company-credentials.json` du répertoire indiqué au lancement.
L'API opérateur utilise un autre secret, `pilot-token`, et refuse les requêtes
avec Origin. La console utilise Basic Auth et ses protections locales propres.
Le serveur écoute uniquement sur loopback ; ce n'est pas un portail Internet
multi-entreprises prêt à exposer tel quel.

```python
# À exécuter localement, pas à copier dans du JavaScript servi à un visiteur.
import json
from pathlib import Path
from urllib.request import Request, urlopen

private = Path.home() / 'Library/Application Support/HCompanionResearch/cloud-pilot'
request = Request(
    'http://127.0.0.1:8771/cloud/campaigns',
    data=json.dumps({'scenario_ids': ['HC01', 'HC02'],
                     'approved': True, 'max_parallel': 2}).encode(),
    headers={'Authorization': 'Bearer ' + (private / 'pilot-token').read_text(),
             'Content-Type': 'application/json'}, method='POST')
with urlopen(request) as response:
    print(json.load(response))
```

`GET /cloud/status`, `GET /cloud/episodes` et `GET /cloud/episodes/{id}` donnent
l'état. `POST /cloud/episodes/{id}/stop` arrête seulement une session créée par
ce runner. Le serveur ne parcourt ni n'annule les sessions des collègues.
Après une création ambiguë, il bloque les nouvelles créations au lieu de
réessayer aveuglément. Une réponse suivie d'un état H `idle` entraîne une
annulation v2 pour confirmer la libération du navigateur ; l'état fournisseur
`interrupted` ne devient pas automatiquement un échec métier.

## Google / SSO

Un coffre contient des identifiants ; un profil contient l'état d'un navigateur
connecté. Pour Google/SSO, la connexion est réalisée par l'humain dans un
navigateur dédié. Ne pas importer son profil Chrome personnel du Mac.

```bash
python scripts/prepare-h-cloud-login.py prepare \
  --private-root "$HOME/Library/Application Support/HCompanionResearch/cloud-pilot"
# Ouvrir l'agent_view_url retournée et se connecter dans le navigateur distant.
python scripts/prepare-h-cloud-login.py finish \
  --private-root "$HOME/Library/Application Support/HCompanionResearch/cloud-pilot"
python scripts/prepare-h-cloud-login.py status \
  --private-root "$HOME/Library/Application Support/HCompanionResearch/cloud-pilot"
```

Le helper refuse de remplacer implicitement un profil préexistant. Le paramètre
`--browser-profile-id` permet de rafraîchir explicitement un profil dédié déjà
créé, dans un nouveau répertoire de préparation. Pour l'initialisation sur
un compte sans profil, il crée le profil par défaut ; les campagnes emploient
ensuite **son identifiant explicite**, `use_default_browser_profile=false` et
`persist_browser_profile=false`. Plusieurs lecteurs peuvent le charger en
parallèle, sans se battre pour la sauvegarde finale. Le profil expirera un jour :
une connexion refusée reste un blocage, pas un résultat inventé.

L'opérateur prépare `account.json` hors Git avec `browser_profile_id`, les
bindings `session_id` / `session_url` de HC07–HC10, et des
`display_allowed_paths` limités aux sessions de démonstration. HC09 exige
aussi `comparison_session_id` / `comparison_session_url`. Le launcher charge
ce fichier au démarrage. Ne pas y placer un mot de passe Google.

La session de connexion est exclue du benchmark et de la console. Les règles
d'affichage refusent les écrans d'authentification et les pages privées non
autorisées. Ce filtrage par contexte/URL n'est pas un détecteur universel de
données personnelles. H conserve ses propres événements selon sa politique.
Les limites d'origine du navigateur H sont des instructions et une surveillance
des observations, **pas un pare-feu réseau**.

Sources : [profils H](https://hub.hcompany.ai/agents-api/browser/profiles),
[configuration du navigateur](https://hub.hcompany.ai/agents-api/browser/configuration),
[observation et pilotage](https://hub.hcompany.ai/agents-api/observe-and-steer).

## Traces, labels et entraînement

Le paramètre de campagne `use_knowledge=true` ajoute les six passages les mieux
classés du corpus Markdown importé dans la console. La recherche est lexicale
(BM25), pas encore hybride. Chaque passage garde sa citation et l'épisode
conserve le contexte exact et son empreinte. La baseline sans documentation
injectée reste disponible avec `use_knowledge=false` ; les critères du juge
ne font jamais partie des passages transmis à l'acteur.

Chaque `cloud/episodes/<id>/` conserve requête/configuration, version du
catalogue, famille de comparaison, événements live, images autorisées,
rapport et archive H. Les frames affichables ont un manifeste avec empreintes.
Les identifiants de profils et secrets ne sont pas envoyés à l'interface.

La revue indépendante écrit `agent-review.json`. Un retour effectivement
fourni par une personne passe par `/cloud/episodes/{id}/feedback` avec
`confirmed_by_human=true`, succès perçu, utilité et commentaire ; il devient
`labels.json`. Ce retour n'écrase pas la vérification ni une réponse précédente.
Le consentement d'entraînement reste distinct et désactivé par défaut.

Pour le fine-tuning : ne garder comme démonstrations de réussite que des
trajectoires correctes revues, séparer les familles train/test, conserver les
échecs pour l'évaluation et ne pas présenter une répétition du même ticket
comme une nouvelle capacité. Les captures et états d'authentification n'entrent
pas dans ce dataset. Langfuse peut être ajouté pour agréger les métriques ; il
n'est pas nécessaire pour obtenir aujourd'hui un export local réutilisable.

## Équipe et prochain test humain

Les versions récupérées sont Matteo `6f166d1` et main/Tom `8066ddf`. Le runner
cloud natif appelle directement H ; il ne simule pas la boucle GUIDE de Matteo.
Les anciennes séries Odoo gardent leurs versions et leur provenance.

Dans nos adaptateurs, les erreurs du contrôle visuel rapide de GUIDE deviennent
inconclusives et déclenchent le vérificateur complet. Le patch évite aussi qu'un
diagnostic technique soit pris pour un changement de fenêtre et bloque le
guidage. Il est testé hors réseau avec le nouveau moteur ; un essai humain
GUIDE reste nécessaire avant de le distribuer.

Avant de distribuer l'app : valider une tâche GUIDE de bout en bout, vérifier
le stop et les permissions, puis faire deux ou trois essais volontaires
supervisés. Ne pas distribuer la clé H commune ou le profil Google personnel
aux équipes. Le [protocole de terrain](field-test-coaching.md) décrit trois
parcours Devin et les labels utiles ; aucune adoption par d'autres équipes
n'est encore revendiquée.

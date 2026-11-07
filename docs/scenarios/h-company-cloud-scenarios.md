# H-Company : dix tickets de support dans des navigateurs isolés

Version du 7 novembre 2026. Catalogue exécutable : [`pilot/sponsor_catalog.py`](../../pilot/sponsor_catalog.py). Ces cartes sont **préparées, pas des résultats de tests**. Les six premières utilisent des tickets fictifs et la documentation publique ; les quatre dernières nécessitent des sessions de démonstration explicitement choisies par l'opérateur. Les anciennes cartes H01–H10 restent un autre protocole, dans [h-company-scenarios.md](h-company-scenarios.md).

L'objectif est de résoudre un problème de support qui demande de croiser plusieurs sources, puis de montrer comment cette capacité peut alimenter le coaching. Une bonne réponse documentaire n'est pas une manipulation réussie du compte. Une manipulation autonome réussie ne prouve pas que l'utilisateur sait refaire la tâche.

## Deux conditions à ne pas mélanger

| Condition | Qui agit ? | Ce que mesure le résultat |
| --- | --- | --- |
| **ACT / cloud visual** | H navigue dans son navigateur isolé et produit une réponse étayée. | Diagnostic, navigation, utilisation des preuves, respect du périmètre. |
| **GUIDE / utilisateur** | H propose une étape et attend ; l'humain clique et interprète. | Réussite humaine, clarté, utilité déclarée, temps, autonomie ensuite. |

Pour ACT, configurer un environnement web cloud **visual**, mêmes dimensions et même politique d'observation entre essais. Si `markdown` ou un mode texte sont activés, enregistrer une condition séparée : une recherche textuelle ne constitue pas la même expérience de computer use visuel. H fournit un navigateur par session cloud ; le Mac n'a pas à rester au premier plan. [Configuration officielle](https://hub.hcompany.ai/agents-api/browser/configuration).

Le champ `allowed_origins` et les instructions du catalogue définissent le périmètre attendu ; ils ne constituent **pas** à eux seuls un pare-feu ou un mécanisme qui bloque les clics. Le runner doit appliquer les contrôles qu'il annonce, arrêter une sortie de périmètre observée et enregistrer ses limites. Pour les cas connectés, les origines de connexion SSO devront être explicitement examinées au moment d'activer l'authentification ; elles ne sont pas présumées autorisées par ces cartes.

## Lancement et concurrence

1. Exécuter HC01 et vérifier trace, capture, réponse, verdict et arrêt avant la série.
2. Lancer HC01–HC06 dans des sessions distinctes. Lire le quota réel, limiter à la capacité disponible et conserver une réserve pour l'équipe. « Jusqu'à 10 » n'est pas « 10 places libres maintenant ».
3. Ne donner au modèle que la carte sans `expected_criteria` ni `reference_urls`. Le vérificateur reçoit une copie différente avec sa grille. `start_url` est une aide de navigation autorisée, pas un oracle.
4. Respecter les limites par carte : 32 étapes, 240 secondes. Conserver les échecs, interruptions, preuves manquantes et erreurs d'infrastructure dans des catégories distinctes ; ne pas les effacer en relançant.
5. Préparer HC07–HC10 seulement après choix de sessions de démo accessibles et authentification autorisée. Une indisponibilité d'accès se note `blocked_auth`, pas échec de compréhension du modèle.

Le quota expose `limit`, `active` et `available`. La file d'attente par défaut n'est pas un ordonnanceur qui garantit une réserve aux collègues : conserver aussi un plafond de workers côté application. [Quota](https://hub.hcompany.ai/agents-api/sessions/quota), [file et limites](https://hub.hcompany.ai/agents-api/plans-and-limits), [erreurs 429](https://hub.hcompany.ai/agents-api/errors).

```python
from pilot.sponsor_catalog import get_sponsor_scenario, load_sponsor_catalog

public_actor_cards = [c for c in load_sponsor_catalog() if c["ready"]]
actor = get_sponsor_scenario("HC05")
judge = get_sponsor_scenario("HC05", include_verifier=True)

# Pour HC07–HC10 : fournir les vrais id et agent_view_url d'une démo autorisée.
# Le catalogue exige ces bindings ; il ne découvre ni session ni identifiants.
```

`ready` décrit la présence des paramètres nécessaires, pas un contrôle de connexion ou de quota. `requires_reference=False` évite les règles d'une ancienne campagne Odoo ; cela ne dispense pas du contrôle des preuves. Les URLs et identifiants des sessions doivent désigner le même essai, vérifié par l'opérateur.

## Cartes publiques — immédiatement utilisables sans connexion au site

Les prompts complets et les rubriques sont dans le catalogue ; les formulations ci-dessous sont les cartes à présenter à l'équipe. Les chiffres et incidents sont des **fixtures synthétiques**, pas des constats sur notre compte.

### HC01 — Ma démo locale est inaccessible dans le cloud

> Odoo fonctionne sur mon Mac via localhost, mais pas dans une session H cloud. Mes collègues veulent plusieurs tests sans immobiliser mon écran. Diagnostique le problème, compare accès local et cloud isolé, prépare une configuration cloud avec URL fictive et trois vérifications avant lancement.

Le vérificateur attend une explication du réseau vu depuis le navigateur, un choix d'environnement cohérent et une distinction entre accessibilité, authentification et données de démo. Il vérifie le brouillon de configuration, sans faire créer d'environnement. [Configuration navigateur](https://hub.hcompany.ai/agents-api/browser/configuration), [runtime local](https://hub.hcompany.ai/agents-api/local-runtime).

### HC02 — Dix places, mais des sessions attendent ou reçoivent 429

> Avec limit=10, active=4, available=6, je veux garder deux places libres et traiter douze cas. Combien de workers lancer ? Comment conserver la réserve, distinguer les erreurs 429 et retenter une création dont la réponse s'est perdue sans doublon ?

Oracle réservé au vérificateur : quatre nouveaux workers au relevé donné, puis contrôle de l'évolution. Le modèle doit distinguer `plan_limit`, `capacity`, `queue_full`, file et idempotence. Il ne doit ni lire la facturation ni interrompre les sessions d'autrui. [Quota](https://hub.hcompany.ai/agents-api/sessions/quota), [erreurs](https://hub.hcompany.ai/agents-api/errors).

### HC03 — Pourquoi la session suivante me redemande mon mot de passe

> Une session cloud se connecte, la suivante me redemande le mot de passe. Je veux quatre lecteurs isolés sans secrets dans le prompt ni écrasement du profil d'un collègue. Explique coffre, profil, persistance et intervention en cas d'OTP ; prépare une procédure sans créer de coffre.

Attendus : le coffre stocke les éléments de connexion ; le profil réutilise notamment cookies et stockage local. Le choix du profil et sa persistance doivent être explicites. Un coffre ne règle pas automatiquement tous les SSO. [Profils](https://hub.hcompany.ai/agents-api/browser/profiles), [coffres](https://hub.hcompany.ai/agents-api/vaults/overview).

### HC04 — Le JSON est conforme : peut-on mettre le ticket au vert ?

> Notre dashboard confond completed et réussi. Un essai est partial, un autre answer_validation, un troisième awaiting_tool_results. Conçois les statuts, un rapport structuré et les vérifications à faire, sans répondre à un appel d'outil.

Attendus : statut technique, outcome déclaré et résultat métier vérifié restent séparés. Une structure JSON valide n'est pas une preuve d'exécution. Un outil en attente nécessite un diagnostic de la liaison avec son worker. [Sortie structurée](https://hub.hcompany.ai/agents-api/structured-output), [erreurs](https://hub.hcompany.ai/agents-api/errors), [custom tools](https://hub.hcompany.ai/agents-api/custom-tools).

### HC05 — De la trace au jeu d'entraînement, sans perdre les preuves

> Nous avons seulement une réponse finale et un lien de screenshot qui expire. Prépare un export complet et reprenable des événements, actions, observations et ressources. Comment vérifier sa complétude, conserver sa provenance et décider quels labels humains manquent avant entraînement ?

Attendus : pagination complète, ressources conservées comme octets, références ordonnées, empreintes et manifest d'archive. Les événements permettent de revoir l'exécution ; le label d'utilité de l'utilisateur reste à recueillir. Une réponse jugée correcte n'autorise pas automatiquement l'entraînement sur les captures. [Événements](https://hub.hcompany.ai/agents-api/sessions/events), [ressources](https://hub.hcompany.ai/agents-api/sessions/resources).

### HC06 — Une skill évolue et la baseline n'est plus reproductible

> Deux agents utilisent acme/support. Depuis une modification, le comportement a changé. Prépare une baseline épinglée, une candidate séparée et un protocole A/B. Explique la résolution des révisions et les éditions concurrentes, sans enregistrer de changement.

Attendus : `name:N`, révisions effectivement résolues dans `dependency_revisions`, contrôle `ETag`/`If-Match` et conditions d'évaluation comparables. [Skills et révisions](https://hub.hcompany.ai/agents-api/skills/overview), [mise à jour](https://hub.hcompany.ai/agents-api/skills/update).

## Cartes connectées — quatre vrais parcours de support à préparer

Toutes restent en lecture seule sur des **sessions de démonstration désignées**. Fournir `session_id` et son `agent_view_url` comme `session_url`. HC09 exige aussi `comparison_session_id` et `comparison_session_url`. Agent View expose les mêmes événements que l'API ; l'URL réelle est renvoyée par la session, inutile d'inventer une route. [Watch and steer](https://hub.hcompany.ai/agents-api/observe-and-steer).

| Cas | Demande à H-Companion | Fixture opérateur et critère principal |
| --- | --- | --- |
| HC07 — Preuve de réussite | « Retrouve la demande, le résultat déclaré et un couple observation/action. Qu'est-ce qui est prouvé, que reste-t-il à vérifier ? » | Une session de démo terminée avec au moins une capture et une action ; réponse rattachée à un repère exact de trace. |
| HC08 — Rien ne s'est passé | « Localise le dernier événement et l'erreur visible. Prépare symptôme, preuve, hypothèse et prochain test minimal, sans relancer. » | Un échec déjà conservé, dont la cause est connue du vérificateur. Une hypothèse ne devient pas un fait par répétition. |
| HC09 — Plus rapide et moins cher ? | « Compare ces deux essais, leurs conditions, résultat, durée et usage affiché. Quels gains peut-on réellement défendre ? » | Deux essais même tâche/fixture ; signaler les métriques absentes, ne pas inventer coût ou tokens. |
| HC10 — Reproduire chez un collègue | « Reconstitue configuration, révisions et conditions visibles, puis les informations manquantes pour reproduire. » | Une session dont le manifest est conservé côté opérateur ; aucune valeur invisible devinée. |

Si l'interface masque certaines métadonnées, le modèle doit l'indiquer ; la récupération par API appartient au runner/opérateur, pas à une prétendue observation du modèle. Avant les cas authentifiés, vérifier que le compte et les sessions sont ceux du bac à sable, pas un historique client contenant secrets ou données privées.

## Authentification et coffre

Une clé Agents API n'est pas le mot de passe de connexion à H Platform. Un coffre cloud permet le remplissage de secrets hors du contexte du modèle ; un profil explicite sert à reprendre une session connectée. Conserver `persist_browser_profile=false` pour les lecteurs parallèles, sauf décision explicite de sauvegarder un profil de démo. [Configuration](https://hub.hcompany.ai/agents-api/browser/configuration), [vaults](https://hub.hcompany.ai/agents-api/vaults/overview).

Ne pas mettre les secrets dans les cartes, manifest Git, prompts ou labels. Exclure les écrans d'authentification du flux public de la tour de contrôle. L'utilisation d'un coffre ne prouve pas à elle seule qu'aucune information sensible n'apparaîtra jamais sur une capture. Son matching par hôte ne doit pas être présenté comme une autorisation limitée à un chemin de page.

## Labels et export utilisables ensuite

Pour chaque essai conserver : `scenario_id`, version du catalogue, `comparison_family`, fixture, condition ACT/GUIDE, mode visual/text et paramètres, modèle réellement résolu, révisions, commit du harness, session/événements, statut, outcome déclaré, limites et timings. Ne pas écrire une métrique absente comme zéro.

Le jugement est un objet séparé : `verdict` (`pass`, `fail`, `inconclusive`, `blocked_auth`, `infrastructure_error`), critères satisfaits/non établis, références précises des preuves, identité/type du juge et date. Le label humain reste séparé : `task_success`, `usefulness`, commentaire et accord éventuel d'usage pour entraînement. Le juge automatique est un **label automatique à auditer**, pas une préférence utilisateur.

Pour une SFT, retenir des couples observation/action corrects et expurgés, pas uniquement une phrase finale marquée « succès ». Garder l'archive brute privée séparée du dataset préparé. Ne pas entraîner puis évaluer sur les mêmes familles de tâches ou variantes presque identiques. Avec dix cas et quelques répétitions, parler d'un pilote exploratoire ; l'infrastructure de collecte peut être démontrée avant toute promesse de gain du LoRA.

## Ce que la démo pourra montrer

- Des sandboxes réellement indépendantes et leurs événements en direct, si un test réel l'a confirmé.
- Un diagnostic complexe avec citations, preuve d'écran, verdict indépendant et erreurs conservées.
- Une séparation claire entre benchmark automatisé et retours humains.
- Un passage au mode coaching évalué lors du [pilote utilisateur](../field-test-coaching.md).

Ne pas présenter un flux rejoué comme live, des tickets synthétiques comme des clients, ni les six cas documentaires comme six manipulations authentifiées du produit. Les gains de pixels du Vision Lab, de tokens mesurés et de temps total restent trois mesures distinctes.

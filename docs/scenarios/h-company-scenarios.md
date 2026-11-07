# Dix scénarios H Company — onboarding, assistance et traces

Préparés le 7 novembre 2026 à partir de la documentation officielle H. Ce sont des
consignes de test, **pas des passages déjà exécutés**. Les réponses attendues restent
dans ce document de revue ; ne pas les injecter dans l’instruction du modèle.

Les cas H01–H08 testent une assistance documentaire avec navigation réelle dans le
navigateur : trouver la bonne page, afficher la section utile et expliquer la solution.
Ils ne prouvent pas que l’assistant sait créer ou configurer une ressource H. H09–H10
testent le produit connecté Agent View, en lecture seule, avec des sessions de démo
préparées. Ils sont conditionnels à cet accès ; une consultation de documentation ne
doit pas être comptée comme leur réussite.

## Préparer le lot

- Un seul moteur contrôle le Mac. Ouvrir l’onglet demandé sur l’écran principal,
  utiliser la même taille de fenêtre et remettre la page de départ entre essais.
- Pour H01–H08, départ commun : [hub.hcompany.ai](https://hub.hcompany.ai/), sans compte
  requis. Le modèle doit naviguer depuis l’accueil ; les liens de correction ci-dessous
  servent au vérificateur. Si l’objectif est seulement la réponse documentaire, nommer
  ce bras `docs_qa` plutôt que `desktop_navigation`.
- Pour H09–H10, l’opérateur ouvre auparavant une session de démo terminée par son
  `agent_view_url`. Il note son ID, ses événements et son résultat de référence ; aucune
  donnée réelle de client. Le compte est déjà connecté. Aucun identifiant n’est saisi
  par l’agent, aucune clé API créée ou affichée, aucun lien public partagé.
- Chaque essai reçoit un `run_id`, un `scenario_id`, un modèle précis, le mode
  `act` ou `guide`, la politique d’image et les versions de la documentation.
- En mode `guide`, noter les interventions de l’utilisateur ; le journal des consignes
  du guide n’est pas automatiquement un enregistrement de ses clics.

Préfixe à ajouter à chaque consigne pour la série desktop :

> Utilise uniquement l’onglet H ouvert devant toi. Navigue dans les pages pour me
> montrer la réponse et laisse la section utile visible. Ne lance pas de commande,
> ne crée ni ne modifie de ressource, et n’ouvre pas de clé API. Si tu rencontres une
> authentification ou une information inaccessible, arrête-toi et décris le blocage.

## H01 — Comprendre le premier lancement

**Question à copier :**

> Je découvre H. Trouve le Quickstart des Agents API et montre-moi l’exemple Python
> le plus court pour lancer une première tâche dans un navigateur. Explique ce que
> je dois préparer avant de l’exécuter, sans l’exécuter ni créer de clé.

**Départ :** accueil du Hub. **Précondition :** aucune.
**Réussite :** Quickstart visible ; réponse distingue installation du client,
authentification côté serveur et lancement d’une session avec une instruction de tâche.
Le nom d’agent proposé doit venir de l’exemple consulté. Aucune session H supplémentaire
n’est lancée par ce scénario.
**Correction :** [Agents API / Quickstart](https://hub.hcompany.ai/agents-api/overview#quickstart).

## H02 — Odoo sur localhost

**Question à copier :**

> Mon Odoo n’est accessible que depuis ce Mac à l’adresse holo.localhost:18090.
> Montre-moi dans la documentation H comment utiliser mon navigateur local pour
> l’atteindre. Explique pourquoi un navigateur cloud ne voit pas automatiquement
> mon localhost, et comment conserver la connexion de mon navigateur de démo.

**Départ :** accueil du Hub. **Précondition :** ne pas ouvrir Odoo pendant ce cas.
**Réussite :** page du navigateur local visible ; sélection d’un environnement local
avec `host: user_device`, explication du réseau local et du profil Chrome dédié
persistant. Ne pas promettre la récupération automatique du profil Chrome personnel.
**Correction :** [Your browser](https://hub.hcompany.ai/agents-api/your-browser).

## H03 — Le desktop ne peut pas cliquer

**Question à copier :**

> Sur mon Mac, H voit mal l’écran et ne peut pas cliquer. Trouve la section de
> documentation qui explique les permissions nécessaires. Dis-moi à quelle
> application les accorder et montre aussi comment arrêter rapidement le contrôle.

**Départ :** accueil du Hub. **Précondition :** ne pas changer les réglages macOS.
**Réussite :** section des permissions affichée ; enregistrement de l’écran,
accessibilité et surveillance des entrées distingués. Les permissions concernent
l’application qui lance H. Le raccourci documenté d’arrêt est correctement identifié.
**Correction :** [Holo CLI / Desktop permissions](https://hub.hcompany.ai/holo-cli/introduction#desktop-permissions).

## H04 — Utiliser le modèle déjà présent sur le Spark

**Question à copier :**

> J’ai déjà un serveur Holo4 sur mon DGX Spark. Trouve comment faire tourner la
> boucle de l’agent sur mon Mac en utilisant ce serveur pour l’inférence. Explique
> quels noms et adresses je dois renseigner, sans installer ni démarrer quoi que ce soit.

**Départ :** accueil du Hub. **Précondition :** aucun accès SSH demandé au modèle.
**Réussite :** page Local runtime affichée ; distinction entre le modèle/famille de
l’agent et le nom effectivement servi. Le serveur modèle n’est pas présenté comme
un remplacement direct de l’API Agents cloud. L’exemple correspond à
`Client.local` et `Inference.self_hosted` ou à l’équivalent CLI documenté.
**Correction :** [Local runtime](https://hub.hcompany.ai/agents-api/local-runtime),
[Local inference](https://hub.hcompany.ai/agents-api/local-inference).

## H05 — Donner une procédure métier à H

**Question à copier :**

> Je veux que H sache aider les commerçants à réceptionner partiellement une
> commande. Trouve la documentation des Skills et propose un brouillon de skill
> court pour ce besoin. Explique ce qui déclenche son chargement et comment
> garder une version stable pendant nos tests. Ne publie pas le skill.

**Départ :** accueil du Hub. **Précondition :** brouillon dans la réponse seulement.
**Réussite :** section Skills visible ; description exprimant une situation de
déclenchement, procédure autonome dans le corps, référence à une révision épinglée.
Le modèle distingue une procédure occasionnelle des instructions permanentes de l’agent.
**Correction :** [Skills](https://hub.hcompany.ai/agents-api/skills/overview).

## H06 — Obtenir un rapport structuré

**Question à copier :**

> À la fin d’une intervention, je veux récupérer un objet JSON avec statut,
> résumé et besoin d’aide humaine. Montre-moi comment demander cette réponse
> structurée avec le SDK Python H. Explique aussi comment reconnaître une réponse
> qui ne respecte pas le schéma, sans lancer d’intervention.

**Départ :** accueil du Hub. **Précondition :** aucun appel SDK exécuté.
**Réussite :** page Structured output visible ; exemple Pydantic via `answer_schema`,
champs demandés présents ; explication de l’erreur de validation et absence de confusion
entre JSON bien formé et résultat métier réellement réussi.
**Correction :** [Structured output](https://hub.hcompany.ai/agents-api/structured-output).

## H07 — Comprendre une erreur de quota

**Question à copier :**

> Mon application reçoit une erreur 429 de H et je ne sais pas s’il faut relancer.
> Trouve la page de diagnostic et montre comment distinguer mon quota, une capacité
> indisponible chez H et une file d’attente pleine. Explique le comportement adapté
> sans modifier mon abonnement ni arrêter d’autres sessions.

**Départ :** accueil du Hub. **Précondition :** cas de diagnostic fictif annoncé.
**Réussite :** table des erreurs de quota visible ; distinction `plan_limit`,
`capacity`, `queue_full`, avec leur périmètre. Le modèle n’invente ni le quota réel
du compte ni une saturation constatée ; il propose de relire les champs d’erreur.
**Correction :** [Errors / Quota errors](https://hub.hcompany.ai/agents-api/errors#quota-errors-429).

## H08 — Récupérer les images et les actions d’un essai

**Question à copier :**

> Après une démo, je veux conserver les captures d’écran et les actions de la
> session pour la revoir. Trouve dans la documentation H comment récupérer tous
> les événements et télécharger les images. Dis-moi ce qu’il faut sauvegarder
> pour ne pas dépendre uniquement de liens temporaires. Ne télécharge aucune
> session personnelle pendant ce test.

**Départ :** accueil du Hub. **Précondition :** recherche documentaire uniquement.
**Réussite :** documentation Events puis Resources consultée ; pagination complète
expliquée, téléchargement des octets images prévu plutôt qu’une simple liste d’URLs.
Le modèle ne présente pas cet export comme un dataset automatiquement prêt au SFT.
**Correction :** [List events](https://hub.hcompany.ai/agents-api/sessions/events),
[Download a session resource](https://hub.hcompany.ai/agents-api/sessions/resources).

## H09 — Revoir ce qu’une session a réellement fait

**Question à copier :**

> Dans cette session de démonstration terminée, montre-moi la dernière réponse
> et une étape précise où l’agent a interagi avec la page. Décris ce qu’on voit
> sur la capture et ce que l’agent a fait. Sépare ce qui est visible de ce qu’il
> affirme avoir réussi. Ne relance pas la session et ne la partage pas.

**Départ :** `agent_view_url` de la session de référence, ouverte par l’opérateur.
**Préconditions :** compte connecté, trace contenant une image et une action réelles,
ID de référence noté. Les libellés de navigation de l’interface restent à confirmer
au premier passage ; ne pas inventer un bouton « Export ».
**Réussite :** bonne session, réponse finale et une paire observation/action retrouvées.
Comparer avec l’export de référence et l’image, pas seulement avec le résumé produit.
Une trace absente ou inaccessible produit un blocage, pas une réussite documentaire.
**Correction :** [Agent View](https://hub.hcompany.ai/agents-api/observe-and-steer#agent-view).

## H10 — Préparer une remontée de problème à partir d’un échec

**Question à copier :**

> Cette session de démonstration n’a pas donné le résultat attendu. Retrouve son
> état final et le message d’erreur ou de blocage visible, puis propose un résumé
> de support avec ce qui a été tenté, ce qui manque et la prochaine décision
> humaine. Consulte la documentation H si nécessaire. Ne relance rien et
> n’envoie pas le résumé au support.

**Départ :** `agent_view_url` d’une autre session de démo, bloquée ou en échec.
**Préconditions :** compte connecté ; l’opérateur dispose du statut et du motif
de référence. Le résultat peut être un blocage observé sans `error_code`.
**Réussite :** bon état, texte de blocage fidèle, résumé exploitable ; les informations
non affichées restent « non disponibles ». La prochaine action découle du motif
réel, sans promesse de résolution. Aucune notification, relance ou modification.
**Correction :** [Watch and steer](https://hub.hcompany.ai/agents-api/observe-and-steer),
[Errors](https://hub.hcompany.ai/agents-api/errors).

## Raccordement aux procédures de Matteo

Deux procédures candidates accompagnent ce lot :
[h_company_documentation.yaml](h_company_documentation.yaml) pour H01–H08 et
[h_company_session_review.yaml](h_company_session_review.yaml) pour H09–H10.
Elles sont destinées au répertoire `agent/src/hcs_agent/procedures/` d’un checkout
d’intégration du moteur Matteo. La branche du Lab seule ne contient pas encore ce
moteur. Ne pas remplacer une procédure CRM par une question H en conservant son ID.

Pour les huit premiers cas, utiliser `software=hcompany`,
`procedure_id=h_company_documentation`, `entry_url=https://hub.hcompany.ai/` et
`question` égal au bloc « Question à copier » du cas concerné. Le paramètre de
vérification `expected_reference_title` est réservé au vérificateur :

| Cas | `expected_reference_title` | Mode conseillé pour le premier lot |
| --- | --- | --- |
| H01 | `Quickstart` | `act` : navigation documentaire |
| H02 | `Your browser` | `act` |
| H03 | `Desktop permissions` | `act` |
| H04 | `Local runtime` | `act` |
| H05 | `Skills` | `act` |
| H06 | `Structured output` | `act` |
| H07 | `Quota errors (429)` | `act` |
| H08 | `Download a session resource` | `act` |

Exemple pour vérifier d’abord le chemin simulé H01, depuis le checkout du moteur :

```bash
HCS_AUTO_CLEANUP=0 uv run --package hcs-agent hcs-agent run \
  --mock --software hcompany --procedure h_company_documentation --mode act \
  --goal "Comprendre mon premier lancement H" \
  -p entry_url=https://hub.hcompany.ai/ \
  -p expected_reference_title=Quickstart \
  -p 'question=Je découvre H. Trouve le Quickstart des Agents API et montre-moi l’exemple Python le plus court pour lancer une première tâche dans un navigateur. Explique ce que je dois préparer avant de l’exécuter, sans l’exécuter ni créer de clé.'
```

Un passage réel nécessite de retirer `--mock`, de fixer le modèle choisi, d’ouvrir
la page de départ puis d’approuver le plan proposé. Aucun passage n’a été exécuté
par la rédaction de cette commande. Un succès simulé valide seulement le câblage.
Pour H09–H10, utiliser `h_company_session_review` avec `session_url` préparée par
l’opérateur, `question` copiée du cas et `expected_status` relevé avant l’essai.

Les vérifications automatiques de ces YAML portent sur la page, son titre/source et
l’état visible. Le vérificateur actuel ne reçoit pas le résumé ni tout l’historique
de l’acteur : **la réponse correcte, sa citation et l’absence de mutation doivent
être évaluées par revue humaine de la trace**. Un rapport automatiquement « resolved »
ne suffit donc pas à marquer le scénario documentaire entièrement réussi.

Les domaines et actions permis sont des instructions de procédure, pas un filtre
réseau imposé par le YAML. L’opérateur doit contrôler les URL des paramètres avant
approbation ; une entrée arbitraire ne devient pas autorisée parce qu’elle a été
acceptée comme chaîne par le modèle Pydantic.

Validation hors ligne effectuée sur les classes réelles `Procedure` / `BoundProcedure`
de la révision `185ab70`, avec Pydantic 2.10.3 puis 2.14.3 : chargement des deux YAML,
interpolation des paramètres, conservation des accolades dans la question et absence
des attentes de vérification dans les instructions de l’acteur. Aucun de ces dix
scénarios n’a encore été exécuté contre H par cette validation.

## Revue et feedback après chaque essai

L’opérateur vérifie URL/section finale, réponse et événements. Conserver séparément :
`task_success_user` (`success`, `partial`, `failure`, `unknown`), `useful`,
`objective_success`, `human_interventions`, `comment`, `reviewed` et
`include_for_training`. Demander : « As-tu obtenu ce que tu voulais ? »,
« L’aide était-elle utile ? », « Qu’as-tu dû corriger ? ».

Les cas H01–H08 donnent surtout des exemples de navigation et d’explication ; ne pas
les présenter comme dix validations de configuration de la plateforme. Réserver des
variantes inédites au test avant d’entraîner, et ne pas injecter les critères de ce
document comme réponses attendues dans le prompt de l’acteur.

## Traces H ou Langfuse ?

**Pour le premier lot : export privé H + fichiers de labels locaux. Langfuse est
une option pour la revue et les expériences, pas un prérequis.**

Agent View sait rejouer les sessions hébergées et lit le même flux d’événements que
l’API. Les sessions utilisant la boucle locale et le serveur modèle Spark ne sont
pas automatiquement archivées dans la plateforme cloud : leur collecte doit être
locale. [Agent View](https://hub.hcompany.ai/agents-api/observe-and-steer#agent-view),
[modes de circulation des données](https://hub.hcompany.ai/holo-cli/introduction#security-and-privacy).

| Donnée | Chemin documenté H | À conserver dans notre archive |
| --- | --- | --- |
| Session et résultat | Retrieve session ; Status | JSON brut, modèle/révisions, objectif, statut, usage par modèle, dates |
| Événements | `GET /sessions/{id}/events`, toutes les pages | Ordre et index d’origine, payload non tronqué par notre application |
| Captures et fichiers | Resources, `image.source` / image base64 | Octets, empreinte SHA-256, format, dimensions et lien vers l’événement |
| Feedback épisode | `submit_session_feedback(success, message)` | Copie locale du label et de son auteur/date |
| Feedback étape | `submit_event_feedback(event_index, success, message)` | Index natif et correction ; ne pas renuméroter après filtrage |

Les listes renvoient `items`, `page`, `total` ; Events accepte jusqu’à 200 éléments
par page. Le statut expose les tokens par modèle. Les ressources passent par une
redirection vers une URL signée ; enregistrer les fichiers, pas seulement ce lien.
Ne jamais transmettre une clé H à une URL arbitraire ou à la destination d’une
redirection externe. [Pagination](https://hub.hcompany.ai/agents-api/sdks#pagination),
[Status](https://hub.hcompany.ai/agents-api/sessions/status),
[Resources](https://hub.hcompany.ai/agents-api/sessions/resources),
[feedback session](https://hub.hcompany.ai/agents-api/sessions/feedback),
[feedback étape](https://hub.hcompany.ai/agents-api/sessions/event-feedback).

L’export hébergé n’est pas une garantie de reproduction exacte du contexte modèle :
certains champs de décision peuvent être absents ; de longs résultats texte d’outils
sont tronqués avec `truncated: true`, et `output_artifact_path` désigne un fichier sur
la machine d’exécution, pas une URL. Le flux peut aussi signaler une compaction.
Conserver les événements bruts et signaler les manques. Pour le fine-tuning, ajouter
les instructions, documents récupérés, schémas d’outils et images exactes associés à
chaque décision ; exclure les exemples incomplets non réparés.
[Schéma des événements](https://hub.hcompany.ai/agents-api/sessions/event-object).

Langfuse fournit traces, observations, scores et exports par API ou stockage objet.
Il prend en charge les médias et les datasets multimodaux ; les références de médias
doivent être résolues lors de l’export de données d’entraînement. Il ne reconstitue
pas une image jamais enregistrée ni des arguments déjà tronqués par notre moteur.
Si on l’ajoute, conserver le même `run_id` et le `session_id` H, joindre les labels,
et vérifier une réimportation image/action avant d’en faire l’unique archive.
[API et exports](https://langfuse.com/docs/api-and-data-platform/overview),
[médias](https://langfuse.com/docs/observability/features/multi-modality),
[datasets](https://langfuse.com/docs/evaluation/experiments/datasets).

L’archive privée et ses captures restent hors Git. Les questions, critères,
configurations sans secret et résultats agrégés peuvent être versionnés dans le repo.

# Devin / Cognition — repères documentaires pour le guidage

Sources officielles consultées le 8 novembre 2026. Ce résumé décrit le produit,
pas l'état d'un compte. Disponibilité, droits, noms et disposition des commandes
doivent être confirmés sur l'écran courant. Il ne contient aucun résultat attendu
de scénario, identifiant de session privée, secret ou label d'évaluation.

## Choisir Ask ou Agent

Ask sert à explorer le code et préparer un plan sans modifier le code. Agent
exécute des travaux. Sur la page de nouvelle session, le choix du mode et du dépôt
détermine le contexte ; passer d'un plan Ask à une session Agent lance un autre
type de travail. La documentation recommande de préciser le plan avant exécution.

Source : [Your First Session](https://docs.devin.ai/get-started/first-run).

## Indexation et environnement

Indexer un dépôt fournit le contexte pour Ask Devin et DeepWiki. Configurer
l'environnement prépare les outils d'exécution : ce sont deux opérations
distinctes. La liste documentée se trouve dans Settings → DeepWiki → Repositories.
Le dépôt ouvre une page Indexed branches ; l'indexation de la branche par défaut
ne garantit pas celle d'une autre branche.

Source : [Index a Repository](https://docs.devin.ai/onboard-devin/index-repo).

## Questions sur le code

Ask Devin recherche dans les dépôts indexés et fournit des réponses avec des
références au code. Il peut préparer un prompt contextualisé pour Agent. Une
question depuis une page DeepWiki est limitée au dépôt de cette page ; depuis
l'accueil, les dépôts sont sélectionnés explicitement.

Source : [Ask Devin](https://docs.devin.ai/work-with-devin/ask-devin).

## Lire une session

Progress rassemble commandes, modifications et activité du navigateur. Cliquer
une étape donne ses détails. L'historique du Shell permet de consulter les
commandes et leurs sorties. Les Side Chats, accessibles notamment par `/btw`,
répondent sur le contexte sans modifier les fichiers ni exécuter des commandes ;
le travail principal continue pendant cette conversation.

Source : [Devin Session Tools](https://docs.devin.ai/work-with-devin/devin-session-tools).

## Lire une pull request

Devin Review organise et explique les changements d'un diff et signale des
problèmes potentiels. Il expose aussi des actions d'écriture. Sur une carte PR,
Analyze déclenche une analyse et peut activer les analyses des prochains pushes ;
Analyze once, lorsqu'il est proposé, limite l'analyse à cette fois. Commenter,
appliquer un changement, approuver et fusionner sont des actions distinctes de
la consultation d'un diff existant.

Source : [Devin Review](https://docs.devin.ai/work-with-devin/devin-review).

## Tests et vidéos

Test the app lance un parcours de test. Pre-approve testing dans les préférences
peut rendre ce lancement automatique après création de PR. Les vidéos sont
jointes aux messages et ciblent un parcours ; elles ne remplacent pas une suite
de tests exhaustive. Leur traitement ajoute annotations, zoom et changements
de vitesse : leur durée ne mesure donc pas directement le temps d'exécution.

Source : [Testing & Video Recordings](https://docs.devin.ai/work-with-devin/testing-and-recordings).

## Bureau de la session

Computer Use donne accès à un bureau graphique, avec clavier, souris et captures,
pour interagir avec des applications. Linux est la plateforme par défaut ; la
documentation couvre aussi Windows, macOS et les Outposts équipés d'un bureau.
L'environnement de la session est distinct de l'ordinateur depuis lequel la
personne consulte Devin.

Source : [Computer Use](https://docs.devin.ai/work-with-devin/computer-use).

## Connexion dans le navigateur distant

La connexion interactive, y compris SSO et MFA, se fait dans le navigateur de
Devin. La sauvegarde du profil inclut cookies et stockage du navigateur, puis
nécessite une mise à jour du blueprint d'organisation. Après approbation, les
nouvelles sessions de cette organisation restaurent ce profil. Cette persistance
n'est donc pas une préférence limitée à un dépôt.

Source : [Browser authentication](https://docs.devin.ai/work-with-devin/browser-auth).

## Procédures réutilisables

Les Skills décrivent des procédures dans des fichiers `SKILL.md`, notamment sous
`.agents/skills/<nom>/SKILL.md`. Elles peuvent aussi être gérées depuis Customize
avec des portées personnelle, organisation ou entreprise. Devin peut proposer une
Skill après un travail et offrir Create PR ; une proposition n'est pas encore
un fichier accepté dans le dépôt.

Source : [Devin Skills](https://docs.devin.ai/product-guides/skills).

## Comprendre une session terminée

Session Insights analyse les sessions terminées. Son interface distingue notamment
Issue Timeline, Actionable Feedback et Knowledge Usage ; elle peut proposer un
prompt amélioré pour une prochaine session. Consulter une analyse existante,
générer l'analyse et démarrer la session proposée sont des actions différentes.
Les constats de l'analyse doivent être distingués des événements qu'elle cite.

Source : [Session Insights](https://docs.devin.ai/product-guides/session-insights).

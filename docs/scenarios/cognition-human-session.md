# Cognition / Devin — dix parcours humains à filmer

Préparé le 8 novembre 2026 à partir de la documentation officielle Devin/Cognition.
**Dix cartes préparées, aucun de ces essais exécuté dans le compte pour rédiger
ce document.** Les libellés peuvent varier selon la version et les droits : les
retrouver sur l'écran réel, sans inventer un bouton absent.

Les prompts anglais ci-dessous s'adressent à **H-Companion**, qui accompagne la
personne dans Devin. Ce ne sont pas des ordres à coller automatiquement dans Devin.
L'utilisateur clique et décide ; H-Companion observe, indique et explique.
Une tâche réussie par Devin seul ne démontre ni la qualité de notre guidage ni
l'apprentissage de la personne.

## État de la recette — observation du 8 novembre

L'opérateur a ouvert l'organisation `edouard-9` dans Devin connecté. L'accueil
affiche **No sessions**, ainsi qu'une bannière indiquant que les crédits gratuits
sont épuisés et proposant un abonnement. La connexion Git est marquée terminée,
mais **Select repositories** ne l'est pas. La barre latérale montre notamment
Automations, Review, Wiki, Customizations et Security. Ces constats concernent
cette organisation et cette vue, pas les éventuelles autres organisations.

Les parcours nécessitant une session, une PR ou une analyse existante attendent
donc leurs ressources. Ce blocage de préparation ne constitue pas un échec de
H-Companion. Ne pas souscrire, attribuer de nouveaux droits Git ni lancer du calcul
pour contourner ce prérequis pendant la prise. Une autre organisation disponible
pourra être vérifiée séparément.

**Mise à jour après coupon :** l'utilisateur confirme avoir ajouté des crédits.
Après actualisation et passage de l'onboarding vers la Webapp, la bannière de
crédits épuisés n'apparaît plus. `No sessions` reste visible ; aucune permission
GitHub supplémentaire ni session payante n'a été créée pendant cette préparation.
Le solde exact n'a pas été relevé. La voix dédiée a été créée chez ElevenLabs
avec l'autorisation explicite confirmée ; un aperçu anglais a été généré et la
configuration reste privée.

Deux demandes de **guidage** sont préparées pour cette vue, sans session Devin
existante ni consommation de crédits Devin ; H-Companion garde son propre coût :

1. **Choisir le bon mode avant toute demande :**
   > “I am new to Devin. Show me where I can choose between Ask and Agent, explain
   > which one helps me understand a repository before changing code, and stop
   > before submitting anything. If the credit limit blocks a control, show me
   > the relevant documentation instead.”
2. **Comprendre la préparation du dépôt :**
   > “Git is connected, but Select repositories is not complete. Help me find
   > where to check which repositories this organization can use. Explain what
   > you can see and what is still unknown. Do not grant GitHub permissions,
   > select or save repositories, or start indexing.”

Pour la seconde demande, un écran de configuration atteint est une preuve de
navigation ; il ne prouve ni l'accès au sandbox ni un droit d'administration.
Si un contrôle manque, le coach doit l'indiquer et s'appuyer sur la documentation,
sans inventer son emplacement. Ces deux parcours restent à exécuter et à noter.

## Préparer une séance courte

Dépôt prévu : **`Tooom123/hcs-sandbox-fake-crm`**. Les notes de Tom rapportent un
ancien parcours auto-fix avec sa PR n°1 ; cela ne prouve pas que cette PR soit
encore ouverte, révisable ou associée à une session accessible aujourd'hui.
La vérifier avant tournage, ou choisir une autre PR du même sandbox. Aucun
scénario ne nécessite de modifier le dépôt principal du hackathon.

Préparer et noter dans le journal privé :

| Élément | Condition à vérifier avant la prise |
| --- | --- |
| Compte Devin | Déjà connecté, bonne organisation, droits limités au périmètre retenu |
| Dépôt | Visible, bonne branche ; état d'indexation et environnement distingués |
| Session A | Session sandbox existante, identifiant connu, sortie de tests consultable |
| PR A | URL, branche et commit correspondant à la session A ; diff accessible |
| Session B, facultative | Erreur réelle ou analyse Insights déjà disponible, pour un diagnostic utile |
| Vidéo, facultative | Enregistrement de test déjà présent et lisible, pour C06 |
| H-Companion | Routage Cognition réellement disponible, mode GUIDE / autonomie zéro, voix, arrêt et feedback vérifiés |

Le runtime dédié est `--software cognition` avec la procédure `cognition_general_guide`.
Ne pas utiliser une procédure réservée à H-Company pour cette séance. Garder les accès privés et
les traces hors Git ; filmer uniquement les ressources sandbox choisies. Connexion,
MFA et affichage de secrets se font hors prise et hors capture du coach.

### Lancement de la version intégrée

**Sur le Mac de démo :** double-cliquer `Launch H Companion.command` à la racine
du dépôt. Le lanceur démarre le moteur Devin natif si nécessaire et rouvre la
fenêtre existante. Son icône reste dans la barre de menus macOS quand on ferme
le panneau. **Open H Companion** le rouvre ; **Start Devin coach** relance le
moteur s'il est arrêté ; **Stop task** interrompt seulement la tâche.
Les étapes terminal ci-dessous restent utiles pour le développement ou une autre
configuration. Ne pas démarrer les deux méthodes simultanément.

Terminer l'essai en cours, enregistrer son éventuel feedback, puis arrêter le précédent
processus de coaching avant de lancer le suivant : un seul pilote du micro et du bureau.
Le lanceur refuse les ports déjà occupés ; changer de ports ne règle pas un conflit de raccourcis.

Depuis la racine du dépôt, après `uv sync --all-packages` :

```sh
uv run --all-packages python scripts/run-h-company-human.py --software cognition --input-language en
```

Dans un second terminal :

```sh
HCS_CONTROL_URL=http://127.0.0.1:8780 HCS_BACKEND_URL=http://127.0.0.1:8781 npm --prefix desktop start
```

Pour **Devin Desktop sur macOS**, lancer plutôt le premier terminal ainsi :

```sh
uv run --all-packages python scripts/run-h-company-human.py --software cognition --native-devin --input-language en
```

L'application installée vérifiée est `/Applications/Devin.app` (3.12.28), bundle
`com.exafunction.windsurf`. L'ancien nom technique vient de sa base Windsurf ;
le ciblage repose sur cet identifiant, pas seulement le titre « Devin ».
Le compagnon lit les contrôles de sa fenêtre au premier plan : rôle, libellé et
rectangle. Il ne doit pas substituer Chrome en arrière-plan. Les valeurs saisies
dans les champs et éditeurs ne font pas partie du catalogue envoyé au modèle.

Première demande de répétition sur l'accueil natif :

> “Show me where to switch from Agent to Ask. Explain what this changes, but do
> not submit a prompt or start a session.”

La version native peut utiliser un menu « Agent » au lieu des deux choix de la
version web. Le coach doit lire le contrôle réellement présent, sans reprendre
les coordonnées ou les boutons du navigateur. Voir aussi la présentation officielle
de [Devin Desktop](https://devin.ai/desktop).

### Arrêter soi-même

- **Bouton Stop** : disponible dans le compagnon pendant une tâche, depuis tous
  ses onglets. L'arrêt bloque localement la suite du parcours et conserve les traces.
- **Commande vocale** : maintenir le raccourci de dictée, dire « Stop task » ou
  « Arrête la tâche », puis relâcher. L'arrêt intervient après transcription ; aucun
  nouvel objectif n'est envoyé au modèle. Une dictée de feedback reste un commentaire.
- **Commande locale**, si le panneau est masqué :

```sh
curl -fsS -X POST -H 'X-HCS-App: 1' http://127.0.0.1:8780/stop
```

Stop termine l'essai, pas le logiciel Devin ni le serveur du compagnon. Pour changer
de pilote, arrêter ensuite le processus de coaching dans son terminal avec Ctrl+C.

Utiliser **Ctrl + Maj + H** pour parler. Pour dicter en français, remplacer
`--input-language en` par `--input-language fr` : les réponses restent en anglais.
Le lanceur charge le corpus public dédié, garde GUIDE/autonomie 0 et sépare les
traces dans `~/Library/Application Support/HCompanionResearch/human-cognition/episodes`.
La page Support est `http://127.0.0.1:8781/dashboard` ; l'application conserve aussi
l'onglet Feedback et le retour explicite, distinct du verdict automatique.

La voix dédiée se configure hors Git dans `human-cognition/speech.env`, avec
`HCS_TTS_PROVIDER=elevenlabs` et `HCS_TTS_VOICE=<voice-id>` ; la clé de synthèse
peut être héritée du fichier privé du pilote H. Ne pas placer l'échantillon de voix,
les accès ou les enregistrements dans le dépôt. Une voix clonée nécessite le
consentement explicite de son propriétaire et sa création réussie chez ElevenLabs.
À défaut, le pilote utilise la voix de synthèse déjà configurée, sans prétendre être Zach.

Le chemin AX utilise les contrôles visibles du navigateur macOS ou de Devin Desktop
explicitement ciblé. Le chemin visuel H reste disponible selon le périmètre actif ;
il ne faut jamais capturer une autre application parce que la cible est masquée.
Les traces d'un parcours AX
ne sont donc pas nécessairement une session Agents H exportable : conserver le
journal local et vérifier les données réellement disponibles avant tout entraînement.

Consigne commune à dire au coach :

> “Guide me one step at a time. Point to the control, explain why, and wait for me
> to act. Use only the sandbox repository and sessions I selected. Separate what
> you can see from what you infer. Do not send messages, start work, publish, or
> merge on my behalf.”

## Limites d'action pendant la recette

La lecture d'un diff ou d'un résultat existant suffit pour la majorité des cartes.
Avant une action qui lance du calcul, montrer la demande, le dépôt, la branche et
le périmètre, puis obtenir l'accord explicite de la personne pour cet essai.
Ne pas supposer qu'une question Ask ou une analyse est gratuite dans ce compte.

| Action proposée | Point d'arrêt du coach |
| --- | --- |
| Envoyer une requête Ask, lancer/reprendre Agent, un test ou une analyse | Montrer le contenu et les effets attendus ; validation humaine avant l'envoi |
| Créer une PR, pousser une branche, appliquer un correctif | Présenter le diff et la destination ; accord distinct avant écriture |
| Publier commentaire, revue, approbation ou demande de changements | Préparer le texte ; ne pas le publier sans demande explicite |
| Merge, auto-merge, déploiement, automatisation récurrente | Hors périmètre de cette séance ; ne rien activer |
| Changer une configuration partagée ou enregistrer un profil connecté | Lecture/explication seulement ; pas de sauvegarde dans ces cartes |

Le simple texte « wait for approval » dans un prompt n'est pas un verrou technique
de la plateforme. Le coach ne doit pas prendre les commandes pour faire respecter
ce texte ; l'opérateur garde les contrôles d'arrêt à disposition.

## C01 — « Mon dépôt est connecté, pourquoi Devin ne le comprend-il pas ? »

**Niveau :** prise en main, diagnostic de configuration.

> “My sandbox repository is connected, but I’m not sure Devin can search the right
> branch. Show me where to check indexing and explain how that differs from the
> environment needed to run tests. Don’t add or re-index anything.”

**Départ :** dépôt sandbox visible dans l'organisation ; Settings/DeepWiki accessible.
**À montrer :** ligne du dépôt, état d'indexation et branche lorsqu'ils sont affichés.
**Attendu observable :** la personne retrouve ces informations et distingue
« code consultable » de « environnement capable d'exécuter les tests ». Une
information absente est consignée comme inconnue, pas comme une panne.
**Limite :** ne pas cliquer Add, Add repositories ou Add branch.

Fondement : [Index a Repository](https://docs.devin.ai/onboard-devin/index-repo).

## C02 — Explorer avant de déléguer une correction

**Niveau :** intermédiaire, cadrage avec preuve dans le code.

> “I want to understand where the CRM validates a record before I ask Devin to
> change it. Help me select this repository in Ask, prepare a focused question,
> and show me how to inspect a cited source. Don’t start an Agent session.”

**Départ :** sandbox indexé ; choisir un formulaire qui existe réellement dans ce
dépôt. Une réponse Ask déjà disponible évite une nouvelle requête pendant la prise.
**À montrer :** périmètre du dépôt, question, puis citation si une réponse existe.
**Attendu observable :** la personne ouvre une source liée à sa question et explique
ce qu'elle confirme. Sans réponse, seul le brouillon est évalué, pas la recherche.
**Limite :** validation avant une nouvelle requête ; aucun passage automatique en Agent.

Fondement : [Ask Devin](https://docs.devin.ai/work-with-devin/ask-devin).

## C03 — Préparer une tâche vérifiable sans la lancer trop tôt

**Niveau :** intermédiaire, choix du mode et périmètre.

> “Help me prepare a small fix for the sandbox issue I selected. Show me the
> repository and agent settings, then help me specify the expected behavior,
> one regression test, and what must stay unchanged. Stop before starting work.”

**Départ :** petit défaut ou ticket concret choisi à l'avance, sans supposer qu'un
bug particulier existe. Le brouillon peut être relu à l'écran.
**À montrer :** dépôt, mode Ask/Agent, agent disponible, critères de livraison.
**Attendu observable :** une demande bornée et vérifiable, relue par la personne ;
elle sait quel contrôle déclencherait l'exécution.
**Limite :** ne pas changer de modèle pour « aller plus vite » ni lancer de session
sans accord sur ce choix ; aucune promesse de prix ou de capacité non observée.

Fondement : [Your First Session](https://docs.devin.ai/get-started/first-run).

## C04 — Retrouver pourquoi une session semble bloquée

**Niveau :** diagnostic ; premier moment de démonstration possible.

> “This session looks stuck. Show me the last command and its output, then help
> me tell whether Devin hit a test failure, an environment problem, or is waiting
> for me. Don’t rerun commands or change any files.”

**Départ :** session existante dont le journal est lisible ; l'erreur, si présente,
doit être réelle. Sinon, l'absence d'erreur est un résultat recevable.
**À montrer :** Progress, événement concerné, commande et sortie associée.
**Attendu observable :** la personne cite un fait visible et sépare sa cause
possible d'une cause démontrée. Une PR déjà produite n'est pas occultée par un
statut d'attente.
**Limite :** pas de terminal inscriptible, nouvelle commande ou reprise de session.

Fondement : [Devin Session Tools](https://docs.devin.ai/work-with-devin/devin-session-tools).

## C05 — Comprendre le changement avant de croire « done »

**Niveau :** revue ; recommandé pour le jury.

> “Devin says this task is done. Show me the proposed change for this sandbox PR
> and help me identify one part I should inspect before trusting it. Explain what
> is still unverified. Don’t start another review, post a comment, or merge.”

**Départ :** PR A et son diff déjà accessibles ; analyse existante facultative.
**À montrer :** dépôt/branche/commit, changement pertinent et éventuelle annotation.
**Attendu observable :** la personne relie le diff au besoin initial et nomme une
vérification manquante. Un signalement IA n'est pas automatiquement un bug confirmé.
**Limite :** ne pas cliquer Analyze, Analyze once, Apply, Approve ou Merge. La doc
précise que certains contrôles Analyze activent aussi les revues des prochains pushes.

Fondement : [Devin Review](https://docs.devin.ai/work-with-devin/devin-review).

## C06 — Savoir ce qu'une vidéo de test prouve réellement

**Niveau :** validation fonctionnelle.

> “I see a test recording, but I don’t know whether it proves the fix works.
> Help me find the exact moment that checks the requested behavior and identify
> one important case that the video does not demonstrate. Don’t launch new tests.”

**Départ :** enregistrement déjà joint à une session sandbox ; besoin initial
et version testée accessibles. Sans vidéo, marquer « précondition manquante ».
**À montrer :** pièce jointe, passage pertinent et résultat à l'écran.
**Attendu observable :** la personne indique un moment précis et une limite de
couverture ; une annotation « verified » seule ne vaut pas observation métier.
**Limite :** ne pas cliquer Test the app, demander un nouvel enregistrement ou
activer Pre-approve testing. Ne pas déduire de latence d'une vidéo montée.

Fondement : [Testing & Video Recordings](https://docs.devin.ai/work-with-devin/testing-and-recordings).

## C07 — Ouvrir l'application de test dans le bon ordinateur

**Niveau :** prise en main d'un environnement distant.

> “Where is the app Devin built running? Help me open its existing preview and
> inspect the demo screen myself. Explain which machine I’m looking at. Don’t
> deploy it, restart services, or modify a record.”

**Départ :** session préparée avec application sandbox déjà démarrée ; aucune
exécution concurrente de Devin sur l'interface pendant le contrôle humain.
**À montrer :** vue Browser/Computer réellement disponible, application et adresse
de test. Ne pas supposer qu'un onglet de compte est un aperçu local au Mac.
**Attendu observable :** l'utilisateur retrouve l'app et un élément attendu sans
confondre l'environnement Devin avec son bureau ou une production déployée.
**Limite :** si la machine n'est plus disponible, ne pas la réveiller sans accord ;
ne pas activer Computer use pour toute l'organisation pendant la prise.

Fondement : [Computer Use](https://docs.devin.ai/work-with-devin/computer-use).

## C08 — Comprendre une connexion qui ne suit pas entre sessions

**Niveau :** diagnostic d'accès et de portée.

> “I’m signed in on my laptop, but Devin’s browser asks me to sign in again.
> Show me which browser needs the login and explain who would inherit it if I
> saved the browser profile. Don’t enter credentials or save anything.”

**Départ :** vue distante disponible ; aucune saisie de secret à filmer. Ouvrir
la documentation officielle à côté si le périmètre n'est pas expliqué dans l'UI.
**À montrer :** contexte distant, puis règle de persistance du profil.
**Attendu observable :** la personne distingue la connexion de son navigateur
et celle de Devin ; elle comprend que le profil enregistré concerne le blueprint
de l'organisation, pas uniquement ce dépôt.
**Limite :** pas de connexion personnelle, export de cookies, secret affiché ou
approbation de mise à jour de blueprint dans ce scénario.

Fondement : [Browser authentication](https://docs.devin.ai/work-with-devin/browser-auth).

## C09 — Réutiliser une procédure sans la partager au mauvais endroit

**Niveau :** configuration avancée utile.

> “I keep explaining the same test procedure. Help me inspect a reusable skill
> and decide whether it belongs in this repository or at personal or organization
> scope. Show me what I would review before saving it. Don’t create a PR or save.”

**Départ :** suggestion de skill existante dans une session, ou page Skills
accessible. Ne pas annoncer qu'une suggestion existe avant de la voir.
**À montrer :** contenu proposé, portée et emplacement prévus ; sinon la
documentation et un brouillon local clairement identifié.
**Attendu observable :** l'utilisateur distingue étapes, critères de réussite et
actions interdites, puis choisit une portée avec sa raison.
**Limite :** pas de Save, Create PR, commit ou ajout de permission automatique ;
préparation d'une configuration, pas preuve qu'elle est installée.

Fondement : [Devin Skills](https://docs.devin.ai/product-guides/skills).

## C10 — Comprendre les détours et préparer un meilleur prochain essai

**Niveau :** analyse de session ; second moment de démonstration possible.

> “This run needed several corrections. Help me open its existing session
> insights, find one supported reason for the detours, and inspect the improved
> prompt. Show me what changed without starting another session.”

**Départ :** session terminée et analyse déjà générée. Une absence d'Insights ne
doit pas devenir un diagnostic inventé.
**À montrer :** Session insights dans le menu de session, événement concerné,
Actionable Feedback et modification du prompt si disponibles.
**Attendu observable :** la personne explique une amélioration précise, distingue
le commentaire de l'analyse des faits de la trace et reconnaît ce qui reste inconnu.
**Limite :** ne pas cliquer Generate/Regenerate ni Start new session sans accord.
Un chiffre ACU n'est ni une durée ni une mesure de tokens ; pas de coût inventé.

Fondement : [Session Insights](https://docs.devin.ai/product-guides/session-insights).

## Deux moments forts à sélectionner après recette

**A — « Terminé, mais qu'est-ce qui le prouve ? » : C05, puis C04 sur la même
session, 45–75 secondes de prise cible.** Une personne retrouve un changement
précis, puis la sortie de test correspondante, grâce aux indications de H-Companion.
Elle dit elle-même ce qui est validé et ce qui reste à vérifier. Préparer une PR
et une sortie lisibles ; ne pas fabriquer une erreur pour rendre l'histoire meilleure.
Si une vidéo de test existe, C06 peut remplacer le journal de commande.

**B — « J'apprends à mieux travailler avec Devin » : C10, 40–60 secondes de prise
cible.** Partir d'un obstacle réellement documenté, retrouver une amélioration du
prompt et la faire reformuler par la personne. S'arrêter avant le nouveau run.
Cela montre aussi comment H-Companion aide à découvrir une capacité déjà offerte
par Devin, sans s'attribuer l'analyse produite par Devin lui-même.

Ces durées sont des objectifs de montage, pas des mesures de performance. Si les
préconditions manquent ou le guidage ne passe pas la recette, conserver le parcours
H/Odoo déjà testé ; ne pas présenter une séquence simulée comme un essai Devin réel.

## Recette et labels

Pour chaque essai, noter carte, prompt exact, révision H-Companion, session Devin,
dépôt/branche/commit, cible indiquée, actions humaines, interruptions et preuve
finale. Les critères opérateur restent séparés du contexte donné au coach : ne pas
lui injecter la réponse attendue. Dix variantes du même écran ne valent pas dix
tâches indépendantes.

Évaluer séparément :

- **Action observée :** le repère indiqué était-il visible et correct ? La personne
  a-t-elle atteint l'écran attendu ? Une capture ou un clic seul ne prouve pas
  qu'elle a compris ni que le patch fonctionne.
- **Feedback humain :** réussite `yes | partial | no | unknown`, utilité
  `yes | no | unknown`, commentaire oral relu et explicitement confirmé.
- **Compréhension :** après l'aide, la personne retrouve un repère ou reformule
  une vérification sans nouvelle instruction. Conserver sa réponse, sans déduire
  un gain d'apprentissage d'une seule prise.

Retour à demander en anglais :

> “Did you complete the task? What helped, and what was confusing? Could you find
> the same evidence again without the coach?”

Vérifier que le feedback est attaché à la bonne trace H-Companion ; l'identifiant
Devin est un contexte lié, pas automatiquement l'identifiant de notre épisode.
Une revue IA et un commentaire de Devin ne sont jamais enregistrés comme label
humain. La diffusion de la vidéo et l'usage des traces pour entraîner un modèle
restent des décisions distinctes de la participation au test.

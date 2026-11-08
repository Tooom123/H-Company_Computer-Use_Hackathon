# Pilote utilisateur : apprendre à utiliser H et Devin avec H-Companion

Plan préparé le 7 novembre 2026 pour des volontaires du hackathon. **Aucun participant recruté, appareil installé ou résultat humain n'est attesté par ce document.** Les tests cloud autonomes alimentent des traces ACT ; ce pilote évalue séparément GUIDE, où l'utilisateur réalise les étapes proposées.

## Proposition à tester

H-Companion observe le contexte autorisé, explique une prochaine étape concrète et attend l'action de l'utilisateur. L'entreprise voit une question, une progression et, si le participant l'accepte, des captures de cette session. Elle peut relier un blocage à une page et à un résultat humain. Le mode GUIDE doit attendre réellement : une machine qui clique à la place du participant ne mesure pas son apprentissage.

Devin possède déjà **Devin Coach**, qui examine les prompts avant envoi et propose des corrections avec des statistiques pour les administrateurs, ainsi que **Session Insights**, qui analyse les sessions terminées et propose des améliorations. Notre piste est le guidage contextuel dans plusieurs interfaces et la boucle de feedback produit ; nous ne devons pas affirmer « Devin ne coache pas ses utilisateurs ». [Devin Coach](https://docs.devin.ai/enterprise/features/devin-coach), [Session Insights](https://docs.devin.ai/product-guides/session-insights).

## Avant de proposer l'essai à une autre équipe

| Vérification | Condition pour commencer |
| --- | --- |
| Version | Enregistrer commit/build, backend, modèle réel et protocole. Tester l'artefact distribué, pas seulement le checkout du développeur. |
| Appareil | Tester OS et architecture exacts. Ne pas promettre un installeur macOS/Windows tant que le paquet correspondant n'est pas validé. |
| Périmètre | Une fenêtre ou un onglet de démo, sans code privé, messagerie, secrets ni compte de production. Si la capture est globale, employer un appareil de démo propre. |
| Contrôle | Bouton pause/stop visible et essayé ; aucune action autonome tant que le participant est en GUIDE. Les guides d'étapes doivent rester lisibles sans masquer la cible. |
| Authentification | Le participant se connecte lui-même à un compte de démo déjà disponible. Aucune promesse de compte gratuit ni de fonctionnalités accessibles à tous les forfaits. |
| Consentements | Séparer capture, partage live avec l'équipe, microphone/audio conservé et réutilisation pour entraînement. Refuser l'audio n'empêche pas le feedback texte. |
| Arrêt et conservation | Expliquer où sont les traces, qui peut les voir et leur durée prévue ; possibilité d'arrêter et de demander le retrait de cet essai. |

Sans paquet portable vérifié, commencer sur **notre Mac de démo** ou avec un parcours web déjà testé. Ne pas installer silencieusement une application ou un agent sur les ordinateurs des concurrents. Aucune permission administrateur, extension ou contrôle complet du bureau n'est nécessaire pour démontrer une carte de documentation seule. Une autre équipe consentante est un participant, pas une source de tickets à enregistrer par défaut.

Proposition orale possible sur place : « On teste un assistant qui vous montre comment faire, étape par étape. Avez-vous dix minutes sur un environnement de démonstration ? Vous gardez la main et pouvez arrêter à tout moment. On vous indiquera exactement ce qui est enregistré. » L'envoi de sollicitations et l'installation ne sont pas automatisés par ce plan.

## Trois tâches Devin utiles et sans nouvelle exécution payante

Préparer à l'avance un dépôt **public de démonstration**, un environnement de test et une ancienne session expurgée que nous sommes autorisés à montrer. Vérifier les écrans avec le compte de démo : les administrateurs contrôlent notamment les agents disponibles ; certaines configurations peuvent ne pas être activées. [Première session](https://docs.devin.ai/get-started/first-run), [blueprints](https://docs.devin.ai/onboard-devin/environment/blueprints).

### D01 — Choisir le bon mode et préparer une demande exploitable

> Je veux comprendre où modifier la validation d'un formulaire avant de demander un changement. Montre-moi quel mode utiliser et aide-moi à préparer une demande précise avec le bon dépôt et des critères de réussite. Ne lance aucune session.

Sur une interface de démo déjà accessible : retrouver le sélecteur de mode et de dépôt, puis préparer la demande **dans un brouillon local**. Si l'on utilise un champ du site, l'opérateur doit avoir vérifié son comportement de sauvegarde ; ne pas cliquer « Send », « Send to Devin » ou équivalent. Le modèle GUIDE explique une étape, le participant localise le contrôle et annonce son choix.

Critères observables : le participant distingue exploration/planification et exécution, choisit le dépôt public attendu, formule tâche/périmètre/acceptation et sait expliquer ce qui se passerait à l'envoi. Le fait qu'Ask ne modifie pas directement le code n'autorise pas à présumer qu'une nouvelle demande serait sans consommation. La carte ne déclenche donc aucune nouvelle requête Devin. [Ask et Agent](https://docs.devin.ai/get-started/first-run).

Variante B comparable : préparer l'analyse d'un test qui échoue avant de demander sa correction. Garder même nombre d'informations à retrouver ; éviter de répéter exactement le même problème dans la condition aidée.

### D02 — Comprendre pourquoi un environnement ne sait pas lancer les tests

> Dans cette configuration de démonstration, le test n'est pas disponible. Aide-moi à retrouver où déclarer outils, dépendances et commande de test, puis explique ce qui est exécuté et ce qui est simplement donné au modèle. Ne sauvegarde rien.

Fixture : blueprint préparé dont un champ manque volontairement, avec oracle opérateur et copie expurgée. Le participant lit les sections et prépare une correction dans un brouillon local. **Ne pas cliquer Save ou Build** : la documentation indique qu'une sauvegarde de blueprint déclenche un build. Ne pas approuver une proposition d'environnement. [Blueprints](https://docs.devin.ai/onboard-devin/environment/blueprints).

Critères : distinguer `initialize` (outils/runtimes), `maintenance` (dépendances exécutées au build et présentées au démarrage, pas auto-exécutées au démarrage) et `knowledge` (référence chargée dans le contexte, non exécutée). Dire quel changement manque et ce qu'il faudrait vérifier après une future construction autorisée. Variante B : dépendance absente au lieu d'une commande de test non documentée.

### D03 — Comprendre un ancien échec au lieu de relancer à l'aveugle

> Cette session de démonstration est terminée mais n'a pas donné le résultat attendu. Montre-moi où retrouver les indices du blocage et aide-moi à préparer une prochaine demande plus claire, sans relancer l'agent.

Fixture : une ancienne session sur dépôt public avec une analyse Insights **déjà produite**, sans données privées. Le participant ouvre le menu de session puis Session insights, localise un problème dans la timeline et retrouve la recommandation associée. Ne pas cliquer « Investigate with Devin », qui ouvre une nouvelle session. Ne pas générer/régénérer une analyse pendant ce pilote de lecture seule. [Session Insights](https://docs.devin.ai/product-guides/session-insights).

Critères : citer une preuve de l'erreur, distinguer cause démontrée et hypothèse, expliquer une amélioration de consigne ou d'environnement, puis proposer le prochain contrôle sans l'exécuter. Variante B : deux anciennes sessions avec des causes différentes mais une difficulté comparable.

Si l'accès au compte ou à ces fixtures manque, faire la même recherche sur la documentation officielle. Étiqueter alors `docs_coaching`, pas `devin_account_workflow`. Ne pas créer de compte, octroyer accès GitHub ou démarrer un calcul pour contourner ce manque pendant l'entretien.

## Déroulement : petit pilote exploratoire

Viser d'abord trois à cinq volontaires et des essais de dix à quinze minutes ; ce nombre valide la faisabilité, pas un effet statistique. Noter familiarité avec le logiciel, rôle et expérience préalable avec des agents, sans chercher à collecter leur identité complète.

1. Présenter consentements et stop ; vérifier qu'ils fonctionnent.
2. Donner une variante d'une carte, avec un plafond de trois minutes sans aide. L'observateur n'indique pas le chemin.
3. Donner une variante comparable avec GUIDE, même plafond et mêmes conditions. Alterner l'ordre aidé/non aidé entre participants pour réduire l'effet d'apprentissage.
4. Proposer un petit transfert sans assistance : retrouver un contrôle analogue ou expliquer la prochaine vérification. Conserver l'ordre et le changement de variante dans la trace.
5. Recueillir retour oral ou texte, puis succès perçu et utilité. Le feedback est attaché au `run_id` du bon essai, pas au dernier écran affiché par hasard.

Ne pas obliger chaque volontaire à finir les trois cartes. Mieux vaut une paire complète et un retour exploitable que trois parcours interrompus. Un entraînement au site entre les conditions, une aide d'un teammate ou un bug d'affichage se note comme événement ; le temps ne doit pas être présenté comme strictement comparable sans cette réserve.

## Mesures et labels

| Champ | Source et interprétation |
| --- | --- |
| `task_success_observed` | Critères visibles et références des captures/étapes ; `pass`, `fail` ou `inconclusive`. Un « oui » de l'agent n'est pas une preuve. |
| `task_success_user` | Ce que le participant pense avoir réussi ; conserver les désaccords avec le vérificateur. |
| `usefulness_user` | Utile / neutre / gênant, avec raison libre. Aucun juge automatique ne remplit ce label à la place du volontaire. |
| `guide_clarity_user` | L'utilisateur savait-il où cliquer et pourquoi ? Noter les étapes ambiguës ou trop nombreuses. |
| `time_to_complete_ms` | Début/fin définis, interruptions consignées, même plafond pour les conditions comparées. |
| `corrections`, `help_requests`, `takeovers` | Corrections de l'assistant, appels à l'observateur, et toute reprise de contrôle automatique. |
| `transfer_success` | Petite tâche sans aide après le guidage ; ne pas assimiler une exécution assistée à un apprentissage durable. |
| `label_source`, `condition`, `fixture_id`, `commit` | Provenance humaine/automatique, ACT/GUIDE/docs_coaching, variante et version exacte. |

Conserver séparément transcription, audio brut et labels. L'audio brut n'est requis ni pour établir un label ni pour entraîner sur des trajectoires d'action. Ne pas remplir le dataset avec des captures de comptes personnels pour obtenir artificiellement cent traces. Distinguer jeux de développement et d'évaluation par familles/fixtures ; les variantes d'un même scénario ne doivent pas fuiter entre entraînement et test.

## Tour de contrôle et présentation au jury

Un ticket représente un essai réel identifié, avec sa condition, son origine et son statut. L'affichage live peut montrer question, dernière capture autorisée, événement, pause/stop et résultat. Les captures absentes, filtrées ou anciennes doivent être signalées ; un replay doit porter la mention replay. L'accès au tableau de bord ne doit pas donner accès aux secrets ou à toutes les sessions du compte par défaut.

Après des essais réellement réalisés, on peut dire : « N volontaires ont testé telle version, X tâches ont été vérifiées et Y retours jugent l'aide utile », avec les dénominateurs et limites. Avant cela : « protocole prêt et collecte instrumentée ». Les cas cloud documentaires démontrent de la navigation et du diagnostic ; les essais humains démontrent éventuellement une aide utilisable. Aucun des deux ne prouve encore une réduction du coût support, une adoption en entreprise ou un gain de fine-tuning.

Ordre de travail conseillé : finir une paire Odoo vérifiable ; exécuter les cas H publics dans les sandboxes ; préparer les sessions H authentifiées si l'accès fonctionne ; valider un parcours GUIDE réel ; seulement ensuite ouvrir le pilote volontaire Devin. Cela donne au jury deux démonstrations cohérentes et des preuves dont l'origine est lisible.

# H Platform coach V2 — script de démonstration à cinq scènes

Préparation : 8 novembre 2026. Les consignes ciblent le script d’Édouard. **Leur présence dans le prompt n’est pas une validation de bout en bout.** La répétition doit confirmer les champs réellement accessibles, la parole, les repères, la progression et les résultats enregistrés. Les exemples de réponse illustrent le ton; l’agent doit répondre à l’écran réel.

Pour la vidéo de deux minutes, privilégier **tour → cloud → création de Skill**, avec les plans en courte conclusion. La clé API est une prise séparée si l’expiration voulue existe dans l’interface. Les cinq demandes restent disponibles pour la répétition.

## 1. Welcome tour

**Départ :** une page H Platform dont la sidebar montre Agents, Sessions et Skills. Mode **Show me**.

> Hey Companion, I’m new here. Give me a quick tour.

**Attendu :** une phrase sur H, puis trois repères maximum, successivement sur Agents, Sessions et Skills. Chaque repère a une courte phrase prononcée. Le texte reste au centre; seul le contrôle entouré change. Le tour se termine sans récapitulatif. Aucun clic n’est nécessaire pour avancer.

Le modèle prépare cette séquence dans un seul appel `tour`; le runtime la joue sans navigation. Si seuls deux contrôles sont visibles, deux points suffisent. Interrompre pendant le deuxième point doit arrêter la voix et les points restants.

## 2. Une clé API temporaire

**Départ :** H Platform connecté, nom `h-hackathon` disponible. Mode **Do it, I watch**, ou Show me si l’utilisateur veut cliquer lui-même.

> Create an API key named h-hackathon that expires in 24 hours.

**Attendu :** ouvrir API keys, inspecter le formulaire, remplir le nom, identifier l’option d’expiration réelle. **L’existence d’une expiration de 24 heures n’est pas encore confirmée.** Si elle n’existe pas, le compagnon le dit et s’arrête avant création; il ne remplace pas ce choix par « jamais ».

En mode autonome, la création finale attend une confirmation explicite dans le compagnon. L’agent ne lit, ne prononce, ne copie ni ne journalise la valeur secrète. Il vérifie uniquement le nom, l’expiration ou le message de création non secret.

**Captation :** la valeur peut apparaître dans l’interface H après confirmation. La supprimer du contexte modèle ne la masque pas dans l’enregistrement vidéo; cadrer ou masquer cette partie avant diffusion. Ne jamais filmer la valeur en clair.

**Réussite :** métadonnées constatées, expiration demandée respectée, secret absent de la voix et des traces. Une phrase annonçant la création ne remplace pas cette vérification.

## 3. Montrer l’exécution cloud

**Départ :** H Platform; idéalement agent de démo sélectionné ou page Environments. Mode **Show me**.

> How can I run an agent without taking over my computer? Show me where to configure that.

**Attendu :** expliquer en une phrase que le navigateur cloud s’exécute chez H et laisse le Mac disponible, puis montrer Environments ou le bon réglage de l’agent. L’utilisateur suit les repères; chaque interaction est suivie d’une nouvelle lecture de l’écran.

**Réussite :** le choix cloud pertinent est visible. Aucune session n’est lancée, aucune configuration n’est sauvegardée pour une simple demande « où/comment ». Si la configuration ne peut pas être identifiée, la documentation officielle peut être ouverte dans un nouvel onglet en mode autonome, puis le passage pertinent montré.

## 4. Créer la Skill de coaching

**Départ :** Skills, nom `guided-onboarding` disponible. Mode **Do it, I watch**.

> Create a skill called guided-onboarding. It should coach users one step at a time, wait for them to act, and never perform the task for them.

**Attendu :** ouvrir le formulaire, remplir le nom, une description déclencheuse et un corps Markdown court. L’agent explique les étapes, sans lire le texte du corps. Il sauvegarde une seule fois puis constate la Skill enregistrée. Si le nom existe déjà, il ne l’écrase pas silencieusement.

Le contenu couvre : une consigne à la fois, contrôle visible identifié, l’utilisateur agit, attente puis vérification de l’écran, une alternative en cas de difficulté, fin sans récapitulatif. L’agent n’attache pas cette Skill à un autre agent sans demande.

**Réussite :** nom, description et corps conservés à la réouverture. Une Skill étant chargée à la demande, le comportement permanent « ne jamais agir » doit aussi être fixé dans les instructions et la politique d’action de l’agent cible. Cette création ne prouve pas que ces réglages sont déjà appliqués.

## 5. Comprendre la concurrence et les plans

**Départ :** H Platform. Mode **Show me** pour guider; Do it pour ouvrir la documentation des plans dans un nouvel onglet.

> How many agent sessions can my current plan run at once? Show me where to check.

**Attendu :** distinguer limite totale, sessions actives et places disponibles. Ne donner la limite du compte navigateur que si elle est effectivement constatée. Le quota API éventuellement fourni au modèle appartient au compte connecté à Companion; sans correspondance d’identité vérifiée, le présenter comme tel, sans l’assimiler au compte ouvert dans Chrome.

Montrer la page Plans/Current plan/billing en lecture seule, ou la documentation officielle. Les nombres publics Free/Builder/Startup sont une référence générale; ils ne prouvent pas le plan de cet utilisateur. Aucun clic Upgrade, achat ou changement de moyen de paiement.

**Réussite :** réponse sourcée par une donnée présente, bonne distinction total/disponible, destination montrée, aucun chiffre de compte inventé.

## Critères communs avant de filmer

- Une seule courte intervention à la fois : maximum 32 mots et 220 caractères pour chaque phrase affichée/prononcée. Le corps d’une Skill est un contenu de formulaire, pas une narration.
- Texte central stable, contrôle réellement visible entouré, parole expliquant ce contrôle. Aucune étiquette générique « on-screen control ».
- Un clic déclenche une observation; il ne vaut pas confirmation de réussite. Après navigation, ne pas redemander un clic déjà effectué.
- Une nouvelle dictée ou Stop interrompt la tâche et la voix; aucune réponse ancienne ne doit réapparaître.
- Répéter chaque scène retenue deux fois. Garder demande transcrite, état initial, résultat observé et feedback humain; ne pas marquer réussi uniquement parce que le modèle a dit « done ».

Réserve déjà préparée : “This session says Interrupted. Did it still produce an answer? Show me where to check.” Utiliser une session dont la réponse existe; distinguer statut et contenu constaté.

Sources officielles : [Agents](https://hub.hcompany.ai/agents-api/agents/overview), [Skills](https://hub.hcompany.ai/agents-api/skills/overview), [Cloud browser](https://hub.hcompany.ai/agents-api/browser/configuration), [Plans et limites](https://hub.hcompany.ai/agents-api/plans-and-limits), [Sessions](https://hub.hcompany.ai/agents-api/sessions/overview). L’expiration des clés reste à constater dans le formulaire.

## Lancer cette version et revenir à l'ancienne

Cette branche contient un lanceur séparé : `scripts/run-h-platform-coach-v2.py`. Il utilise le code de ce worktree, le port **8792** et un profil Electron distinct. Il **ne ferme pas l'ancien moteur** : terminer son essai et l'arrêter avant un test vocal V2 pour éviter deux auditeurs sur la même touche.

Depuis la racine de ce worktree :

```bash
python3 scripts/run-h-platform-coach-v2.py
```

Maintenir **Option droite** pour dicter. Dans la barre de menus, **Start H Platform coach V2** relance le même moteur V2; **Stop task** interrompt seulement sa tâche.

La dictée accepte français et anglais par défaut (`HCS_VOICE_LANGUAGE=fr-en`); les consignes demandent une narration anglaise. Le mode reste celui du slider : demander « create for me » en **Show me** ne déclenche pas d'exécution autonome. Passer à **Do it, I watch** avant les scènes de création, puis dicter la demande.

Pour démarrer uniquement le moteur :

```bash
python3 scripts/run-h-platform-coach-v2.py --backend-only
```

Le lanceur réutilise par défaut Python dans `/private/tmp/hcompanion-matteo-pilot-venv/bin/python` et Electron déjà installé dans le checkout voisin `../h-companion`. Les options d'environnement `HCS_PYTHON`, `HCS_ELECTRON` et `HCS_V2_ENV_SOURCE` permettent de changer ces chemins. Aucun téléchargement n'est effectué.

Les clés sont lues depuis `app/.env` et `agent/.env` de ce checkout voisin, puis les configurations vocales privées `human-cognition/speech.env` et `human-h-company/speech.env`. La configuration H prend priorité sur celle de Cognition; les variables explicitement définies dans le shell gardent priorité. Les clés ne sont ni affichées ni transmises au renderer Electron.

Logs, métadonnées de PID, profil desktop et traces restent dans `~/Library/Application Support/HCompanionResearch/h-platform-coach-v2/`, hors dépôt. Les traces sont dans `episodes/`, le journal moteur dans `runtime-*.log`, celui de la fenêtre dans `desktop.log`. Le lanceur refuse un port occupé par un moteur différent et vérifie l'identité `coach-v2` avant de réutiliser un processus.

Pour revenir à l'ancienne version, quitter **la fenêtre/tray V2**, puis arrêter uniquement son moteur identifié :

```bash
python3 scripts/run-h-platform-coach-v2.py --stop-owned-runtime
python3 ../h-companion/scripts/start-devin-companion.py
```

L'arrêt vérifie le moteur, le port, le PID et le worktree enregistrés. Il ne fait aucun arrêt global et conserve les traces. L'ancien lanceur reprend son propre profil configuré. Aucun changement de branche, reset Git ou suppression de données n'est nécessaire.

## Portée et état de validation

La V2 utilise Holo4, un briefing H ciblé, l’observation AX actuelle et un court historique. La voix, les repères et l’accessibilité macOS sont réutilisés; l’ancien moteur de procédures et sa narration de rapports ne sont pas chargés.

Les instructions couvrent désormais les cinq scènes. La séquence de tour est une présentation de trois contrôles maximum, sans trois navigations. Les créations de Skill et de clé sont des parcours distincts; les achats, suppressions, révocations, secrets et lancements de jobs restent hors de cette démonstration.

La position intermédiaire du slider reste guidée. Changer de mode arrête la demande en cours; reformuler ensuite. La nouvelle dictée interrompt immédiatement la demande précédente.

Les traces V2 et les labels explicites de « Mon retour » restent dans le dossier privé V2. Leur remontée à la tour de contrôle n’est pas encore branchée. Aucun succès humain ni consentement d’entraînement n’est déduit du modèle.

Avant cette extension, 126 tests Python ciblés passaient et les quatre réponses humaines rejetées à tort ont passé le rejeu de parsing/cibles. Ces résultats ne valident pas les nouveaux parcours à cinq scènes. Consigner séparément les nouveaux tests et les répétitions réelles dans `docs/test-log.md`.

# H Platform coach V2 — six questions pour la démo

Préparation : 8 novembre 2026. Les concepts ont été contrôlés dans la documentation officielle H. **Ces six essais ne sont pas encore validés de bout en bout avec le nouveau coach.** Une question connue ne doit pas déclencher une réponse préenregistrée : l'agent doit tenir compte de l'écran réel.

Pour filmer, commencer par **Skills** puis **la réponse d'une session interrompue**. Le premier montre l'onboarding, le second une aide concrète à comprendre un résultat trompeur. Le passage à la documentation dans un nouvel onglet est le meilleur complément en mode autonome.

## 1. Comprendre Skills et trouver le bon bouton

**Départ :** H Platform, page Skills, bouton de création visible. Mode **Show me**.

> What are Skills for, and where would I create one?

Réponse courte attendue, adaptée au libellé réellement visible : “Skills give your agent reusable instructions for specific tasks. You can create one with this button.”

**Action :** entourer le bouton de création. Pas de création ni de sauvegarde demandée.

**Réussite :** définition juste, repère sur le bon bouton, une ou deux phrases audibles, texte central lisible. Échec si l'agent énumère le catalogue, récite la documentation, ou invente un bouton.

## 2. Vérifier une réponse malgré le statut Interrupted

**Départ :** une session de démonstration autorisée, avec statut Interrupted et une réponse existante vérifiée manuellement. Mode **Show me**. Ne pas utiliser un essai sans réponse pour cette prise.

> This session says Interrupted. Did it still produce an answer? Show me where to check.

Si la réponse est visible : “Yes, this session has an answer. You can read it here.” Si elle n'est pas encore visible, guider vers le panneau de réponse puis observer avant de conclure.

**Action :** entourer le panneau ou le contrôle qui révèle la réponse. Après ouverture, ne pas répéter le clic.

**Réussite :** conclusion appuyée sur un contenu visible, statut distingué du résultat. Échec si « Interrupted » suffit à conclure à un échec, si l'agent annonce une réussite métier sans preuve, ou s'arrête à “still needs verification”.

## 3. Comprendre Agents et Sessions

**Départ :** page d'accueil ou liste Agents, avec Agents et Sessions visibles dans la navigation. Mode **Show me**.

> What's the difference between Agents and Sessions? Show me where to review a previous run.

Exemple de réponse : “Agents define how your assistant works. Sessions are its individual runs; open Sessions to review an earlier result.”

**Action :** entourer Sessions. L'utilisateur clique. Le coach constate la liste et s'arrête, sans ouvrir une session privée au hasard.

**Réussite :** distinction claire, bon repère, clic reconnu, aucune boucle ni lecture de toutes les sessions.

## 4. Choisir le cloud pour libérer le Mac

**Départ :** configuration d'un agent de démonstration, environnement visible. Aucune modification ne sera sauvegardée. Mode **Show me**.

> I want to run browser tasks without taking over my Mac. Show me where to choose a cloud browser, without saving anything.

Exemple de réponse : “A cloud browser runs on H's infrastructure, leaving your Mac free. Here's the environment setting to check.” Le second énoncé n'est acceptable que si le bon réglage est réellement visible.

**Action :** guider un contrôle à la fois vers le choix d'environnement; inspecter le champ exact. Si l'interface ne permet pas de l'identifier, proposer la page officielle pertinente au lieu d'inventer.

**Réussite :** bonne configuration localisée, aucune sauvegarde et aucune session lancée. **Plus dépendant de l'interface actuelle** : garder en réserve si le parcours n'est pas encore répété.

## 5. Expliquer le login d'un navigateur distant

**Départ :** page Browser Profiles, sans exposer de secrets. Mode **Show me**.

> I'm signed in here. Why is my agent's cloud browser signed out, and where can I reuse its login?

Exemple de réponse : “Your cloud browser has a separate login from this dashboard. Browser Profiles let you reuse its saved sign-in state.”

**Action :** repérer Browser Profiles ou le contrôle pertinent déjà visible. Pas d'export, d'import, de formulaire de mot de passe ni de manipulation de cookies pendant ce test.

**Réussite :** explique la séparation des deux navigateurs sans prétendre qu'un profil particulier fonctionne déjà. S'arrête après l'explication et le repère utile.

## 6. Ouvrir la bonne documentation à côté du travail

**Départ :** une page H Platform, noter son onglet et son URL. Mode **Do it, I watch** pour la prise autonome.

> Open the browser profiles documentation in a new tab and show me how saved logins are reused. Keep this page open.

Exemple de réponse : “I'll open the guide beside your work.” Puis, après observation du passage pertinent : “This section explains how the cloud browser keeps its sign-in state between sessions.”

**Action :** ouvrir `https://hub.hcompany.ai/agents-api/browser/profiles` dans un nouvel onglet, atteindre la section pertinente, y laisser la page. Réutiliser l'onglet de documentation si déjà ouvert.

**Réussite :** onglet Platform préservé, bon document, passage effectivement visible, voix brève. Échec si l'agent remplace le travail, ouvre plusieurs onglets inutiles, lit un bloc de code ou annonce avoir montré une section sans l'avoir observée.

## Petite vérification avant de filmer

1. Faire chaque essai choisi deux fois avec le même écran de départ. Les exemples de réponse ci-dessus illustrent la longueur souhaitée, pas une phrase exacte obligatoire.
2. Mesurer « fin de dictée → première consigne utile » et vérifier la voix, le repère et le clic séparément. Enregistrer les valeurs observées; ne pas annoncer un gain de latence sans comparaison.
3. Garder pour chaque prise : question transcrite, écran initial, mode, trace, résultat observé et feedback humain réussite/utilité. Un label automatique ne remplace pas ce feedback.
4. Refaire une demande au milieu d'une explication : l'ancienne parole et la tâche doivent s'interrompre. Une demande de petit tour doit rester sur H, en quelques phrases, même si un mot transcrit est hors sujet.

**Contrôlé dans les sources :** sens des Skills, différence Agent/Session, états de session, cloud/browser local, persistance des profils. **À contrôler en live :** libellés exacts, position des repères, progression après clic, navigation en nouvel onglet, parole et comportement du slider.

Sources officielles consultées le 2026-11-08 : [Skills](https://hub.hcompany.ai/agents-api/skills/overview), [Agents](https://hub.hcompany.ai/agents-api/agents/overview), [Sessions](https://hub.hcompany.ai/agents-api/sessions/overview), [Browser configuration](https://hub.hcompany.ai/agents-api/browser/configuration), [Browser profiles](https://hub.hcompany.ai/agents-api/browser/profiles).

## Lancer cette version et revenir à l'ancienne

Cette branche contient un lanceur séparé : `scripts/run-h-platform-coach-v2.py`. Il utilise le code de ce worktree, le port **8792** et un profil Electron distinct. Il **ne ferme pas l'ancien moteur** : terminer son essai et l'arrêter avant un test vocal V2 pour éviter deux auditeurs sur la même touche.

Depuis la racine de ce worktree :

```bash
python3 scripts/run-h-platform-coach-v2.py
```

Maintenir **Option droite** pour dicter. Dans la barre de menus, **Start H Platform coach V2** relance le même moteur V2; **Stop task** interrompt seulement sa tâche. Pour démarrer uniquement le moteur :

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

## État de cette V2

La V2 réutilise la voix, les repères et l'accessibilité macOS, mais ne charge pas l'ancien moteur de procédures, le RAG, le vérificateur ni la narration de rapports. Un appel à Holo4 décide d'une seule étape, avec le briefing H, l'observation AX courante et quatre interactions précédentes au maximum. Aucun historique de screenshots n'est envoyé.

La référence embarquée couvre les concepts et parcours ci-dessus avec leurs sources; ce n'est pas l'intégralité de la documentation H. Cette première version explique et navigue. Elle ne lance pas de jobs, n'achète rien et ne manipule pas de secrets. Les contrôles sans libellé accessible ne sont pas exploitables dans ce chemin AX seul.

- Show me : vous cliquez; un clic ciblé provoque une nouvelle lecture, sans être considéré comme une preuve de réussite.
- Position intermédiaire : reste Show me dans cette V2. Pas de prise de contrôle implicite.
- Do it, I watch : une action de navigation, puis une nouvelle observation. Changer le mode arrête la demande actuelle; reformulez ensuite.
- Toute nouvelle dictée interrompt la tâche et la voix. Les résultats tardifs d'une ancienne demande sont écartés.
- Chaque intervention parlée/écrite est limitée à 32 mots et 220 caractères. Le prompt préfère une ou deux phrases; une troisième phrase courte n’est pas rejetée uniquement à cause de sa ponctuation. Pas de tableau, code ou rapport final récité.
- Les traces V2 et les labels saisis dans « Mon retour » restent dans le dossier privé V2. Ils ne sont pas encore publiés dans la tour de contrôle. Aucun succès humain ni consentement d'entraînement n'est déduit d'une réponse du modèle.

Validation initiale : 91 tests Python et 23 tests desktop réussis. Sept questions sur observations synthétiques envoyées réellement à Holo4 ont respecté le protocole; latence API 6,0–10,7 s avec trois appels concurrents. Ce n'est pas un benchmark vocal de bout en bout. La suite de la session interrompue répond sans répéter son clic.

Limites constatées : demander l'ouverture de documentation en Show me sans lien visible peut produire une réponse non conforme, rejetée avant action. Utiliser Do it pour l'essai 6. Le suivi de l'essai 3 peut proposer une session de la liste plutôt que s'arrêter à la liste; la formulation et l'écran doivent être revus avant filmage. Les essais humains restent à réaliser dans le nouveau runtime.

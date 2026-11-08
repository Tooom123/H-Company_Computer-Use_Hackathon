# Démo H Platform — sauvetage et validation, 8 novembre 2026

Branche isolée : `edouard/h-platform-demo-rescue`. Point de retour : `70d3187`
(passation, code V2 antérieur `f63770c`). Les correctifs Finder développés en parallèle
sur le même checkout (`65e35f1`) sont préservés.
Objectif : deux minutes de fonctionnement réel avec Holo4, voix anglaise et repères visibles.
Les critères détaillés restent ceux de la [passation](handoff-rescue-hcompany-kosmo-2026-11-08.md).

## Décision : réparer V2

| | V2 | Kosmo |
|---|---|---|
| Coach | Holo4 déjà intégré | GPT-6 Sol ; Holo4 sert à localiser visuellement |
| Actions | Clic, saisie, navigation, confirmation avant création de clé | Pointeur et instruction ; l'humain exécute chaque action |
| H Platform | Corpus et tour existants | Notes publiques, parcours authentifiés restant à valider |
| Effort immédiat | Corriger contrat/parsing, observation des formulaires et interruptions | Ajouter coach Holo, contrat d'actions, exécuteur, boucle et confirmations |

**V2 est la reprise la plus courte.** Kosmo reste utile pour son DOM, son overlay et sa voix,
mais sa reprise élargirait la mission. Vérification distante en lecture seule :
`personal` → `https://github.com/edouardfoussier/kosmo`, `HEAD/main` =
`d3344d8ff48f38c568ba1e5e5b7edf799f9c4006` (5 octobre 2026).
L'objet existait localement ; aucun checkout ni changement du dépôt Kosmo.
Entre la copie `da53111` et ce commit, aucun changement de `coach.ts`, `holo.ts`,
`coach/service.ts` ou `extension/background.js` n'ajoute l'autonomie.
Les anciennes mesures Kosmo sur Gradium ne prouvent pas la latence d'un coach Holo4.

## Lancement

Un seul contrôleur du Mac. Chrome connecté sur `https://platform.hcompany.ai/`, sidebar visible.
Dans Companion, sélectionner **Do it, I watch** ; **Show me** laisse les clics à l'utilisateur.
Prononcer « show me » dans la question ne change pas le mode sélectionné.

```sh
cd /Users/edouardfoussier/code/computer-use-hack/computer-use-hack-cdx/h-companion-clean
python3 scripts/run-h-platform-coach-v2.py --stop-owned-runtime
# Attendre la sortie du moteur (la commande Stop peut revenir avant sa fermeture).
python3 scripts/run-h-platform-coach-v2.py
```

Maintenir **Option droite**, parler puis relâcher. Stop ou une nouvelle dictée doivent couper
la voix et empêcher les actions suivantes. Les clés sont chargées depuis les fichiers privés du
lanceur ; ne pas les afficher, déplacer dans le dépôt ou inclure dans les traces publiées.

Pour répéter uniquement la navigation avec une entrée texte locale :

```sh
python3 scripts/run-h-platform-coach-v2.py --stop-owned-runtime
python3 scripts/run-h-platform-coach-v2.py --read-only-rehearsal
```

Ce mode bloque la saisie et les contrôles hors navigation dans l'exécuteur. Il active
`POST /rehearse` avec `{"question":"…"}` et l'en-tête `X-HCS-App: 1`, sur
`http://127.0.0.1:8792`. **Il ne valide ni microphone, ni dictée, ni création de Skill/clé.**
Redémarrer sans cette option pour une prise normale ; relancer seul un moteur déjà présent
ne change pas sa configuration. `GET /status` lit l'état ; `POST /stop` arrête la tâche.

## Preuves et statut des scènes

Une scène n'est retenue qu'après **deux exécutions complètes** avec postconditions observées.
Pour chaque prise : identifiant d'épisode, entrée réelle ou répétition texte/WAV, cache utilisé
ou appel Holo réel, durée totale, délai relâchement → premier playback logiciel, actions et
postconditions, correction manuelle éventuelle. Un démarrage audio logiciel n'est pas une mesure
acoustique au haut-parleur. Garder le feedback humain séparé des conclusions du modèle et des tests.

Traces privées : `~/Library/Application Support/HCompanionResearch/h-platform-coach-v2/episodes/`.
Ne pas committer les traces brutes, secrets ou captures de compte. Les résultats synthétiques
sont à reporter aussi dans `docs/test-log.md` par le responsable des essais.

| Scène et phrase exacte | Postcondition attendue | Prise 1 | Prise 2 / décision |
|---|---|---|---|
| **Accueil** — “Hey Companion, I'm new here. Give me a quick tour.” | Une phrase d'accueil, puis Agents → Sessions → Skills ouverts et expliqués ; aucun récapitulatif | `coach_v2_da0930ebcca143df9deca783c318ad89` : PTT réelle, trois destinations vérifiées, `completed`, 25,763 s ; Holo 7 090 ms, AX 140 ms, relâchement → playback 8 094 ms | `coach_v2_28d1f4d76c4d4672b90e4e49a4f7b72f` : deuxième PTT réelle (“show me around”), trois destinations vérifiées, 17,018 s ; cache Holo réutilisé, relâchement → playback 1 318 ms. Une prise texte intermédiaire a été interrompue après 4,276 s. **Navigation répétée deux fois ; feedback humain séparé** |
| **Clé** — “Create an API key named h-hackathon-demo that expires in 24 hours.” | Préparer le formulaire, vérifier nom/expiration ; confirmation humaine juste avant création ; aucun secret lu/filmé | Script exact non répété. Les essais vocaux `coach_v2_30db1ef6dc734c56a5aee47ff9684540` et `coach_v2_ffd66cbe41294d71b535e66e1928a074` demandaient une clé sans expiration ; bloqués en mode lecture seule, aucune création | **Création exacte 24 h non démontrée** ; UI inspectée avec calendrier par date, sans heure ni choix 24 h ; ne pas substituer No expiry |
| **Cloud** — “How can I run an agent without taking over my computer? Show me.” | Ouvrir Environments/réglage pertinent ; expliquer le navigateur cloud ; documentation officielle dans un nouvel onglet si utile ; aucune session payante lancée | `coach_v2_c6b99195baf843389d2d0f82601a64be` : vraie réponse Holo sur écran réel, entrée texte ; ouverture bloquée par reconnaissance du menu Chrome ; Holo 4 477 ms, texte → playback 5 282 ms | Libellé réel « New tab » et recherche de menu corrigés ; **revalidation live à faire** |
| **Skill** — “Create a skill called guided-onboarding. It should coach users one step at a time, wait for them to act, and never perform the task for them.” | Nom, description et Markdown court remplis ; un seul enregistrement et confirmation observée ; aucun écrasement | À compléter par essai complet | À compléter |
| **Concurrence** — “How many agent sessions can my current plan run at once? Show me where to check.” | Billing & Subscription / plan visible ; chiffre fondé sur ce compte ou limite déclarée non visible ; distinguer total/actives/libres ; aucun Upgrade | Inspection UI réelle : Free Active / Current plan / 3 concurrent sessions. Ce n'est pas une exécution Holo | Tentative de répétition non lancée, moteur en cours de remplacement ; **parcours Holo non validé** |

Pour le tour `coach_v2_da0930…`, **entrée PTT réelle observée** dans le journal (`voice` et événement
de relâchement), sans audio injecté ; **feedback humain non recueilli**. Identifiants complets à
compléter depuis les traces. Trois tentatives texte antérieures ont échoué avec `not_foreground`
et ne comptent pas comme répétitions réussies. Le statut `completed` seul ne constitue pas une
validation humaine. Ne pas transformer ces valeurs en médiane ou en promesse de performance.

Pour la clé, choisir le lendemain dans un calendrier **ne prouve pas une expiration à exactement
24 heures** : ni l'heure ni la sémantique d'expiration ne sont établies. La séquence peut montrer
cette limite et s'arrêter ; elle ne peut pas être présentée comme une création réussie. Un nom
disponible doit être choisi pour toute nouvelle création autorisée. Pour la Skill, les consignes
« wait » et « never perform » constituent son contenu, pas un changement du mode de Companion.

## Montage provisoire de deux minutes

Budget éditorial, **pas promesse de scènes déjà réussies** :

| Temps | Séquence candidate |
|---|---|
| 0:00–0:10 | Chrome et Companion visibles ; mode Do it ; question d'accueil dictée |
| 0:10–0:40 | Tour réel Agents → Sessions → Skills (deux parcours complets observés) |
| 0:40–1:00 | Cloud : navigation et explication, seulement après deux essais concluants |
| 1:00–1:35 | Skill : préparation puis confirmation d'enregistrement, seulement si réellement observée |
| 1:35–1:50 | Plan : preuve visible ou réponse honnête sur la limite non visible |
| 1:50–2:00 | Option : limite d'expiration de clé expliquée, ou démonstration vérifiée de Stop |

Retenir uniquement les meilleures prises validées ; une scène bloquée peut être retirée ou montrée
comme telle. Indiquer les préparations hors caméra, l'usage du cache et les attentes coupées au montage.
Ne pas assembler des étapes distinctes pour faire croire à une exécution continue réussie. Une phrase
courte, cible entourée et voix synchronisée ; aucun code, secret, « Result: Done » ou statut technique lu.

## Vérifications et blocages de cette intervention

- 460 tests ciblés ont passé en 4,12 s (contrat, boucle, navigation, formulaires, voix,
  interruptions, répétition et profil du lanceur), puis `git diff --check` propre.
- Outils Holo séparés par action, valeurs de formulaires non secrètes observées, refus d'une
  expiration 24 h non vérifiable avant confirmation et après rafraîchissement, synchro
  repère/voix et mesure au lancement du processus audio.
- L'ouverture documentaire utilise maintenant le menu natif et l'adresse AX au lieu d'une
  frappe d'URL dépendante du clavier. URL finale contrôlée avant la prochaine décision Holo.
- Lancement autonome général refusé par l'auto-review ; la variante en lecture seule a été
  acceptée. Confirmation spécifique des deux Skills demandée, non reçue à ce point.
- Une intervention parallèle a remplacé le moteur par le mode normal à 11:58 Paris
  (`runtime_profile` faux/faux). Les redémarrages de cette mission ont été suspendus pour
  ne pas perturber ce pilotage. Les correctifs de menu et de courses Stop sur disque restent à revalider après redémarrage coordonné.
- Aucun succès humain synthétique, aucune clé créée par cette intervention, aucune session
  payante lancée. Les essais interrompus/échoués restent dans les traces privées.

## À compléter avant de déclarer la démo filmable

- Commit final et vérifications exécutées.
- Deux résultats par scène encore non validée, état cache/appel Holo et source d'entrée.
- Résultats interruption par Stop/nouvelle dictée, synchronisation voix/repère et feedback humain.
- Script final limité aux prises réellement validées ; blocages conservés explicitement.

## Dernières observations pendant le pilotage utilisateur

- Deuxième tour vocal : `coach_v2_28d1f4d76c4d4672b90e4e49a4f7b72f`, 12:00 Paris,
  réponse issue du cache d'un tour Holo complet, pas de nouvel appel modèle. Les trois destinations
  sont de nouveau observées. 882 ms relâchement → texte, 436 ms texte → playback, soit 1 318 ms.
  Le cache dépend des prompts : une modification les invalide et nécessite un nouveau tour complet.
- Nouvelle demande vocale hors script (« no expiry »), `coach_v2_955d6ec6135c4cf2a5fbd414ed2e6559` :
  Holo ouvre API keys puis le formulaire, mais le hit-test bloque la saisie du nom. La trace contient
  « Unlock 1Password » ; popup ou cible périmée possibles, cause exacte non prouvée. Le hit-test
  reste actif, aucune clé créée. Préparer/fermer un popup avant une prise devra être déclaré.
- Deux courses Stop reproduites hors UI et corrigées : annulation revérifiée avant chaque effet,
  résultats/erreurs d'une génération annulée ignorés pour ne pas relancer la voix.

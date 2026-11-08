# Mission sauvetage — démo H Companion sur H Platform

**8 novembre 2026. Urgent.** Édouard veut enregistrer une vidéo de deux minutes. Le tour fonctionne désormais, mais les autres parcours restent trop fragiles et l'attente Holo est longue. Livrer une démo réelle, courte et répétable ; ne pas prendre les tests unitaires pour une validation utilisateur.

## Résultat attendu

Un compagnon Holo4 qui connaît H Platform, comprend la voix et **répond en anglais**. **Show me** = l'utilisateur clique ; **Do it, I watch** = le compagnon clique/remplit. Dire « show me » ne change pas le mode sélectionné.

Pour la prise : **Do it**, Chrome connecté sur `https://platform.hcompany.ai/`, sidebar visible. Une phrase courte au centre de l'écran, bouton visé entouré, voix synchronisée. Pas de code, « Result: Done », résumé répété, long monologue ni statut technique lu à voix haute. Nouvelle dictée ou Stop interrompt immédiatement voix et actions.

## Script exact et critères de réussite

| Scène | Question à dicter | Comportement attendu |
|---|---|---|
| 1 · Accueil | **Hey Companion, I'm new here. Give me a quick tour.** | Une phrase sur H, puis **Agents → Sessions → Skills** : ouvrir chaque page, entourer son bouton et l'expliquer en une phrase. Trois sections maximum, aucun récapitulatif final. |
| 2 · Clé | **Create an API key named h-hackathon-demo that expires in 24 hours.** | Ouvrir API keys et le formulaire, remplir le nom, choisir l'expiration réellement disponible. La préparation est autonome ; confirmation humaine uniquement avant création effective. Ne jamais substituer « no expiry » si 24 h est indisponible. Vérifier le nom/expiration, jamais lire ni filmer le secret. Choisir un nom libre avant une nouvelle prise. |
| 3 · Cloud | **How can I run an agent without taking over my computer? Show me.** | Naviguer vers Environments ou le réglage observé pertinent ; expliquer le navigateur cloud. Si nécessaire, ouvrir la documentation officielle **dans un nouvel onglet** et montrer le passage utile. Ne pas lancer de session payante. |
| 4 · Skill | **Create a skill called guided-onboarding. It should coach users one step at a time, wait for them to act, and never perform the task for them.** | Créer nom, description et corps Markdown court, enregistrer une fois, constater la confirmation. Ces règles sont le **contenu de la Skill**, pas une instruction pour que Companion cesse d'agir. Ne pas lire le corps à voix haute ni écraser une Skill existante. |
| 5 · Concurrence | **How many agent sessions can my current plan run at once? Show me where to check.** | Ouvrir Billing & Subscription / Plans / Current plan. Répondre depuis les preuves visibles du compte. Distinguer limite totale, sessions actives et places libres. Si la limite n'est pas visible, le dire ; ne pas inventer un chiffre ni cliquer Upgrade. |

Retenir les meilleures prises réelles pour les deux minutes ; signaler les séquences préparées/cachées, ne pas fabriquer de réussite.

## État H Companion à reprendre

- Dépôt : `https://github.com/Tooom123/H-Company_Computer-Use_Hackathon`.
- Worktree : `/Users/edouardfoussier/code/computer-use-hack/computer-use-hack-cdx/h-companion-clean`.
- Branche **`edouard/h-platform-coach-v2`**, code **`f63770c`**. Créer une branche de sauvetage, préserver ce point de retour. Lire `AGENTS.md` ; fusion sur main par PR et revue.
- `agent/src/hcs_agent/coach_v2_runtime.py` : boucle, actions, tour, interruptions ; `coach_v2.py` : appel Holo4 et contrat `coach_step` ; `coach_v2_screen.py` : lecture AX macOS de Matteo.
- Prompts : `agent/src/hcs_agent/data/hcompany-coach-v2-system.md` et `hcompany-coach-v2.md`. Voix/repères : `overlay.py`, `speech.py`, `voxtral.py`. V2 utilise l'AX **sans screenshot**.
- Tour validé par l'utilisateur : **0,46 s de lecture AX, 19,06 s d'appel Holo**. Cache privé 24 h ajouté, labels/phrases sans coordonnées ; délai vocal caché encore à mesurer.
- Clé : faux arrêt sur l'ouverture du formulaire corrigé ; confirmation finale conservée. Création complète non validée.
- **Derniers échecs cloud** : `open_docs` avec `target` rejeté (« This action must not carry a target »), puis `type` sans texte exploitable. Priorité au contrat/outils/parsing plutôt qu'à de nouvelles couches de prompt.
- Quota : confusion **10 autorisées / 8 libres** et compte API/navigateur. Aucun quota API injecté pour « my current plan » sans identité reliée.
- **Seul le tour est validé en live.** Les probes cloud/Skill/quota ne vérifient qu'une première décision fictive. Tests ciblés : environ 1,5 s ; privilégier les régressions utiles et la répétition réelle.

## Option Kosmo : ce qui existe vraiment

Dépôt demandé : `https://github.com/edouardfoussier/kosmo`.

Copie inspectée : `/Users/edouardfoussier/code/antasphere/kosmo-main-local`, branche `codex/compact-voice-bar`, commit `da53111`. **`personal`** pointe vers Kosmo ; **`origin`** vers `antasphere-hackathon/ai-hackathon-2026-cosmos`. Dernière version GitHub non vérifiée : vérifier les remotes avant fetch, préserver les changements locaux.

À réutiliser après inspection :

- `apps/extension/content.js` : DOM, IDs exacts, hit-test, version d'écran ; `background.js` : orchestration/audio/annulation.
- `apps/landing/kosmo-overlay` : source ; ne pas éditer sa copie générée dans l'extension.
- `apps/server/src/integrations/{coach.ts,coach-provider.ts,holo.ts}` : coach OpenAI, Holo4 en repli visuel ; adapter à **Holo4 comme coach**.
- `apps/server/src/coach/service.ts`, `src/api/coach.ts` : traces ; `src/api/voice*.ts`, `src/integrations/gradium.ts` : voix.

**Kosmo guide seulement : l'exécution autonome reste à ajouter.** Réutiliser DOM/overlay/voix, remplacer le corpus par H Platform. Démarrage : `docs/project/extension-local.md`, Node ≥22, pnpm 10.34.4, serveur 3002.

## Accès locaux et reprise rapide

Chrome est connecté à H. Holo, Mistral/Voxtral et ElevenLabs sont configurés ; réutiliser le chargement privé du lanceur, **sans afficher ni committer les clés**.

```sh
cd /Users/edouardfoussier/code/computer-use-hack/computer-use-hack-cdx/h-companion-clean
python3 scripts/run-h-platform-coach-v2.py
```

Contrôle local : `http://127.0.0.1:8792`, en-tête `X-HCS-App: 1`. **Option droite maintenue** pour parler. `/status` en lecture ; `POST /stop` arrête la tâche. `--stop-owned-runtime` arrête uniquement ce moteur avant relance. Ne pas faire tourner deux contrôleurs du Mac simultanément.

Traces/configuration : `~/Library/Application Support/HCompanionResearch/h-platform-coach-v2/` (`episodes/`, `stt.env`, `tour-cache.json`). Dernier échec cloud : `coach_v2_b1dd3aad67ea40f5ac63f2d933c6316d`. Autres fichiers d'environnement : voir le lanceur.

## Mission à exécuter maintenant

1. Choisir rapidement réparation V2 ou branche Kosmo, sans réécriture générale.
2. Valider **une scène complète**, puis les autres ; deux répétitions par prise retenue. Mesurer fin de dictée → voix, conserver traces et feedback humain séparés.
3. Livrer branche/commit, lancement, script final et blocages. Aucun nouveau chantier GPU, fine-tuning, Vision Lab ou portail.

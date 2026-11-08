# H-Company — séance utilisateur en guidage vocal

Préparé le 8 novembre 2026. Dix demandes à essayer dans l'app interactive :
elles ne sont pas dix tests validés. L'utilisateur peut improviser ; conserver
alors ses mots exacts et noter que la demande diffère de la carte.

## Préparer le premier passage

Ouvrir la [documentation H](https://hub.hcompany.ai/) et, pour les cartes de
compte, une session de démonstration choisie par l'opérateur. Noter son URL et
son identifiant dans le journal privé. Pour la comparaison, réserver deux sessions.
Ne pas parcourir les autres historiques. La connexion locale doit être vérifiée
sur le Mac : le profil authentifié d'une sandbox ne connecte pas Chrome local.

Demande commune à dire ou à intégrer au contexte de séance :

> Guide-moi une étape à la fois. Montre où cliquer, explique pourquoi, puis laisse-moi
> agir. Reste en lecture seule : ne crée, ne modifie, ne lance et ne supprime rien.
> Si une information n'est pas visible, dis-le ; distingue ce que tu observes de
> ce que tu supposes. Je veux pouvoir refaire le parcours ensuite.

Fixer l'autonomie à **0 — montrer seulement**, vérifier le micro, la capture écran,
l'overlay et l'arrêt. Les essais GUIDE avec une personne restent en série sur ce
Mac. Ne pas utiliser l'avance automatique de test, ni présenter une prise de
contrôle ACT comme un guidage réussi.

## Dix questions, dans l'ordre conseillé

Les trois premières forment une courte séance. Le repère opérateur sert à préparer
et évaluer le passage ; ne pas dicter de résultat attendu à la place de la question.

| Carte / origine | Demande à dicter | Départ et repère à montrer |
| --- | --- | --- |
| HG01 / HC01 | « Je veux que mes tests tournent sans bloquer mon Mac. Montre-moi dans la doc où choisir un navigateur cloud et quels champs regarder pour savoir où mon site va s'ouvrir. Ne lance rien. » | Docs : [configuration navigateur](https://hub.hcompany.ai/agents-api/browser/configuration). Faire retrouver la section et le bloc de configuration, puis expliquer le choix avec les libellés visibles. |
| HG02 / HC07 | « Je suis sur notre essai de démonstration. Je ne sais pas où lire sa réponse. Montre-moi la réponse, puis la dernière étape qui permet de comprendre ce qu'il a fait. » | Session de démonstration ouverte. L'utilisateur retrouve lui-même réponse et repère d'étape ; leur présence ne valide pas le contenu métier. |
| HG03 / HC03 | « Mes tests me redemandent de me connecter. Montre-moi où la doc explique la différence entre un profil de navigateur et un coffre, puis où vérifier si le profil est conservé. N'ouvre aucun coffre. » | Docs : [profils](https://hub.hcompany.ai/agents-api/browser/profiles) et [coffres](https://hub.hcompany.ai/agents-api/vaults/overview). Montrer les passages utiles, sans accéder aux secrets du compte. |
| HG04 / HC08 | « Cet essai affiche Interrupted et je pensais que rien ne s'était passé. Aide-moi à vérifier s'il a produit une réponse et ce qu'on peut vraiment dire de son arrêt. Montre-moi aussi la règle dans la documentation. » | Session de démonstration choisie, puis [cycle des sessions](https://hub.hcompany.ai/agents-api/sessions/overview). Identifier les faits ; ne pas inventer un timeout ou une panne de livraison. |
| HG05 / HC09 | « J'ai ouvert ces deux essais. On me dit que le second est plus rapide et moins cher. Aide-moi à retrouver les mesures réellement disponibles et à voir si cette comparaison a du sens. » | Deux sessions préalablement désignées. Montrer demande, conditions et métriques accessibles, avec libellés et unités ; une donnée absente reste inconnue. Aucun accès facturation. |
| HG06 / HC02 | « La doc parle de quota et de file d'attente. Montre-moi les champs et les états à regarder. Avec cet exemple fictif : dix places, quatre actives, six disponibles, comment garder deux places pour mes collègues ? » | Docs : [quota](https://hub.hcompany.ai/agents-api/sessions/quota) et [limites](https://hub.hcompany.ai/agents-api/plans-and-limits). Retrouver les explications à l'écran ; aucun appel au quota du compte ni lancement. |
| HG07 / HC04 | « Notre dashboard considère completed comme une réussite. Montre-moi dans la doc où vérifier ce que veut dire outcome et aide-moi à comprendre le cas partial. Qu'est-ce qu'il faudrait encore vérifier ? » | Docs : [erreurs et outcomes](https://hub.hcompany.ai/agents-api/errors), puis [sortie structurée](https://hub.hcompany.ai/agents-api/structured-output) si utile. L'utilisateur retrouve la distinction et formule la preuve métier manquante. |
| HG08 / HC05 | « Je veux transmettre cet essai à notre support avec assez d'informations pour le comprendre. Montre-moi ce qu'il faut repérer dans la session et où la doc explique comment conserver événements et captures. Ne partage ni ne télécharge rien. » | Session autorisée, puis [événements](https://hub.hcompany.ai/agents-api/sessions/events) et [ressources](https://hub.hcompany.ai/agents-api/sessions/resources). Repérer les éléments et préparer une liste orale ; aucun export effectif. |
| HG09 / HC10 | « Un collègue voudrait reproduire cet essai. Guide-moi pour retrouver le modèle, les réglages du navigateur et les versions disponibles dans cette trace. Dis-moi ce qu'on ne peut pas vérifier ici. » | Même session de démonstration. Montrer uniquement les métadonnées effectivement accessibles. Ne pas quitter cette session pour inspecter des réglages ou historiques non désignés. |
| HG10 / HC06 | « Une mise à jour de notre skill change les résultats. Montre-moi dans la doc où trouver sa version et comment préparer une comparaison reproductible sans modifier la skill actuelle. » | Docs : [skills](https://hub.hcompany.ai/agents-api/skills/overview). Montrer les passages concernant versions et références ; proposer oralement un protocole, sans sauvegarde ni nouvel essai. |

Pendant un essai, dire ce qui bloque (« je ne vois pas ce bouton », « cette
explication ne m'aide pas »). L'opérateur doit noter une correction ou interruption
comme telle. Une nouvelle dictée peut remplacer la tâche en cours dans la boucle
Matteo ; ce n'est pas automatiquement un commentaire attaché à l'étape.

## Commandes et instrumentation : ce qui existe dans le code

Lecture du checkout de travail, pas preuve que ce binaire tourne déjà :

- `hcs-agent talk` propose le push-to-talk : maintenir la touche, parler, relâcher.
  Défaut **⌘H**, configurable par `--key` ou `HCS_PTT_KEY` ; `f9` est un exemple
  accepté par le CLI. Vérifier le raccourci choisi sur ce Mac avant la séance.
- Lancement recommandé depuis `h-companion`, avec le Python de l'environnement
  de test disposant des dépendances. Le lanceur utilise le checkout de travail :

  ```bash
  python3 scripts/run-h-company-human.py --key cmd+h
  ```

  Puis, dans un autre terminal, ouvrir la dernière app desktop :

  ```bash
  HCS_CONTROL_URL=http://127.0.0.1:8780 HCS_BACKEND_URL=http://127.0.0.1:8781 \
    npm --prefix desktop start
  ```

  Le lanceur fixe `HCS_GUIDE_OBSERVE_ONLY=1` et l'autonomie à 0 avant d'importer
  le CLI ; le contrôleur maintient ce niveau même si l'app demande de le changer.
  Il lance `talk --software hcompany` **sans `--confirm`** : la question orale
  approuve cette aide en lecture seule. L'option `--confirm` du CLI demanderait
  une confirmation dans le terminal, pas dans l'interface desktop.
  `Ctrl+C` interrompt ; pendant l'attente GUIDE, le CLI accepte aussi `q` puis
  Entrée. Un arrêt confirmé doit être vérifié.
- **Route H ajoutée, passage réel à confirmer :** `talk --software hcompany`
  conserve la question verbatim et choisit `hcompany_general_guide`, sans routage
  approximatif vers Odoo. Cette procédure observe dynamiquement la page ; elle
  n'impose pas une séquence de clics préécrite. Un contexte historique facultatif
  peut conserver demande précédente et dernière consigne, mais ne vaut ni preuve
  de l'écran actuel ni nouvelle autorisation. Les dix cartes restent facultatives.
- Le dossier privé par défaut est
  `~/Library/Application Support/HCompanionResearch/human-h-company`, avec les
  essais sous `episodes/<session>`. Le lanceur démarre le backend local 8781 et
  le contrôle 8780 ; il consigne modèle, révision, mode et nombre réel de documents
  dans `runtime.json`. Le corpus H existant est chargé s'il est présent : ne pas
  annoncer onze documents sans vérifier ce compteur. L'export des seules sessions
  H liées à l'essai produit `archive-status.json` ; complet, partiel et indisponible
  restent distincts.
- La synthèse vocale de la boucle Matteo dépend d'ElevenLabs et d'un lecteur audio.
  Gladia assure la transcription ; sa présence seule ne garantit pas une réponse
  parlée. Les annotations et le texte doivent être vérifiés en live.
- La boucle desktop possède maintenant `request.json`, `events.jsonl` et
  `report.json` dans `<runs-dir>/<session>`, puis un retour explicite : écran
  **Mon retour**, bouton **Dicter mon retour**, dictée avec la touche choisie,
  relecture, choix réussite/utilité et **Enregistrer mon retour**. Le bouton arme
  la prochaine transcription comme feedback ; parler sans l'armer peut créer
  une nouvelle demande. Le brouillon devient `feedback-draft.json`, et la
  confirmation crée `labels.json` pour cet essai terminé. Ce parcours est présent
  dans le code, mais sa validation dans l'app lancée reste à faire par l'opérateur.
  Le push-to-talk efface le WAV temporaire : on conserve ici la transcription,
  pas un enregistrement audio brut. Le partage de captures et l'entraînement
  restent désactivés dans ce nouveau retour desktop.
- Notre ancien panneau **VoicePilot** possède « Dicter mon retour », les choix de
  réussite/utilité et « Enregistrer mon retour ». `pilot/server.py` conserve audio,
  transcription et `episodes/<sid>/labels.json` après la fin du passage. Il faut
  un épisode géré par ce pilote : un identifiant créé par `talk` n'y est pas rattaché
  automatiquement. `run-voice-pilot.py` reste configuré pour des scénarios Odoo et
  des révisions épinglées ; ce n'est pas un lanceur générique de la dernière app H.

**À confirmer avant d'annoncer une collecte enregistrée :** révision réellement
lancée, route H disponible, mode GUIDE/autonomie 0, dossier privé et `session_id`,
capture de la demande, stockage du retour et correspondance des labels à cet essai.
Si le retour n'est pas encore raccordé, recueillir une note explicitement liée à
l'essai et la marquer provisoire ; ne pas annoncer qu'un audio a été sauvegardé.

## Retour à recueillir après chaque essai

> « J'ai réussi / partiellement réussi / pas réussi / je n'ai pas pu vérifier.
> Ce qui m'a aidé, c'est… Ce qui m'a bloqué, c'est… L'aide était utile / inutile /
> je ne sais pas. Maintenant, je saurais / ne saurais pas retrouver cela seul. »

Demander ensuite de retrouver un repère ou reformuler un contrôle sans aide.
Conserver séparément : preuve observée de tâche, réussite déclarée, utilité déclarée,
compréhension, corrections et durée. Dans VoicePilot, les champs existants sont
`task_success_user` (`success|partial|failed|unknown`) et `useful` (`yes|no|unknown`).
Le nouveau retour desktop utilise `success` (`yes|partial|no|unknown`) et `useful`
(`yes|no|unknown`), avec une correspondance enregistrée dans `task_success_user`.
La réutilisation pour entraînement n'est pas activée par ce parcours : elle exige
un consentement distinct, jamais déduit du fait de participer. Un label IA n'est
jamais un retour humain.

Sources de code : `agent/src/hcs_agent/cli.py`, `voice.py`, `control.py`,
`procedures.py`, `speech.py`, `desktop_feedback.py`, `desktop/renderer/index.html`,
`app/src/VoicePilot.tsx`, `pilot/server.py` et
`scripts/run-voice-pilot.py`, `scripts/run-h-company-human.py`.
Catalogue source : [HC01–HC10](h-company-cloud-scenarios.md).

# H-Companion — desktop vision lab (Edouard)

Première tranche Electron du projet : WebGazer local, calibration, région d’intérêt,
capture propre, aperçu du payload et appel d’analyse Holo avec tokens et latence réels.
Cette version **analyse des images sans exécuter d’action souris/clavier**. La boucle
d’intervention de Matteo reste à raccorder ; aucun contrat partagé n’est modifié ici.

## Démarrer sur Mac

Prérequis : macOS 14+, Node compatible avec Vite 8, npm, Xcode Command Line Tools
(`xcode-select --install` si nécessaire). Développement vérifié avec Node 26.

```bash
cd app
npm ci
cp .env.example .env
# Renseigner HAI_API_KEY dans .env pour envoyer à Holo ; facultatif pour capturer localement.
npm run dev
```

`npm run dev` copie les assets locaux WebGazer/MediaPipe, compile le helper ScreenCaptureKit,
puis lance Vite et Electron. Aucun fichier du visage ne part vers Holo. Les modèles de tracking
ne sont pas téléchargés depuis un CDN à l’exécution.

Pour le build sans serveur de développement :

```bash
npm run build
npm start
```

Le processus principal lit `app/.env` ; la clé n’est jamais exposée au renderer.
Le modèle par défaut est `holo4-27b`. Le sélecteur du panneau propose aussi `holo4-35b-a3b`
et `holo3-1-35b-a3b`. Changer de modèle conserve la même image pour un nouvel appel explicite ;
les mesures affichent le modèle qui les a réellement produites. `HCS_MODEL` permet de choisir
le défaut au démarrage. Le transport utilise la [Models API officielle](https://hub.hcompany.ai/models-api/overview).

## Parcours de démonstration

1. Ouvrir un logiciel avec des données fictives sur l’écran principal.
2. Activer la caméra depuis le panneau, puis confirmer dans la fenêtre de calibration.
   La calibration et l’overlay se masquent pendant la demande macOS : cliquer **Autoriser**
   dans le dialogue système. La calibration revient après la réponse. Si l’accès avait déjà
   été refusé : Réglages Système → Confidentialité et sécurité → Caméra → Electron, puis
   relancer l’app. **Échap** permet de quitter la calibration. Fixer puis cliquer les neuf cibles ; rester sur chacune
   pendant la collecte. Quatre autres positions servent à la validation sans apprentissage.
3. Commencer le suivi. La fenêtre de calibration devient transparente et laisse passer
   les clics. L’erreur de validation reste affichée dans le panneau, y compris après arrêt du suivi.
   Aucun point de regard n’est montré ; le rectangle pointillé est la zone candidate.
4. Choisir le regard, le curseur ou l’écran complet, les dimensions de la région en pixels
   source et l’ajout éventuel d’un aperçu global (largeur maximale 640 px).
   Les dimensions enregistrées sont affichées séparément de la saisie. Le bouton de capture
   applique les deux champs et attend leur enregistrement avant de préparer l’image.
5. Cliquer **Capturer dans 3 s**, puis regarder la partie utile du logiciel. L’image reste
   locale. macOS peut demander la permission d’enregistrement de l’écran au premier essai ;
   après accord, relancer l’app si nécessaire. Le helper reçoit les identifiants natifs des
   fenêtres visibles H-Companion et les exclut, dont le panneau et les deux overlays.
6. Inspecter l’image, les coordonnées et l’éventuel repli. **Envoyer à Holo** transmet
   exactement les buffers PNG affichés. Le rectangle plein désigne cette frame, figée même
   si le regard bouge pendant l’appel. L’aperçu global, s’il existe, est envoyé aussi.
7. Lire la réponse, la durée de requête et l’usage API. Annuler interrompt l’attente locale ;
   cela ne garantit pas l’annulation de la facturation serveur. Arrêter la caméra reste
   possible pendant un appel. Fermer l’app coupe ses fenêtres et leurs pistes caméra.

Une calibration imprécise n’est pas une preuve de bon suivi. Refaire la calibration,
élargir la région ou choisir le curseur/plein écran. La version rapporte l’erreur médiane
sur les cibles de validation, mais n’ajuste pas encore automatiquement la taille du rectangle.

## Essai continu sans panneau

1. Préparer le logiciel cible, puis choisir **Curseur** pour vérifier le recadrage sans caméra,
   ou **Regard** après calibration. Garder la même taille, par exemple 800 × 600, entre essais.
2. Dans **Cadre de la région**, comparer **Écran** puis **Fenêtre regardée**. Le second mode
   utilise la fenêtre visible sous le point de regard ou le curseur et borne le crop à son
   rectangle. Sans fenêtre éligible, le panneau indique le retour à la région d’écran.
3. Choisir 15, 30 ou 60 secondes et cliquer **Observer et masquer le panneau**. Trois secondes
   permettent de revenir au logiciel ; environ une capture locale par seconde suit, sans
   chevauchement ni rattrapage des captures lentes. Le contour est désactivé par défaut pour
   ne pas attirer le regard. Le panneau revient automatiquement à la fin.
4. **⌘⇧Espace** (Ctrl+Maj+Espace hors Mac) arrête l’essai et rappelle le panneau. Le rappel
   de l’application depuis le Dock arrête aussi l’observation. Une erreur de capture ou la
   limite de mémoire interrompt la session et restaure le panneau.
5. Revoir les captures avec **Précédente / Suivante** : écran de référence avec rectangle,
   crop exact, fenêtre choisie et coordonnées. Annoter **Cible présente**, **Cible absente**
   ou **Impossible à juger**, selon la cible définie avant la séquence. Le taux affiché porte
   seulement sur les captures évaluables ; ce n’est pas un taux de réussite métier.

Aucun appel Holo automatique. Seul **Envoyer à Holo** transmet la capture sélectionnée et
son aperçu global éventuel. L’image de référence destinée à la revue (largeur maximale
1 024 px) reste locale et n’entre jamais dans le payload. Les observations restent en mémoire,
avec un budget de conservation de 64 Mio (pas un plafond de RAM du processus). **Effacer**
ou démarrer un nouvel essai remplace cette série : terminer les annotations avant la suite.

Le repérage des fenêtres respecte leur ordre devant/derrière au point sélectionné. Il ne
reconstitue pas les parties masquées : le crop contient les pixels réellement visibles,
y compris une éventuelle fenêtre superposée ailleurs dans le rectangle. La géométrie des
fenêtres est relevée juste avant la capture, sans atomicité avec les pixels ; évaluer les
fenêtres stables avant les déplacements rapides. Le suivi explicite de pose de tête et la
décision Jev ne sont pas encore implémentés.

## Ce qui est mesuré

- `detail.dataUrl` et `global.dataUrl` sont les buffers utilisés par `buildRequest()`, sans
  nouvelle capture, annotation ni réencodage entre aperçu et envoi. Chaque PNG a son SHA-256.
- `cropRect` est en **pixels de capture**, origine en haut à gauche ; le rectangle de l’overlay
  est converti vers les points d’affichage à partir des dimensions réelles. `scaleFactor` ne
  sert qu’à estimer la zone candidate avant la première capture.
- `requestedRegion` conserve les dimensions réellement appliquées à cette capture.
  `regionDisposition` distingue une région recadrée (`crop`), un plein écran demandé
  (`full-requested`), un repli (`full-fallback`) et des dimensions couvrant toute la source
  (`full-size`). Par exemple, demander 1 600 × 1 216 sur une source 1 470 × 956 produit un
  plein écran ; 896 × 704 reste un crop de cette taille, même au bord. Quand l’image détaillée
  couvre déjà toute la source, aucun aperçu global redondant n’est ajouté.
- `captureInterval` borne l’appel natif de capture ; `capturedAt` est sa fin, pas un timestamp
  matériel exact. `preparedAt` est la fin de préparation de l’observation.
- `preparationMs` comprend capture native, recadrage et encodage, et exclut les trois secondes
  laissées à l’utilisateur. `latencyMs` couvre l’appel HTTP jusqu’à sa réponse JSON exploitable.
  Ce n’est ni le temps au premier token ni le temps d’une tâche complète.
- Les tokens d’entrée/sortie/total/cache viennent de `usage`. Une valeur absente reste inconnue,
  y compris après échec. Aucun compteur de gains ou coût n’est inventé.
- `gazeAgeMs` est l’âge depuis la **réception du callback** WebGazer, au moment du choix,
  **avant** la capture native. Ce n’est ni une latence webcam ni l’âge à la fin de préparation :
  WebGazer ne fournit pas un horodatage fiable de la frame caméra. Coordonnées, validité et âge
  sont figés ensemble avant la capture ; un changement ultérieur du suivi ne modifie pas cette
  décision. Le repli s’applique si le signal est absent, hors écran, non calibré ou âgé de plus
  de 1 500 ms au moment du choix. L’intervalle natif et le temps de préparation restent séparés.

Les captures temporaires sont effacées dans un `finally`, y compris lors des erreurs.
Les observations et les résultats ne persistent qu’en mémoire. Pas d’export automatique de
captures ou de traces privées. Le panneau agrège les annotations d’une session locale,
mais pas encore les coûts et performances de plusieurs essais Holo.

## Architecture et raccordement de l’agent

| Fichier | Rôle |
| --- | --- |
| `src/App.tsx` | Panneau, sélection, approbation d’envoi, payload et mesures |
| `src/Tracker.tsx`, `src/lib/webgazer.ts` | Calibration explicite, suivi local, arrêt des pistes caméra |
| `src/Overlay.tsx` | Rectangle candidate / envoyé, sans interception de clics |
| `src/ObservationPanel.tsx`, `electron/observation-session.mjs` | Sessions locales bornées, revue et annotations |
| `electron/main.mjs`, `preload.cjs` | Fenêtres, permissions, IPC borné, orchestration et annulation |
| `native/capture.swift`, `electron/capture.mjs` | ScreenCaptureKit, exclusion du processus, PNG et recadrage |
| `electron/geometry.mjs` | Transformations capture / écran / coordonnées Holo |
| `electron/holo.mjs` | Transport de l’image immuable, réponse et usage réels |
| `src/lib/types.ts` | Types locaux de cette tranche UI ; pas le contrat backend |

Le panneau peut appeler Holo dès que la clé est renseignée, sans attendre le backend agent.
Ce transport est une sonde visuelle à appel unique. Pour l’intégration avec Matteo :

1. Réutiliser la construction d’observation et ses identifiants dans la boucle de l’agent.
2. Faire remonter l’image exacte de chaque requête, son usage et ses horodatages.
3. Pour toute action, associer les coordonnées à une image précise et vérifier leur transformation.
   Cette version ne devine pas à quelle image appartiendrait un clic.
4. Proposer les extensions du contrat à son propriétaire ; modifier les modèles sources puis
   régénérer les schémas, sans éditer `contracts/*.schema.json` à la main.

L’API produit prévue reste `127.0.0.1:8765` :

| Méthode | Chemin | Contrat |
| --- | --- | --- |
| POST | `/interventions` | `InterventionRequest` → plan à approuver |
| POST | `/interventions/{id}/approve` | `ApproveCommand` |
| POST | `/interventions/{id}/stop` | `StopCommand` |
| POST | `/interventions/{id}/feedback` | `FeedbackCommand` |
| GET | `/interventions/{id}` | Snapshot |
| GET | `/interventions/{id}/report` | `InterventionReport` |
| WS | `/interventions/{id}/ws` | `AgentEvent` |

Ces routes ne sont **pas encore consommées** par ce panneau. Les fixtures de test sont
explicitement simulées ; une vraie analyse Holo n’est pas une validation de la boucle desktop.

## Vérifier

```bash
npm run typecheck
npm test
npm run build
npx playwright install chromium   # une fois, pour les tests d’interface
npm run test:ui
# Alternative si Chrome est déjà installé :
PLAYWRIGHT_BROWSER_CHANNEL=chrome npm run test:ui
# Après npm run build : Electron avec caméra synthétique, sans capture ni Holo.
npm run test:electron
```

Les tests couvrent les conversions Retina et bords, le payload exact, l’usage inconnu,
l’annulation, la calibration contrôlée et l’arrêt des pistes caméra. Les tests UI injectent
un bridge **simulé explicite** et n’accèdent ni à la webcam ni à Holo. Ils ne prouvent pas
la précision de WebGazer ni l’exclusion native en conditions réelles : vérifier ces deux
points sur le Mac avant la démonstration et journaliser les essais réels selon le dépôt.

Contrôles manuels du 7 novembre 2026 (Paris), **pas un benchmark comparatif** :

- Une analyse réelle Holo3.1 d’une image entièrement fictive a répondu correctement
  « Il reste 2 bouteilles à recevoir » : 544 tokens d’entrée, 10 de sortie, 554 au total,
  0 en cache, 2 468 ms. Appel visuel unique, sans action desktop et sans capture utilisateur.
- Une capture locale réelle a produit une image de 1 470 × 956 pixels en 904 ms de préparation.
  Le panneau et l’overlay visibles ont été vérifiés absents de l’aperçu. Cette image n’a pas
  été envoyée à Holo. L’essai a révélé puis permis de corriger la recherche d’exclusions
  basée uniquement sur le PID : elle utilise désormais les identifiants natifs des fenêtres.
- La précision du regard sur webcam réelle nécessite la calibration de l’utilisateur ;
  elle n’est pas validée par ces deux contrôles.
- Un essai humain ultérieur a terminé les neuf cibles puis les quatre cibles de validation :
  médiane affichée de **393 px d’affichage**, suivi actif confirmé dans le panneau. Cette
  précision grossière ne valide pas une petite région ; la couverture de la cible dans
  la capture reste à vérifier, avec une région élargie et l’aperçu global.
- Deux sondes visuelles réelles sur la même image fictive ont ensuite confirmé le fonctionnement
  de `holo4-27b` (554 tokens, 3 174 ms) et `holo4-35b-a3b` (559 tokens, 2 386 ms), avec la bonne
  réponse dans les deux cas. Un appel par modèle ne permet pas de classer leurs performances.
- Après correction de l’enregistrement des dimensions, une capture humaine en mode regard
  a réellement produit **800 × 600** sur une source **1 470 × 956** (origine 82, 158), soit
  **34 % de surface**. Le panneau confirme la demande appliquée, un âge du signal de 15 ms
  au choix et une préparation de 389 ms. Aucun appel Holo pour cet essai : ce pourcentage
  décrit l’aire du crop seul, pas les économies de tokens ni la réussite d’une tâche.
- Le mode continu a conservé **15 captures en 15 secondes** (après les trois secondes
  de préparation), en mode curseur sur une page publique de H, avec retour automatique
  du panneau. La première image : fenêtre **Google Chrome**, crop **800 × 600**, origine
  **14, 310**, source **1 470 × 956**, préparation **449 ms**. Référence et crop vérifiés
  visuellement ; aucun envoi Holo. Ce contrôle valide le flux technique, pas le suivi du regard.

## Limites et dépendances

- Capture : macOS 14+ uniquement ; un écran principal. Pas encore de packaging/signature
  macOS ni de version Windows. Xcode sert à compiler le helper de développement.
- Le helper identifie les fenêtres par leur `CGWindowID` fourni par Electron, avec les
  correspondances de processus en complément. Il refuse la capture si une fenêtre visible
  demandée n’est pas retrouvée. Il ne s’appuie pas sur `setContentProtection`, insuffisant
  avec ScreenCaptureKit.
- L’overlay peut influencer le regard. Le désactiver pour le lot de mesures principales.
- La calibration n’est jamais `alwaysOnTop`. L’overlay est caché pendant les permissions et
  la calibration, puis revient au niveau `floating` ; aucun niveau `screen-saver` n’est utilisé.
- Aucun entraînement implicite sur les clics du logiciel ou de l’agent. Les profils ne sont
  pas conservés entre sessions. Garder l’éclairage et la position après calibration.
- WebGazer **3.5.3** est épinglé. Sa licence **GPL-3.0-or-later**, le bundle et les assets
  MediaPipe sont copiés localement par `npm run assets` (licence incluse). Voir le
  [dépôt amont](https://github.com/brownhci/WebGazer). Le code ne suppose pas une licence MIT.
- Le panneau utilise une CSP sans évaluation JS dynamique. Seule `tracker.html`, qui charge
  le moteur MediaPipe local, autorise `unsafe-eval` nécessaire à sa glue WASM. Le processus
  principal n’accorde l’accès caméra qu’à la fenêtre tracker et limite ses IPC.

Références : [API H](https://hub.hcompany.ai/models-api/overview),
[coordonnées Holo](https://hub.hcompany.ai/models-api/build-an-agent/core-concepts),
[ScreenCaptureKit](https://developer.apple.com/documentation/screencapturekit),
[WebGazer](https://webgazer.cs.brown.edu/).

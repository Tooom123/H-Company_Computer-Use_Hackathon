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
Le modèle par défaut est `holo3-1-35b-a3b`. Définir `HCS_MODEL` pour un autre modèle accessible
à votre clé (par exemple `holo4-27b`). Le transport utilise la [Models API officielle](https://hub.hcompany.ai/models-api/overview).

## Parcours de démonstration

1. Ouvrir un logiciel avec des données fictives sur l’écran principal.
2. Activer la caméra depuis le panneau, puis confirmer dans la fenêtre de calibration.
   Accepter la permission macOS. Fixer puis cliquer les neuf cibles ; rester sur chacune
   pendant la collecte. Quatre autres positions servent à la validation sans apprentissage.
3. Commencer le suivi. La fenêtre de calibration devient transparente et laisse passer
   les clics. Aucun point de regard n’est montré ; le rectangle pointillé est la zone candidate.
4. Choisir le regard, le curseur ou l’écran complet, les dimensions de la région en pixels
   source et l’ajout éventuel d’un aperçu global (largeur maximale 640 px).
5. Cliquer **Capturer dans 3 s**, puis regarder la partie utile du logiciel. L’image reste
   locale. macOS peut demander la permission d’enregistrement de l’écran au premier essai ;
   après accord, relancer l’app si nécessaire. Le helper exclut toutes les fenêtres appartenant
   au processus Electron, dont le panneau et les deux overlays.
6. Inspecter l’image, les coordonnées et l’éventuel repli. **Envoyer à Holo** transmet
   exactement les buffers PNG affichés. Le rectangle plein désigne cette frame, figée même
   si le regard bouge pendant l’appel. L’aperçu global, s’il existe, est envoyé aussi.
7. Lire la réponse, la durée de requête et l’usage API. Annuler interrompt l’attente locale ;
   cela ne garantit pas l’annulation de la facturation serveur. Arrêter la caméra reste
   possible pendant un appel. Fermer l’app coupe ses fenêtres et leurs pistes caméra.

Une calibration imprécise n’est pas une preuve de bon suivi. Refaire la calibration,
élargir la région ou choisir le curseur/plein écran. La version rapporte l’erreur médiane
sur les cibles de validation, mais n’ajuste pas encore automatiquement la taille du rectangle.

## Ce qui est mesuré

- `detail.dataUrl` et `global.dataUrl` sont les buffers utilisés par `buildRequest()`, sans
  nouvelle capture, annotation ni réencodage entre aperçu et envoi. Chaque PNG a son SHA-256.
- `cropRect` est en **pixels de capture**, origine en haut à gauche ; le rectangle de l’overlay
  est converti vers les points d’affichage à partir des dimensions réelles. `scaleFactor` ne
  sert qu’à estimer la zone candidate avant la première capture.
- `captureInterval` borne l’appel natif de capture ; `capturedAt` est sa fin, pas un timestamp
  matériel exact. `preparedAt` est la fin de préparation de l’observation.
- `preparationMs` comprend capture native, recadrage et encodage, et exclut les trois secondes
  laissées à l’utilisateur. `latencyMs` couvre l’appel HTTP jusqu’à sa réponse JSON exploitable.
  Ce n’est ni le temps au premier token ni le temps d’une tâche complète.
- Les tokens d’entrée/sortie/total/cache viennent de `usage`. Une valeur absente reste inconnue,
  y compris après échec. Aucun compteur de gains ou coût n’est inventé.
- `gazeAgeMs` est l’âge depuis la **réception du callback** WebGazer, au moment où la sélection
  est évaluée. WebGazer ne fournit pas un horodatage fiable de la frame caméra : ce champ ne
  mesure pas la latence du tracker. Le signal est figé avant la demande de capture, puis un
  repli plein écran est appliqué s’il est absent, hors écran, non calibré ou âgé de plus de
  1 500 ms à la préparation. Un démarrage lent peut donc entraîner un repli.

Les captures temporaires sont effacées dans un `finally`, y compris lors des erreurs.
L’observation et le résultat ne persistent qu’en mémoire. Pas d’export automatique de captures
ou de traces privées. Le panneau ne fournit pas encore l’agrégation sur plusieurs tentatives.

## Architecture et raccordement de l’agent

| Fichier | Rôle |
| --- | --- |
| `src/App.tsx` | Panneau, sélection, approbation d’envoi, payload et mesures |
| `src/Tracker.tsx`, `src/lib/webgazer.ts` | Calibration explicite, suivi local, arrêt des pistes caméra |
| `src/Overlay.tsx` | Rectangle candidate / envoyé, sans interception de clics |
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

## Limites et dépendances

- Capture : macOS 14+ uniquement ; un écran principal. Pas encore de packaging/signature
  macOS ni de version Windows. Xcode sert à compiler le helper de développement.
- Le helper ne capture rien s’il ne peut pas identifier l’application à exclure. Il ne
  s’appuie pas sur `setContentProtection`, insuffisant avec ScreenCaptureKit.
- L’overlay peut influencer le regard. Le désactiver pour le lot de mesures principales.
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

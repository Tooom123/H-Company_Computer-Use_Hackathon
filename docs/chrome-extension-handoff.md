# Passation — extension Chrome de guidage H-Companion

8 novembre 2026. **Document de conception, contrat proposé `hcompanion-dom/0.1`.**
Les messages ci-dessous ne sont ni un contrat partagé généré ni des endpoints
déjà disponibles. Aucun appel ne doit être envoyé vers une route inventée.

L'objectif est de montrer précisément un contrôle dans la page, laisser la
personne agir, puis vérifier ce qui a changé. Le DOM fournit des cibles et leurs
positions ; H prépare l'explication et la prochaine étape. La voix, les traces
et le retour humain doivent réutiliser l'app existante.

## Périmètre du premier parcours

Une extension Manifest V3, un utilisateur, un onglet actif, un document principal,
une demande et un parcours H documentaire en lecture seule. Exemple : « Montre-moi
où la doc explique le navigateur cloud, puis aide-moi à repérer sa configuration. »
La personne ouvre les liens et défile ; l'extension surligne et explique.

Activer l'observation par un geste explicite sur l'extension, avec `activeTab` et
`scripting`, sans `<all_urls>`. `activeTab` accorde un accès temporaire à la suite
du geste utilisateur ; un changement d'origine retire cet accès. Cela ne remplace
pas notre propre liste d'origines autorisées. Voir la
[documentation Chrome activeTab](https://developer.chrome.com/docs/extensions/develop/concepts/activeTab).

Liste applicative à figer entre les propriétaires avant le test :

| Cible | Proposition pour le pilote | État |
| --- | --- | --- |
| Documentation H | `https://hub.hcompany.ai`, chemins documentaires approuvés | Premier parcours proposé |
| Compte H | `https://platform.hcompany.ai`, une session de démonstration désignée | Hors premier parcours ; autorisation et chemins à définir |
| Cognition / Devin | Origine documentaire exacte à confirmer avec le teammate | Désactivé tant que la liste n'est pas validée |

Pas de joker de sous-domaines. Une redirection vers l'authentification, un coffre,
la facturation ou une origine non prévue suspend l'observation. Ne pas inclure
Google/SSO pour « faire fonctionner le login » ; l'utilisateur se connecte à part.

## Ce qui existe, ce qui reste à raccorder

| Composant existant | Réutilisation prévue / limite actuelle |
| --- | --- |
| `agent/src/hcs_agent/cli.py`, `runner.py`, `backend.py` | Moteur H, mode GUIDE et arrêt. Le chemin actuel observe des captures : il ne consomme pas encore ce catalogue DOM. |
| `agent/src/hcs_agent/voice.py`, `speech.py` | Dictée et lecture des consignes ; Stop et prise de parole interrompent la voix. Conserver ces contrôles. |
| `agent/src/hcs_agent/control.py` | Contrôle local : état, arrêt, voix, feedback. Le lanceur humain utilise le port 8780 ; le défaut général est 8768. Aucun canal DOM ni appairage extension n'y existe. |
| `scripts/run-h-company-human.py` | Runtime humain, autonomie zéro / observation seulement, corpus H et journaux privés. Ne pas lancer une seconde session qui pilote le même bureau. |
| `agent/src/hcs_agent/desktop_feedback.py` | `request.json`, `events.jsonl`, rapport et feedback explicitement confirmé dans `labels.json`. |
| Backend / portail entreprise | Remontée des traces et retours ; le lanceur humain utilise le backend local 8781. Ce port n'est pas une API DOM. |

Prévoir un adaptateur validé avec Matteo entre les messages DOM et le moteur.
Un catalogue DOM ne peut pas être simplement envoyé au backend actuel en supposant
qu'il remplace la capture. **Le premier flux proposé n'envoie pas de screenshot** :
si le moteur ne peut pas fonctionner ainsi, retourner « contexte insuffisant »
ou faire évoluer explicitement le périmètre, sans capture implicite. Une expérience
hybride image + DOM sera une option séparée, visible et consentie.

## Répartition des responsabilités

- Le teammate extension possède **`extension/`** : manifest, service worker,
  content script, popup, overlay dans la page, tests et guide de chargement local.
- Matteo et le propriétaire du runtime possèdent le raccord moteur et son
  adaptateur. Coordonner toute modification de `cli.py`, `backend.py` ou du
  contrôleur ; aucun changement parallèle de ces fichiers sans accord.
- Le propriétaire du backend raccorde les événements au journal et au portail.
  Les contrats partagés restent sous `agent/src/hcs_agent/contract.py` ; si une
  modification devient nécessaire, régénérer `contracts/` avec
  `scripts/export_contracts.py`, conformément à `AGENTS.md`.
- Edouard réalise le parcours et confirme son feedback. Une validation technique
  de l'extension ne constitue pas ce retour humain.

Commencer avec un faux transport local dans les tests de l'extension. Valider le
contrat et l'appairage avec le propriétaire du runtime avant le raccord réel.

## Architecture et appairage local proposés

Le content script reste dans le monde isolé et lit le DOM visible. Il échange des
messages typés avec le service worker ; seul le service worker parle au pont local.
Le monde isolé sépare les variables JavaScript, **pas le DOM partagé** : son contenu
reste une donnée non fiable, jamais une instruction autorisant une action. Voir
[les content scripts Chrome](https://developer.chrome.com/docs/extensions/develop/concepts/content-scripts)
et [leur messagerie](https://developer.chrome.com/docs/extensions/develop/concepts/messaging).

Le pont doit être limité à `127.0.0.1`, sur un port convenu explicitement. Les
requêtes réseau d'une extension privilégiée passent par le service worker avec
les permissions d'hôte nécessaires ; ne pas exposer un proxy qui accepte une URL
arbitraire venant de la page. Les permissions d'hôte ne constituent pas une
restriction par chemin : appliquer celle-ci dans notre code. Voir
[les requêtes réseau Chrome](https://developer.chrome.com/docs/extensions/develop/concepts/network-requests).

**L'appairage ci-dessous reste à implémenter :**

1. L'app locale affiche une invitation courte durée avec secret aléatoire à usage
   unique, d'au moins 128 bits. L'utilisateur le transmet uniquement à la popup
   de l'extension ; jamais au DOM du site, à une URL ou à un journal.
2. Le pont confirme l'extension attendue et le périmètre demandé dans l'app locale,
   échange un défi frais, puis délivre un jeton de session borné en durée et en
   capacités : observation, consigne, événement et arrêt, pour l'onglet choisi.
3. Le service worker conserve ce jeton dans un contexte privé de l'extension,
   inaccessible au content script/page. Ni la clé H ni celles de Gladia/ElevenLabs
   ne quittent le runtime. Déconnexion/arrêt révoque le jeton ; une perte d'état
   du worker requiert une reprise authentifiée ou un nouvel appairage.
4. Le pont vérifie jeton, durée, numéro de séquence et limites sur chaque message.
   Contrôler `Host` loopback et l'origine extension lorsque présente ; l'ID et
   l'en-tête `Origin` seuls ne sont pas une preuve d'authentification. Refuser une
   origine web inattendue et tester les en-têtes réels du service worker.

Le contrôle desktop actuel vérifie `Host` et **`X-HCS-App: 1`**. Cette valeur est
publique, pas un secret d'appairage : une extension peut la reproduire. Ne pas
ouvrir les routes desktop à l'extension en se reposant uniquement dessus. Pas de
CORS `*`, pas de reflet libre d'`Origin`, pas de listener `externally_connectable`
ou `window.postMessage` donnant les capacités du pont à n'importe quelle page.
Une politique CORS précise peut être nécessaire selon le transport ; elle ne
remplace jamais le jeton. Ne pas modifier les protections du contrôleur existant
pour contourner un échec d'intégration.

## Contrat proposé `hcompanion-dom/0.1`

Les deux côtés valident une liste fermée de types et de champs ; version inconnue,
valeurs non finies, message trop gros, onglet ou document incohérent sont refusés.
Ce protocole ne contient **aucune commande de clic, saisie, JavaScript, shell,
navigation, téléchargement ou lecture de secret**.

### Observation et cibles

Chaque observation porte `run_id`, `observation_id`, `seq`, heure UTC de capture
et horloge monotone du document. Le pont ajoute son heure de réception ; ne pas
soustraire les horloges monotones de processus différents.

Le contexte contient l'onglet, `frame_id=0`, l'identifiant du document, une révision
croissante de la page, l'origine et une URL expurgée. Le service worker recoupe
l'onglet/document avec l'expéditeur Chrome, au lieu de croire les champs fournis
par le content script ; Chrome expose ces métadonnées via
[`MessageSender`](https://developer.chrome.com/docs/extensions/reference/api/runtime#type-MessageSender).
Un rechargement produit un nouveau document ; une route SPA incrémente la révision.

Les candidats sont les contrôles visibles utiles : rôle, libellé court nettoyé,
état activé/désactivé et rectangle. `element_id` est un identifiant opaque local,
stable pour **le même nœud dans ce document seulement** (par exemple un UUID dans
une WeakMap). Un nœud remplacé reçoit un autre ID ; ne pas prétendre stabiliser
un bouton entre navigations avec son texte ou un sélecteur CSS fragile.

Le rectangle vient de `getBoundingClientRect()`, dans le repère explicitement
nommé **`layout_viewport_css`**, accompagné de la taille du viewport, du défilement,
du DPR et de `visualViewport` (offsets, dimensions, scale). Il ne s'agit ni des
pixels physiques de l'écran ni des coordonnées normalisées de l'overlay macOS.
Les transformations et la visibilité doivent être évaluées localement ; détecter
les contrôles recouverts plutôt que de guider vers un élément derrière une modale.
Iframes secondaires, shadow roots fermées, canvas et interfaces hors DOM sont
« non pris en charge » dans le premier parcours.

Exemple fictif, non normatif :

```json
{
  "protocol": "hcompanion-dom/0.1", "kind": "observation",
  "run_id": "demo-1", "observation_id": "obs-12", "seq": 12,
  "captured_at": "2026-11-08T10:00:00Z", "document_monotonic_ms": 8200,
  "context": {"tab_id": 7, "frame_id": 0, "document_id": "doc-a", "revision": 3,
    "origin": "https://hub.hcompany.ai", "url": "https://hub.hcompany.ai/agents-api/overview"},
  "viewport": {"coordinate_space": "layout_viewport_css", "width": 1280, "height": 800,
    "scroll_x": 0, "scroll_y": 120, "device_pixel_ratio": 2,
    "visual": {"offset_left": 0, "offset_top": 0, "width": 1280, "height": 800, "scale": 1}},
  "candidates": [{"element_id": "el-8", "role": "link", "label": "Browser configuration",
    "enabled": true, "rect": {"x": 40, "y": 180, "width": 190, "height": 28}}],
  "truncated": false, "simulated": true
}
```

### Consigne et overlay dans la page

Le moteur propose un `step_id`, une instruction, la raison et un candidat de
l'observation courante. Il ne commande pas un clic. L'extension vérifie le contexte,
retrouve le nœud vivant, remesure son rectangle et dessine dans la page un cadre
avec `pointer-events: none`. Rendre le texte avec `textContent`, sans HTML du modèle.
Exclure notre overlay des observations et des candidats. Son affichage effectif
émet un événement `guidance_shown` avec heure et rectangle mesurés.

```json
{
  "protocol": "hcompanion-dom/0.1", "kind": "guidance",
  "run_id": "demo-1", "step_id": "step-2", "based_on_observation_id": "obs-12",
  "tab_id": 7, "document_id": "doc-a", "revision": 3, "target_element_id": "el-8",
  "instruction": "Ouvre Browser configuration.", "why": "Nous y vérifierons le navigateur cloud.",
  "expected_postcondition": {"criterion_id": "browser-doc-visible", "description": "La section de configuration du navigateur est visible."},
  "expires_in_ms": 2000
}
```

Sur navigation, route SPA, scroll, resize, zoom, changement d'onglet, déplacement
du contrôle ou suppression du nœud : retirer immédiatement le cadre, invalider
la consigne et produire une observation fraîche après stabilisation. Un ID stable
ne rend pas un ancien rectangle valide. Ne pas multiplier les coordonnées par le
DPR dans l'overlay DOM. Tester au moins zoom 100 % et 125 % ; le pinch-zoom peut
rester hors périmètre, avec suspension explicite.

### Clic, résultat observé et feedback

Un clic réel sur le candidat affiché est corrélé au `step_id` et à la dernière
observation par l'extension. L'activation clavier doit être distinguée et testée.
Un clic synthétique ou un événement hors contexte ne devient pas une action
humaine validée. Ce signal indique une interaction, **pas la réussite de l'étape**.

```json
{
  "protocol": "hcompanion-dom/0.1", "kind": "interaction",
  "run_id": "demo-1", "step_id": "step-2", "observation_id": "obs-12", "seq": 13,
  "tab_id": 7, "document_id": "doc-a", "revision": 3, "element_id": "el-8",
  "interaction": "click", "trusted_event": true, "observed_at": "2026-11-08T10:00:02Z"
}
```

Ensuite, conserver une **nouvelle observation** et un résultat de vérification
`satisfied | not_satisfied | unknown`, avec critère et références aux preuves.
Le moteur déclare séparément son interprétation. Une nouvelle page, un clic ou
l'absence d'erreur ne suffisent pas à satisfaire une postcondition. Une preuve
indisponible reste `unknown` ; ne pas forcer le passage à l'étape suivante.

Enfin, la personne confirme ses labels de réussite/utilité et son commentaire.
Réutiliser le parcours de feedback explicite de l'app ; aucun événement DOM
n'écrit un label humain. Conserver la correspondance `run_id` ↔ session locale ↔
session H, puis `step_id` ↔ observations ↔ interactions ↔ vérification. Les noms
de champs ci-dessus sont proposés ; leur mapping vers les contrats existants
doit être validé avec leurs propriétaires.

## Minimisation, bornes et arrêt

Pas de HTML complet, `outerHTML`, état React, cookies, stockage local, corps des
requêtes, presse-papiers, contenu des champs ou identifiants secrets. Retirer query
et fragment des URL par défaut ; expurger aussi les identifiants sensibles dans
les chemins. Les libellés peuvent eux-mêmes contenir des données personnelles :
filtrer avant transmission, et omettre plutôt que prétendre qu'un filtre est parfait.

Bornes de départ proposées : 64 Kio UTF-8 par message, 200 candidats, libellé
120 caractères, instruction 800 caractères, maximum deux observations par seconde
après debounce de 150 ms, une seule observation en attente (la plus récente).
Indiquer les troncatures ; ne pas demander au modèle de choisir une cible absente.
Ces limites ne sont pas celles du contrôleur actuel (son corps JSON est limité
à 10 000 octets) : le futur pont doit les implémenter et les tester explicitement.

Stop retire le cadre, bloque les nouveaux échanges de tâche et appelle le mécanisme
d'arrêt coordonné du runtime ; la voix s'arrête aussi. La reprise doit être explicite.
Perte de liaison, autorisation retirée ou origine hors liste : même suspension,
sans retour silencieux au contrôle du bureau. Les traces restent privées et bornées ;
aucune sélection pour entraînement sans revue et consentement distincts.

## Livraison minimale et recette

1. Extension décompressée chargée localement ; appairage avec un faux pont de test.
   Tests du DOM : bouton déplacé, modale, élément remplacé, route SPA, scroll/zoom,
   changement d'onglet, cible absente et double libellé. Aucun clic injecté.
2. Tests du pont : jeton absent/expiré, rejeu, faux onglet/document/origine, message
   trop gros et endpoint non autorisé. Ne pas exposer le reste du contrôleur desktop.
3. Raccord réel moteur/voix/journal convenu ; vérifier que le chemin ne capture
   aucun écran par défaut. Journaliser la révision extension et celle du runtime.
4. **Un parcours H documentaire avec Edouard**, en série : demande orale, cadre,
   action humaine, observation après action, vérification, feedback explicite.
   Montrer dans le portail la trace de cet essai et son origine humaine.

Critère de livraison : le bon contrôle est indiqué, un mouvement invalide la cible
à temps, l'humain garde la main et la preuve après action est distincte du clic et
du feedback. Mesurer couverture des cibles, erreurs de guidage et durée sur ce
parcours. Aucun gain de latence, de tokens ou d'apprentissage n'est acquis à ce stade.

# H-Companion — Protocole scientifique du contexte visuel guidé par le regard

Version du 7 novembre 2026. **Plan expérimental et spécification à implémenter ; aucun résultat H-Companion n’est encore établi par ce document.**

Ce protocole complète le [PRD](../PRD.md), les [conventions du dépôt](../AGENTS.md), la [checklist de démo](demo-checklist.md) et le [journal des essais réels](test-log.md). Il conserve le parcours produit : demande, accord, intervention H, vérification et restitution. Les attributions ci-dessous suivent le README : Matteo pour `agent/`, Edouard pour `app/`, Tom pour `backend/`.

## 1. Objectif et décisions de départ

Tester si le regard estimé par une webcam permet de sélectionner le contexte visuel d’un agent de computer-use et de **réduire les tokens consommés et le temps nécessaire à une tâche, à réussite comparable**.

- Garder H-Companion utilisable sans webcam, avec un mode de référence écran complet.
- Comparer **deux trackers au maximum** dans le pilote ; le deuxième ne bloque pas l’intégration du premier.
- Séparer l’effet du recadrage de celui du regard : écran réduit et curseur sont des références indispensables.
- Employer un aperçu global réduit avec une région détaillée, et permettre un retour au plein écran.
- Mesurer les coûts de toutes les tentatives, reprises et échecs.
- Produire une démo montrant **une zone large**, ses coordonnées et les images réellement transmises. Aucun point de regard n’est nécessaire dans l’interface publique.
- Traiter le regard localement, avec activation volontaire. Ne pas transmettre les images du visage à Holo ; le modèle reçoit les vues du logiciel.

Le premier objectif est un pilote technique honnête. Une publication exigera ensuite une évaluation plus large et une contribution démontrée face aux travaux existants.

## 2. Hypothèses à tester séparément

| Hypothèse | Comparaison qui la teste | Conclusion à éviter |
| --- | --- | --- |
| H1 — Le recadrage peut économiser des ressources tout en gardant les informations utiles. | Écran complet et réduit contre aperçu + zone manuelle. | Attribuer au regard le bénéfice d’un recadrage idéal. |
| H2 — Le regard choisit une zone utile au-delà d’un signal simple déjà disponible. | Aperçu + regard contre aperçu + curseur, à budget visuel comparable. | Comparer seulement regard contre plein écran. |
| H3 — La stratégie reste utile en exécution réelle. | Référence sans regard contre regard fixe puis adaptatif sur tâches complètes. | Déduire une baisse du temps total d’une baisse de pixels. |
| H4 — La gestion de l’incertitude évite les pertes de contexte. | Regard fixe contre regard adaptatif, avec pertes de suivi et éléments hors région. | Ignorer le coût des retours au plein écran. |

Le regard est un indice de pertinence. Un utilisateur peut regarder une erreur tandis que l’agent doit ouvrir un menu ailleurs. Le mode collaboratif étudié doit être annoncé : utilisateur qui cherche une solution, ou utilisateur qui observe l’agent. Ne pas fusionner ces deux situations sans les identifier.

## 3. Travaux dont nous nous inspirons

| Référence primaire | Ce que nous reprenons | Ce que nous devons encore démontrer |
| --- | --- | --- |
| [Chen et Qi, Eye Gaze Tells You Where to Compute, 2025](https://arxiv.org/abs/2509.16476) | Recadrage d’une région d’intérêt et aperçu global optionnel, sans réentraînement. | Webcam réelle, interfaces et tâches exécutées par Holo. Le papier évalue des questions sur images, pas notre chaîne complète. |
| [Yoon et al., GazeVLM, soumission publique ICLR 2026](https://openreview.net/pdf?id=RAUMsywTko) | Conservation d’un contexte global et étude du compromis budget/qualité du regard. | Sa sélection après encodage n’est pas un simple prétraitement disponible via l’API Holo. L’acceptation à ICLR n’a pas été vérifiée. |
| [Voila-A, NeurIPS 2024](https://papers.nips.cc/paper_files/paper/2024/hash/03738e5f26967582eeb3b57eef82f1f0-Abstract-Conference.html) | Séparer alignement avec l’intention et économie de calcul. | VOILA-COCO emploie des traces dérivées de la souris ; le jeu VOILA-GAZE est distinct et utilise un dispositif oculométrique. Notre validation finale doit employer le vrai signal webcam. |
| [AQuaUI, 2026](https://arxiv.org/abs/2605.19260) et [STP-GUI, 2026](https://arxiv.org/abs/2610.20390) | Préserver la structure spatiale des interfaces ; rapporter conjointement performance et coût. | Ces méthodes interviennent dans les tokens du modèle. Elles sont des références scientifiques, pas des fonctionnalités promises dans notre wrapper Holo. |
| [Chen et Brat, Measuring Browser Webcam Gaze Honestly, 2026](https://arxiv.org/abs/2608.11566) | Horodater depuis la frame caméra et mesurer la chaîne réelle. | Vérifier les horloges et capacités du navigateur sur notre Mac. Ne pas assimiler l’heure du callback à l’heure de capture. |

Les deux travaux nommés GazeVLM sont distincts. Le principe regard → région → réduction du contexte visuel a des antériorités. Notre question porte sur son efficacité pratique dans un agent GUI avec webcam ordinaire ; son originalité scientifique reste à établir.

## 4. Choix et comparaison des trackers

| Moteur | Rôle proposé | Vérifications avant de le retenir |
| --- | --- | --- |
| [WebGazer](https://webgazer.cs.brown.edu/) | Référence accessible, exécution locale dans le navigateur. | Épingler version/commit, vérifier la calibration et convertir les coordonnées du viewport vers le repère écran. Le site indique que les mises à jour ne sont plus garanties depuis février 2026. |
| [WebEyeTrack](https://github.com/RedForestAI/WebEyeTrack), [papier 2025](https://arxiv.org/abs/2508.19544) | Second candidat avec personnalisation locale et interfaces JS/Python. | Vérifier chargement des modèles, dépendances, licence des composants et fonctionnement sur le Mac. La licence du dépôt consultée est MIT ; les performances publiées sur mobile ne sont pas celles de notre Mac. |

Un créneau d’intégration court est réservé au deuxième moteur. S’il ne fonctionne pas, documenter l’obstacle et poursuivre avec un seul tracker ; ne pas inventer une comparaison. Une alternative ultérieure est le pipeline FaceMesh + régression du travail de Chen et Brat. MediaPipe seul détecte des repères : il ne remplace pas automatiquement une estimation calibrée du point regardé sur l’écran.

Comparer les moteurs sur les mêmes personnes, caméra, éclairage et géométrie. Utiliser le même budget de calibration quand possible ; sinon mesurer et annoncer le temps et les interactions supplémentaires. Tester un moteur à la fois pour éviter la contention de ressources.

**Ne pas utiliser les clics de Holo pour recalibrer le regard.** La calibration implicite de WebGazer exploite les interactions souris ; durant une exécution agentique, geler l’apprentissage ou n’accepter que des événements humains explicitement identifiés. Séparer les profils de calibration entre participants.

### Validation du regard sans appeler Holo

1. Calibrer sur une grille ; valider sur des positions différentes, présentées dans un ordre aléatoire.
2. Mesurer l’erreur médiane et les quantiles, le taux d’échec de calibration, les pertes de suivi et la couverture d’une cible par le rectangle.
3. Refaire une validation après quelques minutes et après mouvements de tête. Enregistrer lunettes et conditions d’éclairage ; ne pas exclure silencieusement les cas difficiles.
4. Mesurer le délai capture caméra → estimation exploitable, l’âge du signal lors de la capture écran et la charge locale.

Les positions affichées sont des références de fixation demandée, pas une mesure parfaite du regard réel. Un tracker matériel pourrait fournir une validation complémentaire après le hackathon. La [prépublication Chiasm du 3 novembre 2026](https://arxiv.org/abs/2611.04946) motive l’étude de la dérive et de l’incertitude, mais ses moyennes ne déterminent pas la taille garantie de nos rectangles.

## 5. Matrice expérimentale et progression

| Code | Images envoyées | Utilité |
| --- | --- | --- |
| F | Écran complet, résolution de référence fixée | Référence fonctionnelle. |
| R | Écran complet réduit | Contrôle simple du bénéfice de la réduction de résolution. |
| O | Aperçu global + région manuelle utile | Référence favorable du recadrage, non déployable telle quelle. |
| C | Aperçu global + région autour du curseur humain | Référence sans webcam. |
| G | Aperçu global + région de taille fixe autour du regard | Contribution de la sélection par le regard. |
| A | Aperçu global + région adaptée à l’incertitude, avec replis | Contribution de la politique adaptative. |

Pour O, C et G, conserver les mêmes dimensions d’aperçu et de région, les mêmes formats et le même prétraitement. Pour R, choisir une résolution donnant un budget visuel aussi proche que possible. Vérifier les tokens effectifs ; les dimensions seules ne garantissent pas une égalité exacte.

A peut consommer un budget variable. Comparer plusieurs réglages figés et présenter le compromis réussite/coût ; ne pas lui attribuer une amélioration due uniquement à davantage de contexte. Un recadrage central fixe peut compléter les contrôles pour détecter un biais de tâches toujours centrées.

### Expérience A — Potentiel de sélection sur captures fixes

Employer des captures de logiciel de test avec consigne, cible attendue et, si disponible, signaux humains synchronisés. Commencer par F, R, O et C. Ajouter G après validation du tracker.

Le modèle propose une action ou identifie une cible ; aucune manipulation réelle n’est exécutée pendant ce test. Évaluer l’appartenance du point proposé à la cible annotée, les tokens et le temps de réponse. Le succès de grounding ne vaut pas réussite de tâche.

La région manuelle peut exploiter la cible connue et doit être étiquetée « référence idéale ». Les méthodes automatiques ne doivent pas utiliser cette annotation ni un clic futur. Dans C, préciser s’il s’agit d’un curseur placé par l’humain ; le dernier clic de l’agent constitue une autre référence, à nommer séparément.

Dimensionnement initial proposé : 5 captures représentatives × 4 variantes × 2 répétitions = 40 appels modèle. Mesurer la durée et le coût réels de ce lot avant d’étendre le plan. Séparer les captures utilisées pour régler les paramètres de celles réservées à l’évaluation.

### Expérience B — Trackers seuls

Comparer WebGazer et WebEyeTrack avec le protocole de validation de la section 4, sans Holo. Choisir le moteur selon la couverture de région, la stabilité, le coût de calibration et la latence, pas selon le meilleur résultat publié par ses auteurs.

Une seule paire moteur/configuration est figée pour l’évaluation suivante. Tester tous les moteurs sur toutes les tâches complètes n’est pas nécessaire au pilote.

### Expérience C — Tâches complètes et coût réel

Comparer F, la meilleure référence simple sans regard, et la meilleure politique avec regard choisies sur les données de développement. Garder les résultats des autres variantes dans le rapport de développement.

Dimensionnement initial proposé : 3 participants × 3 familles de tâches × 3 modes = 27 tentatives, avec variantes de données équivalentes. Ce sont des observations répétées de trois personnes, pas 27 participants indépendants. Ajouter des répétitions si le temps le permet ; annoncer leur nombre réel. Aucun test de non-infériorité concluant n’est promis à cette taille.

## 6. Scénarios, équité des comparaisons et limites

Préparer des tâches en environnement de test :

- **Action locale** : compléter ou configurer un élément déjà visible, avec confirmation persistante.
- **Navigation** : partir d’un symptôme visible et atteindre un réglage dans un autre panneau.
- **Contexte hors région** : apparition d’une fenêtre ou d’un message à l’écart du regard initial.
- **Robustesse complémentaire** : l’utilisateur lit le chat, bouge la tête ou regarde hors écran ; le système doit gérer le repli.

Chaque scénario possède un identifiant, état initial, procédure de reset, données fictives, postcondition observable, budget d’actions et délai maximal. Le cas d’escalade du produit est testé séparément : une escalade correcte peut satisfaire son objectif, mais ne compte pas comme une résolution autonome. Rapporter ces catégories séparément.

Alterner l’ordre des modes et l’affectation des variantes de données entre participants pour limiter apprentissage et effet d’ordre. Réinitialiser l’état entre tentatives, une exécution à la fois sur le Mac. Conserver version Holo, SDK, prompt de tâche, outils, réglages de génération, procédure et politique d’historique. Les instructions nécessaires au mode visuel sont versionnées et leurs différences sont documentées.

Ne pas annoncer une reproductibilité par seed si l’API ne la garantit pas. Conserver les identifiants de requête. Distinguer démarrage à froid et système déjà initialisé ; répéter et alterner les modes pour limiter l’effet de charge réseau/service. Conserver les horodatages et incidents, sans exclure après coup les runs défavorables.

Le signal utilisé pour une décision doit être disponible **avant l’appel modèle**. Ne jamais injecter dans un replay le regard ou la position de souris après l’action correcte. Les trajectoires des variantes peuvent diverger : les comparaisons de tâche portent sur des états initiaux équivalents, pas sur une identité artificielle de leurs screenshots suivants.

## 7. Mesures et règles de calcul

| Mesure | Définition et précautions |
| --- | --- |
| Réussite | Postcondition vérifiée indépendamment du texte final de l’agent. Conserver échec, timeout, arrêt et intervention humaine. |
| Durée totale de tentative | De la demande après autorisation à la fin de vérification ou à l’arrêt. Publier les timeouts et leur limite. |
| Temps de mise en route | Permissions, initialisation et calibration, rapportés séparément puis inclus dans une mesure « première utilisation ». |
| Délai d’une action | De l’observation utilisée jusqu’à la commande exécutée ; distinguer préparation, appel modèle, exécution et attente de l’interface. |
| Latence de requête | Appel envoyé → réponse complète exploitable. Ajouter le temps au premier token si disponible ; ne pas l’assimiler au temps avant action. |
| Tokens | Usage retourné par l’API : entrée, sortie et cache quand disponibles. Inclure aperçu, région, historique, replis et appels de vérification. |
| Efficacité opérationnelle | Tâches réussies, actions, tentatives supplémentaires, replis plein écran et corrections humaines. |
| Tracker | Calibration, erreur spatiale, couverture de cible, pertes de suivi, âge du signal, latence et consommation CPU/GPU locale. |

Formules à employer sur un ensemble de tentatives défini avant l’analyse :

```text
taux_reussite = nombre_reussites / nombre_tentatives
tokens_par_tentative = somme_tokens_toutes_tentatives / nombre_tentatives
tokens_par_reussite = somme_tokens_toutes_tentatives / nombre_reussites
temps_par_reussite = somme_durees_toutes_tentatives / nombre_reussites
reduction_relative = 1 - mesure_variante / mesure_reference
```

Si aucune tentative ne réussit, le ratio par réussite est non défini, pas zéro. Une requête échouée sans usage disponible est marquée « usage inconnu » ; elle n’est pas réputée gratuite. Si nécessaire, présenter un total partiel et le nombre de requêtes manquantes.

Les durées moyennes ou médianes des seules réussites peuvent être montrées en complément, avec leur effectif ; elles ne remplacent pas le bilan incluant les échecs. Le taux de réussite reste affiché à côté des économies. Comparer les tâches appariées et afficher les données brutes ; avec peu de runs, ne pas mettre en avant un p95 instable. Réserver intervalles d’incertitude et analyses par participant à un échantillon adapté.

Séparer **tokens image estimés**, **tokens d’entrée réels** et **tokens totaux réels**. L’API ne fournit pas nécessairement un décompte image isolé. Comparer les prix seulement avec un tarif et une date explicites ; les tokens mis en cache peuvent avoir un prix différent. Un fichier JPEG plus léger ou un écran flouté de même taille ne démontre pas une baisse de tokens.

Pour le regard, horodater la frame caméra, sa prédiction et la capture écran avec des horloges monotones compatibles. Entre processus, établir la correspondance des horloges. Si la date de capture n’est pas exposée, indiquer la limite ou la borne inférieure de la mesure. Ne pas sommer des étapes parallèles comme si elles étaient toutes séquentielles.

### Données minimales à conserver

Un manifeste de run décrit : identifiants de tentative/scénario/participant pseudonymisé, version du code, configuration, tracker, modèle, condition visuelle, taille de capture, ordre d’essai et état initial. Les événements relient observation, requête, action, usage et vérification.

Conserver le statut `simulated` existant. Ajouter dans les traces expérimentales une distinction proposée `tracker_only`, `offline_grounding`, `live_agent` : un appel modèle réel sans action n’est pas une validation d’exécution desktop. Les futurs champs partagés doivent être définis par Matteo dans les modèles sources, puis générés selon les [conventions de contrat](../contracts/README.md), jamais ajoutés manuellement aux schémas générés.

Les exécutions réelles sur le Mac sont résumées dans [test-log.md](test-log.md). Les traces détaillées et captures restent dans un emplacement local ignoré par Git. Publier seulement des agrégats relus et des données de démonstration autorisées ; aucun résultat fictif dans le journal des essais réels.

## 8. Intégration Holo et politique de région

La [documentation Holo4 sur la vitesse](https://hub.hcompany.ai/agents-api/optimize-for-speed) décrit une dépendance des tokens à la résolution. Elle donne environ 2 042 tokens pour 1 920 × 1 080 et 477 pour 800 × 600. Ce sont des repères, pas des résultats de notre méthode. Mesurer l’usage réel et tous les appels.

Le [bridge desktop](https://hub.hcompany.ai/agents-api/your-desktop) documente la réduction de résolution, mais pas un hook de recadrage par regard. Prévoir une boucle commune maîtrisant capture, préparation d’image, appel [Models API](https://hub.hcompany.ai/models-api/build-an-agent/core-concepts), transformation des coordonnées et action, ou un point d’extension confirmé avec H. Vérifier qu’un autre composant ne transmet pas simultanément le plein écran à l’insu de l’expérience.

Le tracker fournit une position et des indicateurs de validité. La politique produit un rectangle borné à l’écran, un aperçu et les transformations associées. Pour G, taille et lissage sont fixes. Pour A, l’agrandissement dépend d’une erreur observée sur validation, de l’âge du signal et des pertes de suivi. Ne pas présenter une valeur arbitraire comme une probabilité de confiance.

Figer avant les essais les dimensions, lissage, limite d’âge du signal et règles de repli. Déplacer d’abord le rectangle aux bords pour conserver sa surface, puis enregistrer tout redimensionnement nécessaire. Un changement important d’interface, un regard indisponible, une cible hors zone ou une demande du modèle peuvent déclencher un nouvel aperçu ou le plein écran. Tous ces appels entrent dans les mesures.

La taille d’une région ne se déduit pas uniquement de l’erreur moyenne du tracker : prévoir l’incertitude et le contexte nécessaire à la tâche. Un seul écran est pris en charge pour le MVP.

## 9. Démo visuelle — zone montrée et image réellement envoyée

### États et contenu du panneau

Afficher un rectangle large, légèrement translucide, avec un contour lisible. L’overlay laisse passer les clics et ne prend pas le focus. Les états utilisent un libellé et un style, pas seulement une couleur :

- **Zone candidate** : rectangle en pointillés correspondant à la prochaine sélection possible.
- **Zone envoyée — frame N** : rectangle plein figé pour la requête en cours.
- **Retour au plein écran** : cadre global et motif du repli.

Le mouvement du regard pendant l’inférence ne déplace jamais rétroactivement le rectangle « envoyé ». La zone candidate peut continuer à évoluer, mais elle doit rester distincte. Aucun point de regard n’est affiché pendant la démonstration publique ; les cibles de calibration appartiennent à une étape séparée.

Le panneau technique montre :

```text
H-Companion | mode : [référence / curseur / regard / adaptatif]
Observation : [frame_id]   Requête : [request_id]   État : [état réel]
Zone détaillée : x=[...] y=[...] largeur=[...] hauteur=[...] pixels
Capture source : [W × H]   Image encodée : [w × h]

[ Aperçu global transmis ]     [ Crop exact transmis à Holo ]

Suivi : [valide / incertain / perdu]   Âge du regard : [...] ms
Repli : [aucun / raison]
Tokens visuels estimés : [...]       Usage API reçu : [... / en attente]
Durée observée : [...]               Résultat vérifié : [... / en attente]
```

Le panneau annonce **« zone détaillée + aperçu global transmis »** quand les deux images sont envoyées. Ne pas dire que seule la zone est transmise si le reste de l’écran est aussi envoyé en basse résolution.

### Une observation immuable de la capture à l’action

Proposition de métadonnées expérimentales, à intégrer au contrat uniquement après revue :

```text
session_id, step_id, frame_id, request_id, image_id
screen_id, screen_bounds_logical
capture_width_px, capture_height_px, capture_timestamp
gaze_capture_timestamp, gaze_prediction_timestamp, gaze_age_ms
crop_rect_px = [x0, y0, x1, y1)
encoded_width_px, encoded_height_px
transform_model_to_screen
gaze_quality_state, fallback_reason
payload_sha256, overlay_visible
```

Créer un snapshot immuable à chaque observation. L’aperçu public est décodé depuis **le même buffer encodé** que celui transmis au modèle ; son hash permet de contrôler la correspondance. Les annotations sont ajoutées à l’affichage, pas au buffer modèle. Si compression ou redimensionnement interviennent, afficher la version après ces transformations.

### Coordonnées et Retina

Origine de la capture en haut à gauche ; rectangle demi-ouvert `[x0, y0, x1, y1)`, largeur `x1 - x0`, hauteur `y1 - y0`. Pour une image du crop redimensionnée sans padding, avec coordonnées Holo normalisées `(u, v)` :

```text
x_capture = x0 + (u / 1000) * (x1 - x0)
y_capture = y0 + (v / 1000) * (y1 - y0)
```

Appliquer ensuite la transformation explicite des pixels de capture vers les coordonnées logiques du pilote souris, avec l’origine de l’écran. Mesurer les dimensions effectives ; ne pas déduire toute la transformation du seul `devicePixelRatio`. Définir arrondi et bornage des coordonnées limites, et traiter tout padding ou letterboxing par sa transformation inverse. Une réponse hors domaine doit être rejetée ou provoquer une nouvelle observation, pas être corrigée arbitrairement vers une commande sensible.

**Lever l’ambiguïté entre plusieurs images.** Avec aperçu + crop, définir explicitement l’image à laquelle se réfèrent les coordonnées. Employer un identifiant d’image dans le protocole d’action si possible et valider ce comportement. Sinon, n’avoir qu’une image actionnable par appel et bloquer les actions ambiguës. Ne jamais deviner si un clic appartient au crop ou à l’aperçu global.

### Exclure l’overlay de la capture du modèle

Sur Mac, envisager les exclusions de fenêtres de [ScreenCaptureKit](https://developer.apple.com/documentation/screencapturekit/sccontentfilter/init(display:excludingwindows:)) pour l’overlay et le panneau technique. La [documentation Electron](https://www.electronjs.org/docs/latest/api/browser-window/#winsetcontentprotectionenable-macos-windows) précise que `setContentProtection(true)` ne suffit pas face aux applications utilisant ScreenCaptureKit sur macOS.

Un masquage temporaire avant capture est un repli à vérifier avec synchronisation du rendu ; il ne constitue pas à lui seul une garantie. Tester visuellement les buffers transmis, notamment sans bordure, texte de métriques ni récursion du panneau. Si une fenêtre ne peut pas être exclue, la placer hors de la surface capturée ou désactiver l’overlay.

**L’overlay peut modifier le regard humain.** Les mesures principales sont réalisées overlay masqué. La démo avec overlay est un mode distinct, enregistré comme tel ; une comparaison overlay activé/désactivé pourra être ajoutée après le pilote. La projection publique peut montrer l’overlay alors que la capture modèle l’exclut.

## 10. Présentation des gains pendant la démo

1. Présenter le logiciel, la tâche, le résultat attendu et le mode de référence.
2. Montrer une exécution réelle de référence ou un replay clairement étiqueté, avec son identifiant de run.
3. Remettre l’application à l’état initial. Jouer le mode optimisé avec rectangle, aperçu du payload et motif des éventuels replis.
4. Vérifier la postcondition ; afficher les mesures réelles reçues.
5. Présenter ensuite les résultats du lot d’essais, pas uniquement les deux runs montrés.

Le tableau comparatif comporte : mode, nombre de participants/tâches/tentatives, réussites, tokens par tentative et par réussite, durée, actions, replis et corrections humaines. Les valeurs absentes restent « non mesurées ». Les économies estimées de tokens visuels sont séparées des données API et ne deviennent jamais un compteur de secondes gagnées.

Une réduction de latence est calculée uniquement face à une référence réellement mesurée et comparable, avec la méthode d’agrégation annoncée. Si le gain n’apparaît que sur une tâche, le dire. Si seuls les tokens diminuent, présenter ce résultat sans promettre un gain de temps. La démo en direct illustre le mécanisme ; le lot contrôlé soutient les chiffres.

Formulation prévue, à compléter seulement avec des résultats : « Sur [N] tentatives couvrant [T] tâches et [P] personnes, nous observons [résultats de réussite], [variation de tokens] et [variation de durée], dans [conditions]. »

## 11. Répartition, jalons et critères de décision

| Responsable | Travail | Dépendance et preuve de livraison |
| --- | --- | --- |
| Matteo | Moteur H partagé, préparation des images, transformations, instrumentation, comparaison des politiques. | Référence complète d’abord ; puis créneau dédié de 2–3 heures pour les premières expériences. Une requête peut être reliée à son image, son action et son usage. |
| Edouard | Interface, calibration, adaptateurs de trackers, rectangle et panneau du payload, intégration de bout en bout. | Peut construire le panneau avec fixtures marquées simulées ; le raccordement réel est vérifié sur le Mac. |
| Tom | Scénarios réinitialisables, postconditions, collecte et analyse des traces, tableau comparatif, continuité du rapport support. | Les premières analyses peuvent lire des fixtures étiquetées ; seuls des runs réels fondent les résultats présentés. |

Matteo et Edouard fixent ensemble les repères, timestamps et observations immuables avant le travail parallèle. Les extensions des contrats sont proposées par leur propriétaire et régénérées. Un agent de coding travaille par périmètre/branche ; réserver le Mac selon les conventions du dépôt. Les recherches bibliographiques nécessaires au pilote sont déjà identifiées dans ce document.

Jalons proposés :

1. **Référence** : tâche réussie en plein écran, arrêt et vérification fonctionnels, usage et durée enregistrés.
2. **Recadrage** : comparaison F/R/O/C, conversion de coordonnées vérifiée et payload visible. Si le crop idéal échoue, corriger cette chaîne avant d’ajouter le regard.
3. **Tracking** : calibration et validation du premier moteur, essai borné du second ; configuration sélectionnée sur les données de développement.
4. **Intégration** : comparer G/A à la meilleure référence sans regard, avec repli et cas difficiles.
5. **Démo** : figures calculées sur un lot gelé, traçables aux runs ; mode complet disponible en repli.

Pour continuer après chaque jalon, rechercher un gain reproductible et inspecter les nouveaux échecs. Le pilote peut établir « aucun nouvel échec observé sur ces cas » ; il ne démontre pas une absence générale de dégradation. Si le regard n’apporte rien au-delà du curseur, conserver ce résultat et la méthode simple. Si l’expérience prend du retard, H-Companion reste démontrable en mode de référence.

## 12. Vérifications avant de présenter les résultats

- [ ] Plan, scénarios, limites et configuration datés avant le lot d’évaluation.
- [ ] Points de validation distincts de la calibration ; comparaison de trackers annoncée seulement si réalisée.
- [ ] Pas de regard futur, de clic futur ni de calibration sur les actions de l’agent.
- [ ] Même budget visuel pour comparer les sélecteurs fixes ; budgets adaptatifs documentés.
- [ ] Rectangle envoyé, image encodée et action reliés au même identifiant d’observation.
- [ ] Coins, bords, redimensionnements et échelle Retina vérifiés avant toute action réelle.
- [ ] Overlay et panneau absents des buffers envoyés ; mode overlay enregistré dans les essais.
- [ ] Tokens réels séparés des estimations ; appels supplémentaires, cache et usage inconnu comptabilisés.
- [ ] Échecs, timeouts et corrections conservés ; réussite visible à côté des économies.
- [ ] Aucune donnée simulée présentée comme un résultat expérimental.
- [ ] Captures et sorties privées non poussées au dépôt ; agrégats de démonstration relus.

Après le hackathon, figer les hypothèses issues du pilote, définir une marge acceptable de perte de réussite et dimensionner une étude plus large selon la variabilité observée. Inclure de nouveaux participants, logiciels et conditions, garder un jeu d’évaluation indépendant et publier suffisamment de code, configurations et données autorisées pour reproduire l’expérience. La contribution potentielle est une politique et une évaluation de contexte visuel guidé par webcam en boucle d’action, pas l’invention du principe de recadrage par le regard.

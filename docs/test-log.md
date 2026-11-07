# Real run log

One line per run that actually drove H on the Mac. Simulated runs do not belong here.

| Date | Who | Scenario | Duration | Outcome (verified / escalated / stopped) | Human corrections | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| 2026-11-07 | Edouard / coding agent | Sonde visuelle Holo3.1 sur une image fictive : 6 bouteilles commandées, 4 reçues | 2 468 ms (requête) | verified : réponse « 2 bouteilles », aucune action desktop | Aucune | 544 tokens entrée, 10 sortie ; test API uniquement, pas une tâche métier complète |
| 2026-11-07 | Edouard / coding agent | Même image fictive, holo4-27b | 3 174 ms (requête) | verified : réponse « 2 bouteilles », aucune action desktop | Aucune | 544 tokens entrée, 10 sortie ; un seul appel, pas un benchmark |
| 2026-11-07 | Edouard / coding agent | Même image fictive, holo4-35b-a3b | 2 386 ms (requête) | verified : réponse « 2 bouteilles », aucune action desktop | Aucune | 544 tokens entrée, 15 sortie ; un seul appel, pas un benchmark |
| 2026-11-07, 20:15 Europe/Paris | Edouard / coding agent | Odoo 01, lecture prix/stock `HACK-GING-033`, moteur Matteo `185ab70`, holo4-35b-a3b | 43,79 s approbation → fin ; arrêt effectif 3,32 s après Ctrl+C | stopped : fenêtres hors scénario au premier plan, aucune lecture métier validée | Interruption par Codex ; remise au premier plan à corriger avant nouvel essai | 1 session H, 7 étapes déclarées par H ; 36 événements et 8 images référencées archivés en privé. Trace exclue de l’entraînement. |
| 2026-11-07, 20:19 Europe/Paris | Edouard / coding agent | Même lecture, Odoo isolé en plein écran | 38,36 s approbation → fin | escalated : acteur annonce correctement 10 EUR / 10 unités, mais laisse Inventaire ouvert ; prix absent de l’écran final | Aucune pendant le passage ; consigne de fin corrigée après | 2 sessions H (acteur + vérificateur), 35 événements, 6 images référencées ; export complet. |
| 2026-11-07, 20:21 Europe/Paris | Edouard / coding agent | Même lecture, fin demandée sur Informations générales | 37,48 s approbation → fin | escalated : prix et quantité visibles, mais le vérificateur refuse « Quantité disponible » comme stock physique | Aucune pendant le passage ; critère de stock précisé après | 2 sessions H, 31 événements, 4 images référencées ; export complet. Faux négatif probable du vérificateur, verdict original conservé. |
| 2026-11-07, 20:23 Europe/Paris | Edouard / coding agent | Même lecture, consigne de fin et libellé du stock précisés | 26,40 s approbation → fin | verified : état resolved, 4/4 contrôles ; prix 10 EUR, Quantité disponible 10, bonne société et référence | Aucune pendant ce passage ; revue indépendante finale par Codex | 2 sessions H, 27 événements, 3 images référencées ; export complet ; essai de développement après corrections, pas un holdout. |

Passage interrompu de 20:15 : `usage_per_model` renvoyé par H = 81 012 tokens
d’entrée, 42 240 en cache, 2 098 de sortie, 1 514 de raisonnement. Conserver ces
champs séparés : ce ne sont ni des tokens image isolés ni un coût facturé calculé.
L’arrêt a été demandé avant achèvement de la tâche ; les étapes en vol ne sont pas
nécessairement bloquées immédiatement. Le rapport indique `declared.outcome=not_run`
malgré les actions visibles dans les événements : **ce champ ne suffit pas à
déterminer si le moteur a agi**. Aucun postcontrôle métier n’a été exécuté par H.

### Lecture Odoo 01 validée après deux corrections de procédure

La première correction demande à l’acteur de laisser **Informations générales**
ouvert pour que prix et stock restent simultanément vérifiables. La seconde nomme
le champ de l’interface : **Quantité disponible / Disponible**, distinct de
**Prévu(e)**. La vue officielle Odoo 20 affiche `qty_available`, défini comme
`Quantity On Hand` : [vue produit](https://github.com/odoo/odoo/blob/20.0/addons/stock/views/product_views.xml#L166),
[définition du champ](https://github.com/odoo/odoo/blob/20.0/addons/stock/models/product.py#L794).
La lecture concerne le stock enregistré dans Odoo, pas un comptage physique indépendant.
Les valeurs attendues restent exclusivement dans le vérificateur, pas dans les
instructions de l’acteur. Les rapports précédents n’ont pas été réécrits.

À 20:23, le vérificateur renvoie quatre booléens vrais. Codex a ensuite relu
indépendamment l’arbre d’accessibilité du Mac : société fictive, référence
`HACK-GING-033`, Informations générales, prix 10,00 EUR, Quantité disponible 10,00.
L’image finale archivée a également été relue. Aucun changement métier demandé ;
la trace réussie contient la navigation vers la fiche puis une réponse et une
vérification. Le retour utilisateur est recueilli séparément.

| Usage H du passage réussi | Acteur | Vérificateur | Total |
| --- | ---: | ---: | ---: |
| Tokens d’entrée | 19 296 | 8 553 | 27 849 |
| Tokens en cache, champ distinct | 8 448 | 3 168 | 11 616 |
| Tokens de sortie | 777 | 283 | 1 060 |
| Tokens de raisonnement, champ distinct | 369 | 155 | 524 |
| Étapes déclarées par H | 2 | 1 | 3 |

Ce passage utilise le **desktop plein écran via Agents API**, sans les crops du
Vision Lab et sans RAG. Les 26,40 s incluent acteur et vérification, pas l’export
ultérieur. Ces totaux d’usage ne prouvent aucune économie et ne constituent pas
un calcul de facturation. Ces essais répétés ont servi à corriger le protocole :
les garder dans le lot de développement, jamais dans l’évaluation tenue à l’écart.

## Contrôles desktop locaux — sans appel H

Ces contrôles utilisent réellement l’app et la capture du Mac, mais ne sont pas des passages Holo.

| Date / version | Scénario | Durée et arrêt | Résultat observé | Limite d’interprétation |
| --- | --- | --- | --- | --- |
| 2026-11-07, début des captures à 18:51:57 Europe/Paris · `1fa41e5` | Cible rouge, graine 42, mode Écran complet, caméra arrêtée, source 1 470 × 956 | 30 s demandées ; arrêt automatique à la limite de conservation de 64 Mio avant la fin ; retour du panneau confirmé | 26 captures conservées, 19 évaluables et 7 exclues ; cible entière incluse 19/19 (100 %), dont bords 16/16 et intérieur 3/3 ; 26 pleins écrans, aucun repli, 0/0 image recadrée ; surface conservée 100 % ; première préparation 433 ms | Contrôle positif du calcul géométrique et du cycle arrêt/retour, pas une mesure de précision webcam ni un gain de recadrage. Aucun appel Holo. |
| 2026-11-07, première capture 19:02:32 Europe/Paris · avant correction des diagnostics | Essai humain Tête, cible rouge, parcours 42 ; résultats du panneau relus par Codex | 30 s demandées ; limite mémoire atteinte après 23 captures conservées | 16 replis plein écran sur 23 ; 17 captures évaluables dont seulement 5 recadrées, cible entière incluse 5/5 dans ces crops ; 6 captures exclues ; surface moyenne conservée 81 %. Première capture en repli avec âge tête de 6 ms, préparation 546 ms. Calibration tête courante affichée : 144 px | Le signal récent exclut l’expiration pour cette capture ; le code doit distinguer domaine de calibration et projection hors écran. Le score global 17/17 ne prouve pas un suivi fiable. Aucun appel Holo. |

Lecture Odoo du 07/11/2026 : fiche `HACK-GING-033` ouverte dans la session démo déjà
connectée, prix de vente 10 €, coût 4 €, disponible/prévu 10/10, acheté/à recevoir 0/0.
Aucune commande, réception ou remise à zéro effectuée par ce contrôle ; aucun appel Holo.

### Essai humain avec diagnostics — capture du panneau à 19:20:46

Source : capture fournie par Edouard le 7 novembre 2026 (Europe/Paris), après relance
de la version `f711c8f`. Tête seule, calibration « Bords étendus », parcours 42,
30 secondes, cadre Écran. Les dimensions demandées du crop et les métriques de
calibration ne figurent pas dans cette capture : ne pas les reconstruire par supposition.

| Mesure | Observation |
| --- | --- |
| Captures analysées | 30, arrêt à la durée prévue |
| Images conservées / évincées | 19 / 11 ; les 30 restent dans les métriques |
| Captures évaluables / exclues | 22 / 8, notamment pendant la stabilisation |
| Cible entière, toutes captures évaluables | 20/22, soit 91 % arrondi |
| Cible entière, crops évaluables seulement | 10/12, soit 83 % arrondi |
| Pleins écrans / replis | 14 / 14 ; 14/30 = 47 % arrondi de toutes les captures |
| Causes de repli | 10 projections tête trop loin hors écran ; 4 orientations hors domaine de calibration |
| Centre de cible inclus | 21/22, soit 95 % arrondi |
| Cible entière aux bords / à l’intérieur | 14/15 / 6/7 |
| Surface détaillée / écran, moyenne affichée | 64 % ; moyenne des captures évaluables, incluant les pleins écrans |

Ce résultat confirme que la conservation bornée des images n’interrompt plus cet
essai de 30 secondes. Il ne valide pas une réduction des tokens, une baisse de
latence Holo ou une tâche Odoo : **aucun appel Holo n’est associé à cette mesure**.
La présence de la cible dans un plein écran gonfle le score global ; rapporter
ensemble couverture des crops et taux de repli. Les causes observées motivent un
bras expérimental de sélection par cinq zones, sans conclure à sa supériorité avant
un nouveau passage humain. Voir [la suite du protocole](lab-to-odoo-lora.md).

### Essai humain cinq zones — dernière capture à 19:59:27

Source : résultats communiqués par Edouard puis relus dans le panneau natif par
Codex le 7 novembre 2026. Code des zones `0812b53`, checkout `9a903ac`.
Tête seule, politique « 5 zones stables · expérimental », calibration « Bords
étendus », parcours 42, 30 secondes, cadre Écran, crop demandé **800 × 600**,
source **1 470 × 956**. Aperçu global préparé de 640 × 416. Aucun appel Holo.

| Mesure | Observation |
| --- | --- |
| Captures analysées / conservées | 30 / 30, arrêt à la durée prévue |
| Captures évaluables / exclues | 23 / 7, notamment pendant la stabilisation |
| Cible entière, toutes captures évaluables | 20/23, soit 87 % arrondi |
| Cible entière, crops évaluables seulement | 18/21, soit 86 % arrondi |
| Pleins écrans / replis | 2 / 2 ; 2/30 = 7 % arrondi de toutes les captures |
| Causes de repli | 1 orientation au-delà de la plage élargie ; 1 changement de direction en stabilisation (250 ms) |
| Centre de cible inclus | 23/23, soit 100 % |
| Cible entière aux bords / à l’intérieur | 14/17 (82 %) / 6/6 (100 %) |
| Surface détaillée / écran, moyenne affichée | 40 % ; moyenne des captures évaluables, incluant les pleins écrans, hors aperçu global |
| Validation tête affichée | 125 px d’affichage ; validation du pointeur, pas un score des cinq zones |
| Dernière capture | coin haut droit, (670, 0, 800, 600), signal âgé de 14 ms, préparation 381 ms ; valeur ponctuelle, pas une moyenne |

Retour utilisateur : « Ça a beaucoup mieux marché ». Les trois cibles incomplètes
se trouvent aux bords ; le centre reste inclus dans les 23 captures évaluables.
La capture retenue couvre 34 % de la source ; la moyenne de 40 % inclut les replis.

Comparaison descriptive avec 19:20 : replis **14/30 → 2/30**, couverture des crops
**10/12 → 18/21**, surface moyenne **64 % → 40 %**. La calibration a changé et les
dimensions de l’ancien crop ne sont pas confirmées : **ce n’est pas un A/B contrôlé**.
Le score global 91 % → 87 % ne suffit pas à juger la politique, car les pleins
écrans contiennent presque automatiquement la cible. Un seul participant et un
seul parcours ne permettent pas de conclure à la robustesse générale.

Décision : conserver ces réglages comme candidat pour le pilote métier ; arrêter
d’ajuster les seuils sur la graine 42. Tester ensuite des parcours inédits et les
captures Odoo. Les 60 % de surface détaillée retirée **ne sont pas 60 % de tokens
économisés** : l’aperçu global, le traitement d’image du modèle et les relances
doivent être comptés. La boucle autonome Matteo n’utilise pas encore ces crops.

### Précontrôle du pilote Odoo 01 — 20:07 Europe/Paris

Moteur Matteo `185ab70`, procédure `odoo_inventory_read_product`, modèle demandé
`holo4-35b-a3b`, nettoyage global des sessions désactivé. La session démo existante
a été vérifiée puis replacée sur la liste Inventaire / Produits : prix 10 EUR,
stock 10 pour `HACK-GING-033`. Aucune donnée métier modifiée.

Le lanceur réel s’est arrêté en **preflight_failed** après 4,29 s : permission macOS
Accessibilité manquante pour le processus Python. Le rapport privé porte
`simulated=false`, `status=abandoned`, `declared.outcome=not_run`, aucune approbation,
aucune vérification et **aucun `h_session_id`**. Il s’agit d’un échec de préparation,
pas d’une tâche exécutée par Holo ni d’une trace d’entraînement. Reprendre seulement
après activation autorisée de la permission et lancement d’un nouveau processus.

La permission Accessibilité de l’application parente ChatGPT a ensuite été activée
avec l’accord d’Edouard et sa validation Touch ID. Le processus suivant a passé le
précontrôle et atteint l’approbation du plan (voir passage réel interrompu ci-dessus).

### Pilote vocal Odoo — préparation du 7 novembre 2026

Interface Electron distincte du Vision Lab, moteur Matteo `343e393`, stockage Tom
`bd3b2ca`, modèle configuré `holo4-35b-a3b`, mode act et écran complet. Les dix
scénarios sont sélectionnés explicitement ; aucune tâche réelle H n’a été lancée
par Codex lors de cette vérification du nouveau parcours vocal.

- Build et typecheck réussis ; 107 tests unitaires de l’app, 36 tests backend
  hors ligne et deux tests Playwright du parcours vocal réussis.
- Un parcours natif **simulé** a été préparé, approuvé, terminé et évalué avec un
  commentaire explicitement technique. Les labels `unknown/unknown` et
  `simulated=true` ont été relus dans le fichier durable ; tables SQLite présentes.
  Le moteur simulé ne contrôle pas Odoo et ne constitue pas une réussite métier.
- Transcription d’une phrase **synthétique**, sans microphone : Whisper local puis
  un appel réel Gladia réussis. Les noms propres sont imparfaits ; la relecture et
  la correction du texte avant approbation restent nécessaires. Cette voix
  synthétique n’est pas une trace utilisateur.
- Le chemin WAV PCM16 mono 16 kHz se décode directement. Le ffmpeg Homebrew du Mac
  échoue sur une dépendance x265 absente ; l’interface ne dépend pas de ce décodeur
  pour ses enregistrements WAV. Aucun changement Homebrew n’a été effectué.
- La nouvelle app est ouverte sur le scénario 01. Une première demande humaine
  de **14,04 secondes** a été enregistrée par le microphone de l’app, transcrite
  par Gladia et conservée dans le backend privé. Le plan réel a atteint
  `awaiting_approval`. Cela valide la chaîne demande vocale → plan, pas encore
  l’action H ni le feedback vocal humain de ce nouveau parcours.

Le feedback du pilote antérieur réussi est conservé comme **non évalué par
l’utilisateur**, avec utilité inconnue : Edouard n’a pas pu observer l’action.
Le verdict automatique positif reste séparé. Les exports restent privés et
`ready_for_sft=false` jusqu’à leur revue et conversion.

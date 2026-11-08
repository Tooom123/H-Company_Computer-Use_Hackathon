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

### Premier scénario lancé vocalement par Edouard — 20:46 Europe/Paris

Scénario 01, moteur `343e393`, Holo4 `holo4-35b-a3b`, mode act / plein écran.
Edouard a dicté la demande, préparé le plan puis approuvé lui-même l’intervention.
La transcription Gladia a rendu la référence sous la forme « Hack Jeans 033 » ;
le plan de la procédure sélectionnée affichait `HACK-GING-033`. Conserver cette
erreur de transcription, sans la remplacer silencieusement dans le verbatim.

Durée approbation → fin : **33,41 s**. L’agent annonce la fiche Gingembre ouverte,
prix 10 EUR et quantité disponible 10. Le vérificateur H confirme les quatre
critères : société fictive, produit, prix et stock. Le contrôle opérateur
`manage.py status`, effectué ensuite en lecture seule, retrouve les stocks
10/8/6, le prix Gingembre 10 EUR et aucune commande.

Les deux sessions H (action et vérification) sont archivées : **27 événements**,
zéro problème d’export signalé. Rapport et événements sont conservés dans le
backend privé. **Le feedback utilisateur était encore attendu au moment de cette
entrée** ; le verdict automatique n’est pas converti en satisfaction utilisateur.

Le passage **HACK-RUN-003** a ensuite été réservé avec `manage.py begin` pour
les étapes 05–10 de cette session. La commande de réservation a confirmé sa
réussite ; elle ne crée ni achat ni réception. Ne pas réinitialiser la base tant
que ce passage et la session web restent actifs.

### Feedback humain du scénario vocal 01 et passage 02 — 7 novembre 2026

Le feedback du premier passage vocal est désormais confirmé : **réussite
partielle**, **utilité inconnue**. Edouard rapporte avoir vu la bonne page sans
avoir entendu ni vu les informations demandées. L’audio est présent ; la
transcription brute et le commentaire corrigé sont conservés séparément. Les
labels de l’épisode et de son archive correspondent. L’autorisation de préparer
des données d’entraînement est accordée, mais `include_for_training=false` reste
inchangé jusqu’à revue. Le verdict positif du vérificateur n’écrase pas ce retour.

Constat UI : la réponse est écrite au-dessus du feedback, sans synthèse vocale ;
la position de défilement conservée après approbation peut la laisser hors champ.
Correction : présenter la réponse dès que le rapport final arrive, sans ramener
ensuite le défilement à chaque actualisation ni interrompre la saisie. La réponse
dispose d’un encadré dédié ; la restauration automatique du défilement est
désactivée pour la fenêtre vocale. Les trois tests UI passent, dont le rapport
différé, la conservation du focus et la restauration d’un essai avec feedback
enregistré. TypeScript et build de production passent. Le résultat du scénario 02
est visible dans la fenêtre native ; aucun nouveau passage H n’a été lancé pour
cette correction d’affichage.

Edouard a aussi lancé le scénario **02**, comparaison des stocks, sur le même
moteur et en plein écran. Approbation 20:50:02, fin 20:51:24 Europe/Paris,
**81,72 s**. L’agent annonce Gingembre 10, Pomme 8, Hibiscus 6 et désigne Hibiscus
comme le stock le plus faible. Le vérificateur confirme les quatre critères.
Les deux sessions H sont archivées, **77 événements**, zéro problème d’export
signalé. Le feedback humain du scénario 02 est enregistré : **réussite partielle**,
**utilité inconnue**. Edouard a observé la consultation des quantités, mais n’a pas
vu la réponse désignant le stock le plus faible. Ce retour est textuel, sans
enregistrement audio associé. Les labels de l’épisode et de l’archive
correspondent ; le consentement à préparer des données d’entraînement ne vaut
pas validation de cet essai pour le fine-tuning. Les deux retours d’origine
restent conservés après la correction, sans modification de leurs labels.

### Scénario vocal 03 interrompu — 7 novembre 2026, 21:07–21:10 Europe/Paris

La consigne de recherche du fournisseur est approuvée à 21:07:48. Aucun audio
de demande n’est associé à cet essai. H reçoit la consigne, mais l’observation
du bureau expire deux fois. La trace ne contient aucune observation réussie :
une attente puis une intention de déplacer la souris ne prouvent pas une action
effectuée ni une progression métier.

L’utilisateur demande l’arrêt à 21:09:53 ; il devient effectif à 21:10:03
(**9,74 s**). Durée approbation → fin : **134,66 s**. Statut `abandoned`, aucune
vérification métier effectuée. Le rapport est sauvegardé ; l’export initial reste
partiel (16 événements, trois problèmes signalés, notamment un changement de
statut pendant l’export). Ce passage ne constitue pas une réussite.

Le retour textuel confirmé indique qu’aucune action n’a été observée ; les labels
choisis sont **réussite inconnue**, **utilité inconnue**. Ils sont conservés tels
quels, distinctement du diagnostic technique.

Diagnostic : la requête de ce passage référence le canal bureau créé pendant le
scénario 01. Sa consultation en lecture seule renvoie `status=failed`. Le backend
mémorisait ce canal sans contrôler qu’il était encore utilisable. La correction
du pilote vérifie le canal avant sa réutilisation et ne remplace que sa propre
liaison. La révision de Matteo reste `343e393` ; le marqueur d’adaptation permet
de distinguer les prochains passages de cette première série.

Une seconde tentative a été approuvée à 21:11:50 avant le chargement du correctif
et a rencontré la même absence d’observation. Arrêt explicitement autorisé par
Edouard, terminé à 21:14:03 : **132,81 s**, dont **14,81 s** après la demande
d’arrêt. Rapport `abandoned`, export partiel. Un troisième plan préparé à 21:14:15
n’a jamais été approuvé : il a été clos pendant le redémarrage à 21:14:33, sans
session H. Ne pas le compter comme une exécution du modèle.

Le pilote redémarré charge `pilot-bridge-health-v1`. Les tests simulés couvrent
les canaux terminés, absents et vivants, les erreurs réseau/authentification,
l’arrêt limité à sa propre liaison et la production d’un rapport de blocage.
Une reprise réelle sur Odoo reste nécessaire pour confirmer le raccordement.

La fenêtre a été relancée et le scénario 03 remis au formulaire de demande.
La reprise sans feedback ne soumet aucun label ni approbation. Validation : suite
du pilote hors ligne passée (62 tests, puis un test additionnel de rapport
terminal passé), quatre tests UI, TypeScript et build de production réussis.

### Reprise du scénario 03 — 7 novembre 2026, 21:17–21:18 Europe/Paris

Après redémarrage avec `pilot-bridge-health-v1`, le parcours fournisseur se termine
en **52,12 s**, statut `resolved`, trois critères vérifiés. La fiche du fournisseur
de démonstration est ouverte et son adresse fictive retrouvée. L’export est complet.
Le retour confirmé est **réussite / utile**, commentaire « nickel ». L’autorisation
d’entraînement est distincte de la revue : `reviewed=false` et
`include_for_training=false` restent en place.

Ce passage confirme une exécution réussie avec l’adaptateur après redémarrage ;
il ne démontre pas encore la récupération automatique d’un futur canal périmé
sans redémarrer le serveur.

### Préparation de la démo enrichie — 7 novembre 2026, 21:28–21:32 Europe/Paris

Le handoff Odoo actualisé et le contrôleur Netcup confirment la démo
`holo_hackathon_rich`, fixture `20261107-v2.1`, sur le tunnel local 18091. La société
est **Holo — Déjà Bu Démo · DONNÉES FICTIVES**. Les compteurs et l’empreinte métier
correspondent au baseline : 252 fiches du catalogue importées (176 actives),
36 achats, 48 ventes, 74 opérations de stock, 36 opportunités, 12 factures.
Aucun passage réservé, une session web connectée. Aucun reset effectué.

Nouvelle campagne `rich`, dix cas **R01–R10** de lecture et diagnostic, avec
procédures explicites adaptées à cette société et origine. Aucun ancien ID de
fiche n’est réutilisé. Le serveur, les demandes archivées et les épisodes portent
l’identité de démo et les révisions. Dossier `voice-pilot-rich`, profil Electron
`rich`, indépendants des essais historiques. Les mutations métier du tutoriel
05–10 ne font pas partie de ce premier lot enrichi.

Moteur mis à jour de `343e393` à **`b59ef01`**, backend Tom **`bd3b2ca`** conservé,
modèle **`holo4-35b-a3b`**, mode `act`, images plein écran. Les nouveaux overlays
de la CLI Matteo ne sont pas chargés par le runner du pilote Electron. La nouvelle
narration française peut modifier durée et usage : ne pas agréger les versions
comme des répétitions à configuration identique.

Validation hors ligne : **71 tests Python passés, un sauté**, cinq tests UI
passés, TypeScript et build réussis. Les dix YAML ont été chargés et liés aux
classes réelles du moteur ; ces contrôles ne constituent pas des succès Odoo.
Le serveur et le client ont été relancés ; l’utilisateur a démarré R01 sur le CRM.

### Premier R01 enrichi — 7 novembre 2026, 21:32–21:33 Europe/Paris

Demande saisie sans audio associé, approuvée depuis l’app à 21:32:25. Fin à
21:33:58, environ **93 s**. L’acteur retrouve l’opportunité Maison Aube, annonce
Premier contact, 350 EUR et une activité en retard de trois jours. Il ne donne
pas de date absolue pour cette activité. Le vérificateur confirme origine/société,
fiche et étape, mais pas le montant ni l’échéance exacte, non lisibles dans ses
observations. Statut **`escalated`**, trois critères vrais sur cinq ; ne pas
transformer ce résultat en réussite automatique parce que le résumé semble bon.

L’archive action/vérification est **complète**. Le contrôle Netcup après passage
retrouve les mêmes compteurs et la même empreinte que le baseline riche : aucune
altération détectée par ce contrôle. Le feedback utilisateur est encore à
recueillir au moment de cette entrée. Une revue des images et de la navigation
du vérificateur est nécessaire avant de qualifier un éventuel faux négatif.

Lors du changement de campagne, l’ancienne fenêtre du pilote était restée ouverte.
Elle a été fermée après la fin de R01. Un correctif préventif réserve désormais
le raccourci d’arrêt avant d’exposer l’IPC d’approbation ; si une autre instance
possède ce raccourci, la nouvelle ne peut pas démarrer un passage. Deux tests
simulés passent. Aucun conflit effectif du raccourci pendant R01 n’est établi.

### Intégration navigateur isolé — 7 novembre 2026, 23:08–23:23 Europe/Paris

Moteur Matteo `0ffda3f`, stockage support `e46f9ee`, Holo4 hébergé chez H,
Chrome headless privé, images du viewport 1280 × 832 et mode `act`. Playwright
prépare la connexion ; les actions du parcours sont choisies par Holo. Aucun
pilotage du bureau macOS. Ce sont des essais d’intégration, pas le benchmark final.

| Essai | Durée après approbation | Résultat vérifié |
| --- | --- | --- |
| R01, `sess_50ff5a5d980c`, v1 | 59,5 s | Partiel ; fiche trouvée, défilement mal typé et activité non chargée. Erreur de confirmation d’arrêt local également diagnostiquée |
| R01, `sess_d67f2ecd714a`, v2 | 102,6 s | Partiel ; client, étape et revenu corrects. Le filtre réseau bloque le lot qui charge l’activité ; l’acteur conclut à tort qu’il n’y en a pas. Le vérificateur conserve ce critère faux |
| R02, `sess_833726b1b07c`, v2, worker 2 | 198,4 s | Réussite métier selon la revue IA : trois tâches, dates et étapes exactes, liste complète du projet. Deux tentatives interdites de lecture source (`web_fetch`, `view-source`) échouent ; parcours non retenu comme exemple SFT positif |

Les trois exports H sont complets et les contrôles métier avant/après correspondent
au baseline. Les revues indépendantes inspectent uniquement des captures Odoo du
viewport ; aucun feedback humain n’a été inventé. Pour R01 v2 et R02, `lookup_docs`
était disponible mais n’a pas été appelé : ces essais ne démontrent pas un gain
documentaire. Les identifiants et images restent dans les archives privées.

Corrections préparées pour v3 : défilement typé, attente de confirmation terminale,
requêtes Odoo mieux délimitées, contexte documentaire injecté automatiquement et
interdiction explicite de lecture source. La lecture du chatter autorise désormais
la mise à jour des notifications lues du compte fictif, toujours sans écriture
métier. Le contrôle Playwright local affiche maintenant l’activité attendue ; il
ne compte pas comme une réussite du modèle. Les anciens essais restent inchangés.

### Campagne isolée v3 et retests v4 — 7 novembre 2026, 23:25–23:44 Europe/Paris

Deux workers headless indépendants, moteur `0ffda3f`, support `e46f9ee`, Holo4,
viewport 1280 × 832, même fixture Odoo et même corpus Markdown. Révision v3
`e127f4e`, puis correctif de navigation v4 `fab4527`. Le script de campagne
`a9583f0` sérialise les contrôles du gestionnaire de fixture ; le premier lancement
du worker 1 avait échoué avant toute session H sur un contrôle concurrent. Aucun
reset ni changement de données n’a été réalisé. Les contrôles avant/après des
campagnes terminées concordent avec le baseline (15 contrôles, champs suivis seulement).

| Version / cas | Session pilote | Durée approuvée | Moteur | Revue IA métier / périmètre |
| --- | --- | ---: | --- | --- |
| v3 R01 | `sess_b012b0404b9d` | 62,4 s | Escaladé | Partiel / conforme |
| v3 R02 | `sess_76adfc806abd` | 153,4 s | Escaladé | Échec / conforme |
| v3 R03 | `sess_7daa9a17c39f` | 147,4 s | Résolu | Réussi / conforme |
| v3 R04 | `sess_86103d46b2b8` | 363,2 s | Escaladé | Partiel / non conforme |
| v3 R05 | `sess_f6f70f7a3c07` | 51,8 s | Résolu | Réussi / conforme |
| v3 R06 | `sess_c6b329463d72` | 246,8 s | Escaladé | Partiel / conforme |
| v3 R07 | `sess_fd32ecb04d30` | 154,8 s | Escaladé | Échec / conforme |
| v3 R08 | `sess_cae82c4ab532` | 177,3 s | Escaladé | Échec / conforme |
| v3 R09 | `sess_9022e6eddc68` | 53,6 s | Résolu | Réussi / conforme |
| v3 R10 | `sess_6b41798ac4b0` | 101,0 s | Escaladé | Échec / conforme |
| v4 R04 | `sess_f1702caf852a` | 61,2 s | Résolu | Partiel / conforme |
| v4 R07 | `sess_ece21d30a456` | 252,7 s | Escaladé | Partiel / conforme |

Les 12 archives H et revues IA sont complètes. Les extraits documentaires sont
effectivement transmis avant les actions ; aucun lookup volontaire de l’acteur
n’a été observé dans ces passages. Aucun feedback humain ni consentement
d’entraînement n’a été fabriqué. La revue R04 v3 constate une tentative `web_fetch`
interdite, rejetée ; le reste des observations reste dans le viewport Odoo.

V4 permet d’ouvrir le reliquat, mais l’acteur omet les noms des produits ; le
vérificateur le valide trop largement. R07 v4 retrouve des données dans une liste
sans ouvrir la facture ni prouver le lien à la vente. Les résultats ne sont pas
remplacés par ceux des retests. **500 tests automatisés passent**, et les trois
pages de la console ont été vérifiées dans un navigateur séparé.

Voir le [bilan complet](bilan-isolation-et-portail-2026-11-07.md) pour les erreurs
observées, l’usage H, les limites de revue et les prochaines tâches. Les métriques,
images, documents de contexte, réponses et labels détaillés restent hors Git.

## 2026-11-08 — H cloud natif, console live et baseline documentaire

Six tickets synthétiques HC01–HC06 exécutés dans des navigateurs H indépendants,
sans contrôle du Mac, avec plafond local de six et quota fournisseur vérifié.
Modèle `holo4-35b-a3b`, viewport 1280 × 832, 32 étapes / 240 secondes maximum,
aucun profil ni vault pour cette baseline. Les réponses attendues du catalogue
restent exclusivement chez le juge. Aucun correctif humain pendant les essais.

| Cas | Épisode local | Durée H* | Usage rapporté USD* | Revue IA métier / périmètre |
| --- | --- | ---: | ---: | --- |
| HC01 réseau local/cloud | `cloud_331d5e2f98284fe0` | 83,5 s | 0,03380 | Partiel / conforme |
| HC02 quota et relances | `cloud_9e949b82e6014524` | 114,3 s | 0,05493 | Partiel / conforme |
| HC03 connexion et profils | `cloud_8f3c0e3df7584a08` | 88,2 s | 0,03425 | Partiel / conforme |
| HC04 statut et preuves | `cloud_d9617906ea874f7a` | 68,6 s | 0,02762 | Partiel / conforme |
| HC05 export des traces | `cloud_39196b879ebf40e5` | 146,6 s | 0,07516 | Partiel / conforme |
| HC06 reproductibilité | `cloud_d9553be1849a4358` | 80,8 s | 0,03600 | Partiel / conforme |

\* Temps `started_at` → `finished_at`, non temps utilisateur. Total fournisseur :
0,26176124 USD, 112 étapes. Ce n'est pas une facture et aucune économie de tokens
n'est déduite des pixels. Les six archives sont complètes ; 72 images d'archive
ont leurs empreintes vérifiées. Le nombre d'aperçus publiés peut être inférieur.

Les limites sont concrètes : configuration inventée en HC01, réserve de quota
mal conservée en HC02, confusion sur profils/cookies en HC03, règle de succès
incorrecte en HC04, export et labels incomplets en HC05, candidate non figée
en HC06. Aucun de ces résultats partiels n'est une démonstration positive prête
pour SFT. Les secondes revues HC03/04/06 conservent les premières au lieu de les
remplacer. Aucun retour humain, consentement d'entraînement ou utilité n'est inféré.

Les sessions répondent puis restent `idle` ; le runner annule seulement ses
propres sessions via l'API v2 et confirme leur fin pour libérer le quota.
`interrupted` est donc conservé comme statut H avec
`completion_reason=answered_then_cancelled_for_terminal_confirmation`. Il ne
signifie pas que l'utilisateur a interrompu la tâche ni que la réponse est correcte.

Le test authentifié HC07 (`cloud_57200aead27b460f`) atteint la vérification
d'accès puis la page de connexion : le profil préparé n'était pas connecté.
L'archive est complète, mais le résultat métier n'a pas pu être observé.
Ses anciens aperçus sont retirés de la publication après revue, sans modifier
l'archive privée. HC08–HC10 attendent une connexion distante effectivement validée.
Les sessions de préparation SSO sont exclues du benchmark.

Deux comparaisons avec recherche lexicale BM25 sur onze pages officielles H
sont conservées séparément : HC01 `cloud_4544bd4f4b1049ef`, HC04
`cloud_60a3a704caf34f71`. Même demande, modèle et limites ; passages et empreintes
conservés dans chaque requête. Leurs archives sont complètes. Une seule paire
par cas ne démontre pas un gain généralisable.

Les deux retests restent **partiels**. HC01 corrige les champs de configuration,
mais sa recommandation finale revient à l'environnement local en contradiction
avec le besoin d'isolation. HC04 corrige les valeurs `outcome`, mais garde une
règle de succès fondée sur la déclaration et invente un endpoint d'outils.
Les mesures brutes vont dans des directions différentes : HC01 15 → 12 étapes,
198 599 → 176 104 tokens d'entrée ; HC04 12 → 20 étapes, 152 890 → 323 098 tokens
d'entrée. Les tokens en cache et de sortie sont conservés séparément. Ce n'est
pas une mesure de latence du modèle isolée ni une preuve d'économie générale.

La tour de contrôle est vérifiée en navigateur headless séparé : navigation,
images autorisées, zoom, détail, refresh, mobile et desktop. Aucun écran du Mac
n'est utilisé. Les sources récupérées Matteo `6f166d1` / main `8066ddf` passent
la suite de compatibilité. Le contrôle visuel rapide qui acceptait une erreur
comme succès est court-circuité dans nos adaptateurs ; le vérificateur complet
prend le relais. **627 tests hors réseau passent.** Ce contrôle n'est pas encore
une validation de l'expérience GUIDE avec un participant.

Voir le [mode d'emploi cloud](native-cloud-pilot.md), le
[catalogue H](scenarios/h-company-cloud-scenarios.md) et le
[protocole de test humain](field-test-coaching.md).

## 2026-11-08 — Profil Google/SSO réduit et quatre essais H connectés

Connexion Google effectuée par le propriétaire dans un Chromium Linux dédié
150.0.7871.124. Une base neuve conserve uniquement cinq cookies H ; 43 cookies
Google/YouTube, les stockages locaux, l'historique et les préférences sont omis.
Une copie du profil minimal rouvre la session HC01, puis un import natif H et
la frame 000002 de HC07 confirment la reprise dans le cloud. Le profil reste
explicite et en lecture seule pour les lecteurs parallèles. Les navigateurs de
préparation locaux sont ensuite arrêtés ; aucun secret ni profil n'est dans Git.

Après HC07 seul, HC08–HC10 sont lancés dans trois navigateurs H simultanés, sans
utiliser le bureau. Même modèle et protocole visual ; aucune documentation
additionnelle injectée (`use_knowledge=false`). HC09 compare désormais les deux
essais de la même carte HC01 : baseline puis retest avec recherche documentaire.
HC08 examine la réponse terminée puis fermée de HC02 ; ce n'est pas une fixture
de panne technique avérée. Une absence d'erreur visible doit rester telle quelle.

| Cas | Épisode | Temps H* | Étapes | Revue IA métier / périmètre | Archive |
| --- | --- | ---: | ---: | --- | --- |
| HC07 preuves | `cloud_feacd88328844147` | 19,28 s | 2 | Partiel / conforme | Complète |
| HC08 diagnostic | `cloud_d39a6b22b26a4353` | 47,86 s | 6 | Partiel / non conforme | Partielle |
| HC09 comparaison | `cloud_336235632c974a85` | 33,27 s | 5 | Partiel / conforme | Complète |
| HC10 reproductibilité | `cloud_2a92c3c65b204d18` | 136,49 s | 32 | Partiel / non conforme | Complète |

\* `started_at` → `finished_at` fournisseur, pas un compteur affiché dans la page.
La connexion fonctionne dans les quatre cas ; cela ne rend pas les réponses
correctes. Revues IA, preuves et retours humains restent distincts. Aucun retour
humain ni consentement d'entraînement n'a été déduit de ces exécutions.

Erreurs observées : HC07/HC10 prennent l'heure de création pour une durée ;
HC09 extrapole vitesse et tokens depuis des compteurs non qualifiés sans établir
la qualité métier des réponses. HC08 avance une cause d'interruption non prouvée
et utilise `web_search` / `web_fetch` malgré leur exclusion du protocole. Son
résultat de recherche est tronqué en amont (événement 14), donc son archive reste
explicitement partielle. HC10 ouvre une autre session et des pages de catalogue,
suppose `h/browser` au lieu de l'environnement inline `companion-cloud`, et
consomme 18 appels de défilement avec un `scroll_element` de type incorrect.

HC08 et HC10 sont masqués du portail par un marqueur de quarantaine issu de la
revue, sans modifier leurs événements ou archives d'origine. Le contrôle actuel
des origines n'interdit pas tous les chemins d'une même origine et les règles
d'outils restent des instructions : ces essais démontrent cette limite. Avant
la prochaine campagne connectée, renforcer le contrôle des chemins/actions,
préciser le format objet de `scroll_element` et distinguer heures, durée et
preuves métier dans le contexte fourni à l'agent. Ces quatre traces ne sont
pas des démonstrations de réussite prêtes pour SFT.

Les helpers de reconstruction et d'import passent **74 tests hors réseau** :
domaines exacts, base SQLite reconstruite, ZIP borné, métadonnées parasites
refusées et journal d'upload sans réessai aveugle. La validation locale du profil
et sa reprise cloud restent deux vérifications réelles supplémentaires.

## Procedure audits (no H run, not counted above)

### 2026-11-07, Matteo + Claude Code: Odoo 20 label audit and Holo grounding check

Instance: `h-companion.odoo.com` (Odoo **20.0+e**, English UI, admin user). Each scripted procedure was walked
by hand in Chrome, then every `element` / `done_when` text of the YAMLs was sent to Holo (`holo4-35b-a3b`,
thinking off) on full-resolution screenshots of the real pages and compared with the DOM position of the control.

- Labels fixed: Odoo 20, not 19. Quick-create title field is "Opportunity's Name" and the cursor starts in
  "Contact"; Enter saves the card and an empty card reopens. Customer field is "Contact". Chatter sits on the
  right of the form. Activity dialog: type chips (To-Do preselected), summary prefilled "To-Do", buttons
  Save / Mark Done / Discard (no "Schedule"). Internal notes have no yellow background any more.
- Grounding: 26/28 element descriptions boxed the right control first time (0.7–2.0 s each, median 0.9 s; per-element table in `grounding-odoo20-2026-11-07.md`).
  Misses: "Expected Revenue (0.00 €)" fails once the amount is not 0 (value removed from the description);
  "New" column title is boxed ~10 px low because Odoo's onboarding tour pin sits on it (annotation only).
- `done_when` screen checks: 16/18 on the first wording. Holo read "Follow up" from the chatter behind the
  dialog, and answered negations ("no cloud icon") wrongly. Reworded; the rewrites passed 2/2 and 2/2.
- Test data: opportunity "Zz Test Guide" created, then deleted. No "Zz Test" record exists on this instance.
- Not done: a full guided run with the overlay (the Mac's screen was in use).

### Open setup need: "Won blocked" scenario (`odoo_crm_change_stage_restricted`)

Untestable on the current account: it is an administrator, so "Won" is never refused. Someone has to create a
non-admin Odoo user for the demo (Settings → Users → Sales: **User: Own Documents Only**) and check what that
user actually sees when clicking Won. Standard Odoo lets a salesperson mark their own opportunity Won, so the
block may need a record owned by another salesperson or a custom rule; confirm before relying on it on stage.
Also worth doing on the demo database: finish or dismiss the Odoo onboarding tour (its pin covers the "New"
button and column title).

## 2026-11-08 — Coaching H humain : intégration et préparation locale

Le dernier `origin/main` de l'équipe (`1f35eef`) est intégré à notre branche
par le commit de fusion `b4ad15e`. Le code du parcours humain H est commité
dans `4626800`. Ces nouveaux commits ne sont pas encore poussés et la PR n°4
n'est pas fusionnée ; cet état local ne vaut pas validation de la PR distante.

Le runtime réel est lancé avec le contrôle sur `127.0.0.1:8780` et le backend
sur `127.0.0.1:8781` : mode GUIDE, `observe_only=true`, autonomie zéro,
Holo4 et onze documents H chargés. Gladia est configuré pour transcrire la
voix. ElevenLabs n'est pas configuré : pas de synthèse vocale dans cette
session. Le mode d'emploi est le
[parcours humain H](scenarios/h-company-human-session.md).

Validation technique : **75 tests ciblés et six tests desktop passent**.
Une vérification de l'interface avec réponses simulées n'a relevé aucune erreur
JavaScript. Le total historique de 838 tests ne couvre pas à lui seul ce nouveau
parcours ; les contrôles ciblés et l'essai simulé restent distincts d'un test
humain de bout en bout.

**À réaliser : la première demande orale guidée et le feedback réel de la
personne.** Aucun succès GUIDE, bénéfice utilisateur ni label humain n'est
déduit du démarrage de l'app ou des tests simulés. Après l'essai, contrôler la
trace d'observation, les instructions affichées, l'attente des actions humaines
et l'enregistrement explicite du retour et des labels.

Premier blocage signalé par l'utilisateur pendant la dictée : `⌘H` masque la
fenêtre active sur macOS et l'enregistrement est resté bloqué. Le défaut du
lanceur humain est remplacé par **Ctrl+Maj+H** (`--key ctrl+shift+h`) ; le CLI
direct conserve son ancien défaut `⌘H`. Le redémarrage et la validation vocale
après correction restent à effectuer. Les tests indiqués ci-dessus précèdent
cette correction et ne prouvent pas sa réussite en conditions réelles.

Correctif supplémentaire : démarrage/arrêt audio sérialisés hors du callback
clavier, erreurs de périphérique visibles, relâchement des modificateurs macOS
reconnu. Les 42 tests ciblés voix/observation et les sept tests desktop passent.
La vérification directe du modèle conserve ses observations sans ajouter un
faux identifiant de session H dans l'archive. Les logs du lanceur humain suivent
désormais le même dossier privé que les épisodes. Aucun nouvel essai H ni retour
humain n'a été fabriqué pour ces contrôles.

## 2026-11-08 — Positionnement, voix locale et encombrement du coaching

Retour humain dans le chat : consignes claires, repères mal placés. Ce retour
ne fournit pas de label de réussite ou d'utilité pour chaque essai.

Dans l'essai privé `sess_218da7c4dd91`, le premier guidage arrive 12,53 s après
le début de l'essai ; les cinq suivants arrivent entre 5,78 et 6,96 s après
reprise, médiane 6,37 s. Entre réception d'une observation et émission de la
consigne : 4,90 à 6,04 s. Ces temps comprennent la boucle API et la restitution,
pas uniquement l'inférence. Le temps de lecture/action humaine est exclu de ces
intervalles ; le temps total de séance ne mesure pas la latence du modèle.

Correctifs préparés : contrat de coordonnées GUIDE explicite 0–1000, échelles
X/Y indépendantes, cibles invalides ou ambiguës masquées ; Magnet repliable et
badge de raccourci masqué en mode compact, états actifs conservés ; voix macOS
locale Thomas quand le pilote humain est lancé sans fournisseur vocal externe.
La transcription Gladia et la synthèse vocale sont des composants distincts.
La synthèse Thomas a produit un WAV valide hors sandbox, sans lecture audio
pendant ce contrôle. Aucun gain de latence H ni précision réelle après correctif
n'est encore établi par ces tests techniques.

Intégration : `1d0b1d9` contient les corrections ; `7e7ef88` intègre le nouveau
`main` de Matteo (`6cfe7a3`) dans la branche de travail, sans fusionner notre PR
sur main. Après résolution du conflit de routage CLI : **961 tests Python et
sept tests desktop passent**. Les huit tests nécessitant un serveur local ont
d'abord été bloqués par le sandbox ; la suite complète hors sandbox passe.

Le pilote humain redémarré expose `speech.provider=macos`, `voice=Thomas`,
`enabled=true`, tout en conservant `observe_only=true` et autonomie zéro.
La page Voice réelle affiche ces paramètres et la commande de test vocal a été
acceptée. Audibilité et précision du cercle restent à confirmer par l'utilisateur.
Les sept anciennes traces sont conservées ; elles n'avaient pas de fichier de
labels humains au moment du redémarrage. Le test de voix ne crée pas de succès H.

Premier passage après redémarrage : demande « Montre-moi où lire les réponses
de cet essai », `sess_0037fb139a9b`. Une consigne, cible logique (1057, 523),
18,7 s pour la séance complète, coût H déclaré 0,0041307 USD. Le vérificateur
visuel valide ses deux critères et le rapport est resolved. Ce résultat technique
ne confirme ni l'audibilité, ni le placement perçu du cercle, ni l'utilité : retour
humain encore attendu. Pas de comparaison de vitesse avec les essais différents.

## 2026-11-08 — Activation ElevenLabs et retour visuel

Retour humain reçu dans le chat : voix locale audible, repère encore décalé.
Ce retour n'est pas converti automatiquement en labels de réussite/utilité.
La clé ElevenLabs fournie est conservée hors dépôt, dans `speech.env` privé
(mode 0600) ; le lanceur charge uniquement les variables vocales autorisées.
Test réel de synthèse français : succès, 147 456 octets PCM, durée audio 3,34 s,
requête 0,92 s avec le modèle flash configuré. Ce temps concerne la synthèse
vocale uniquement, pas Holo ni une tâche utilisateur.

L'essai en attente `sess_e9749b5ceb6b` a été arrêté proprement pour recharger la
voix. Rapport et événements locaux conservés ; export H signalé partiel.
L'audit de `sess_0037fb139a9b` confirme une conversion normalisée cohérente et
un point situé dans le panneau demandé, sans preuve de nouveau décalage Retina.
Un défaut distinct de restitution est identifié : la dernière consigne peut
arriver sans état `awaiting_user` et ne pas dessiner sa nouvelle cible.

Correctif de restitution finale : l'écran de clôture affiche maintenant la vraie
consigne finale avec sa cible et son verdict, même si aucune attente utilisateur
n'a précédé cette étape. Les cas non vérifiés restent présentés comme tels ; un
abandon ne réutilise pas une ancienne cible. Tests ciblés de clôture, voix et
coordonnées exécutés hors réseau ; précision perçue à retester sur une page H.

## 2026-11-08 — Clic ciblé et préparation des phrases GUIDE

Audit : le watcher desktop acceptait un clic quelconque ou un changement global
de l’écran et le backend le traduisait en « I did it ». Une réponse groupée pouvait
alors afficher une cible devenue périmée. Ces signaux n’étaient pas une preuve
de réussite.

Correction : le signal automatique est limité à la cible géométrique proposée,
avec garde sur l’application active ; la saisie nécessite un champ ciblé, de la
saisie puis Enter/Tab. Le changement d’écran seul ne valide plus l’étape. Les
coordonnées deviennent invalides après défilement ou interaction susceptible de
changer le contexte. Un repère absent ou imprécis permet toujours une déclaration
explicite dans Home : « J’ai fait l’étape » / « Je suis bloqué ». Ces boutons sont
liés à la session et au numéro d’étape ; une commande périmée est refusée.

Le backend conserve la différence entre interaction observée et déclaration
humaine. Après chaque réponse, il demande à H une nouvelle observation et le
contrôle de l’état attendu. Une seule étape est affichée par tour. Il ne certifie
pas indépendamment la fraîcheur du screenshot ni la bonne identité DOM du bouton :
l’extension devra apporter cette preuve supplémentaire.

Deux instructions suivantes au maximum sont préparées pour la synthèse vocale.
Elles ne déclenchent ni lecture ni affichage ; leur texte devra être confirmé par
le nouveau tour. La phrase en cours a priorité, les préparations en attente sont
remplacées si le plan change et annulées à Stop. Une synthèse déjà partie peut
finir silencieusement dans le cache. Aucun appel H spéculatif supplémentaire.

Tests techniques hors modèle : mauvais clic, point périmé, app/scroll, saisie,
arrêt, confirmation explicite, lot de consignes invalidé, cache vocal, priorité
audio, annulation et compatibilité des schémas. Aucun score humain ni gain de
latence réelle n’est déduit de ces tests. Un parcours humain H reste nécessaire.

Validation finale : **1 038 tests Python passent** (agent, backend, pilote et
import/minimisation de profils), ainsi que les sept tests desktop existants.
La recette renderer en Chrome headless couvre sept groupes de vérifications
avec un serveur simulé local : confirmations exactes, double clic, conflit 409,
états masqués, voix et feedback ; zéro erreur JavaScript. Elle ne mesure pas
l’audio réel, H, ni le masquage natif Electron.

## 2026-11-08 — Microbenchmark réel Holo4 : DGX et fenêtre

26 appels Models API au total : 13 cloud et 13 DGX, dont 20 mesures retenues,
quatre échauffements et deux préflights. Localisation d’un bouton de documentation
H publique, bureau synthétique, sans données personnelles ni interaction réelle.
Le centre prédit est dans la cible DOM pour 20/20 réponses mesurées. Ce score
géométrique ne constitue ni une tâche réussie ni un label humain.

Médianes TTFT reçu / JSON complet : cloud image complète 1,442 / 1,714 s ;
DGX complète 0,600 / 1,705 s ; cloud fenêtre 1,376 / 1,568 s ; DGX fenêtre
0,512 / 1,617 s. Tokens d’entrée : 1816 → 1286, soit −29,19 %. Une page
fixe, cinq répétitions par condition et cache partiellement réutilisé ; ce n’est
pas un A/B du coaching. Les images ont une échelle commune et restent hors Git.

Relais DGX temporaire, tunnel et jeton fermés après mesure ; aucune modification
des serveurs de modèles existants. Résultats et fixtures archivés dans le dossier
privé HCompanionResearch/benchmarks. Protocole et limites dans
[le rapport](holo4-latency-window-benchmark-2026-11-08.md). L’application utilise
toujours son moteur précédent ; crop et DGX ne sont pas activés en production.

## 2026-11-08 — Intégration accessibilité, coach Devin et préparation du pitch

Intégration de `origin/main` à `954c0ca` : catalogue de contrôles macOS du navigateur,
guidage textuel par Holo4 avec coordonnées AX, transcription Gladia en direct,
nouvelle interface desktop de Tom. Nos retours vocaux/labels privés, confirmations
liées à la session et à l'étape, mode observation seule et raccourci Ctrl+Maj+H sont
conservés. Le cadre d'une app masquée ne filtre plus les clics dans son ancien rectangle.

Nouveau `--software cognition` : procédure de guidage ouverte, réponses anglaises,
documentation publique dédiée et traces séparées des essais H. Aucun lancement,
message, commentaire ou merge Devin n'est autorisé par cette procédure de lecture.
Le corpus local conserve ses citations versionnées et n'est pas une observation du compte.

Validation hors ligne après résolution des conflits : **1 043 tests Python**, **11 tests
desktop**, contrats régénérés ; contrôle headless de Home/retour/voix, y compris
780 px de large. Les tests du microphone ne démarrent pas d'enregistrement réel.

Un **appel réel Models API Holo4** sur un catalogue de trois contrôles préparés
(`Agent`, `Ask`, `Prompt`) a reçu une question française : il a sélectionné `Ask`
et produit une instruction et une explication anglaises. Durée client **3,222 s**.
Il s'agit d'un test de raccordement sur fixture, sans capture ni clic dans le compte,
sans label humain, pas d'une mesure de performance du parcours utilisateur. Résultat
conservé hors Git dans le dossier privé `human-cognition/cognition-planner-probe.json`.

Compte Devin ouvert : l'utilisateur a ajouté des crédits par coupon, et la bannière
d'épuisement a disparu après actualisation. L'espace ne montre encore aucune session.
Le clonage vocal autorisé a abouti chez ElevenLabs après ajout du droit de création à
la clé par l'utilisateur ; aperçu anglais généré. Échantillon, identifiant de voix et
clé restent privés. La qualité perçue de cette voix et le guidage live restent à noter
par un humain. Aucun essai H actif n'a été arrêté pour ces vérifications.

Préparation éditoriale : [dix scénarios Devin](scenarios/cognition-human-session.md),
[conducteur 120 secondes](pitch-video-2min.md). Ce sont des plans de recette/tournage,
pas des vidéos réalisées ni dix réussites acquises.

## 2026-11-08 — Arrêt utilisateur et raccord natif Devin Desktop

L'ancien essai H a été arrêté sur demande explicite de l'utilisateur. Son état
terminal `stopped`, son rapport, son journal et l'archive complète de sa session H
ont été vérifiés dans le stockage privé avant l'arrêt de l'ancien serveur.
Aucun feedback humain ni label de réussite n'a été ajouté à cet essai.

Le bouton **Stop task** est maintenant accessible pendant une tâche depuis tous
les onglets du compagnon. Une erreur d'arrêt reste visible et permet une nouvelle
tentative. Les commandes vocales exactes « Stop task » et « Arrête la tâche »
sont reconnues après transcription, sans lancer de nouvelle tâche. Une dictée
explicitement destinée au feedback reste un feedback.

Le lanceur accepte `--software cognition --native-devin`. La collecte AX cible
uniquement la fenêtre focalisée de Devin Desktop (`com.exafunction.windsurf`),
revérifie le premier plan après la collecte et la planification, et exclut les
valeurs et descendants des champs de saisie. Pas de repli navigateur ni de capture
du bureau dans ce pilote natif. Si AX manque, le coach annonce le blocage ;
l'identité de l'application ne constitue pas une preuve de réussite métier.

Devin Desktop **3.12.28** est installé et son arbre natif expose notamment
`Switch mode`, `Cloud` et `Local`. La lecture du pilote lorsque Codex était au
premier plan a correctement renvoyé une cible indisponible. Cela ne valide pas
encore le guidage vocal ni le placement des annotations dans un essai humain.

Validation après intégration : **1 104 tests Python** et **13 tests desktop**
passent. Les tests couvrent le changement de fenêtre, l'exclusion des champs et
de leurs descendants, l'arrêt vocal, le bouton global et le refus d'une requête
d'arrêt. La recette hors ligne ne produit pas de label humain ou de gain de latence.

## 2026-11-08 — Dictée vide, barre de menus et relance autonome

L'utilisateur signalait une app disparue. Le processus Electron tournait encore,
mais le moteur vocal avait quitté avec `ValueError: Please say a question` après
une transcription vide. Ce n'était pas un échec de Holo ni de l'accès à Devin.
Une transcription vide affiche désormais une invitation à réessayer et conserve
le listener ; elle ne crée pas de tâche, ne consomme pas un feedback armé et ne
produit pas de label.

La barre de menus macOS reprend le visage du compagnon : ouverture du panneau,
arrêt de tâche et relance du pilote Devin. La croix masque la fenêtre ; une nouvelle
ouverture réutilise la même instance. Le panneau masqué n'envoie plus de heartbeat
qui maintiendrait le Magnet caché. Quitter l'interface reste distinct d'arrêter le
moteur vocal indépendant ; aucun service au démarrage de macOS n'est installé.

Le lanceur `Launch H Companion.command` démarre le moteur détaché, vérifie sa
disponibilité et réutilise uniquement un pilote natif Devin identifié par son PID
et ses métadonnées. Il refuse les ports occupés par un autre moteur et ne tue aucun
processus existant. Les logs et la configuration de l'interpréteur restent privés.

Validation : **1 114 tests Python**, **26 tests du lanceur** et **19 tests desktop**
passent. Sur le Mac, le lancement détaché a réussi ; une seconde ouverture a gardé
le même PID moteur et un seul processus principal desktop. L'interface affiche
le raccourci choisi par l'utilisateur, **Option droite**, et le moteur rapporte
ElevenLabs disponible et activé. Aucun scénario Devin n'a été lancé par cette
recette ; aucun label humain de guidage n'a été ajouté. La visibilité du menu dans
la barre macOS a été soumise à vérification de l'utilisateur.

L'utilisateur a confirmé avoir vu l'icône avant de la fermer. À sa demande,
un lanceur natif **`/Applications/H Companion.app`** a ensuite été compilé,
signé localement et installé avec le même visage. Son ouverture a recréé une
seule interface Electron et réutilisé le moteur prêt ; le panneau natif affiche
**Right ⌥: new request**. La vérification de signature passe. Ce bundle est un
raccourci vers le checkout et l'environnement du Mac, sans secret embarqué,
pas encore une distribution autonome destinée aux autres équipes.

## 2026-11-08 — Diagnostic du blocage natif Devin

Deux essais humains se terminaient par « Native accessibility guidance is
unavailable ». Leurs journaux montrent pourtant trois plans successifs chacun,
avec des contrôles AX natifs nommés et positionnés, en environ 1 à 1,7 seconde
par plan. Le vrai déclencheur était la répétition d'une consigne, suivie d'un
message de repli trop général. Ces observations ne prouvent pas une permission
macOS manquante ni un arbre inaccessible.

Le moteur distingue désormais répétition, absence de catalogue, perte du premier
plan, réponse de planification invalide et blocage signalé par l'utilisateur. Il
demande ce qui a changé plutôt que d'attribuer toute absence de progression à AX.
**112 tests ciblés passent**, dont sept nouvelles régressions. Aucun repli vers
Chrome ou une capture globale n'a été introduit. La cause exacte de la répétition
après les gestes humains et la qualité du guidage restent à mesurer sur un nouvel
essai ; aucun de ces essais n'a été labellisé réussi automatiquement.

L'inspection native suivante a établi un défaut reproductible : le menu
« Devin Settings » expose un `AXMenu` frère de `AXWebArea`, alors que le collecteur
ne parcourait que ce dernier. La lecture couvre désormais la fenêtre native
focalisée entière, menus compris, en conservant le ciblage du bundle/PID,
la revérification du focus et l'exclusion des valeurs et descendants des champs.
Les autres fenêtres ne sont pas parcourues. **121 tests AX, cognition et guidage
passent**, avec des régressions sur l'apparition et la fermeture du menu. Aucun
réglage Devin n'a été modifié pendant l'inspection. Cette correction explique
une répétition possible ; elle ne constitue pas encore une réussite humaine
de bout en bout du scénario.

## 2026-11-08 — Homepage publique et redémarrage immédiat

La homepage de Tom est publiée sur **https://hcompanion.help/**. Le domaine
principal répond 200 en HTTPS et `www` redirige vers celui-ci avec un certificat
valide. Les sept fichiers statiques publiés ont été comparés à la release locale.
Les tests visuels desktop/mobile n'ont trouvé ni débordement ni erreur JavaScript.
Les cinq tests de la démo passent ; les anciens liens de paiement ne déclenchent
plus de requête vers localhost et ne prétendent plus confirmer un paiement.
Le texte présente le parcours de coaching actuel et les prix comme illustratifs.
Les contrôles des services déjà hébergés et les 19 identifiants de conteneurs
restent inchangés. Détails : [déploiement](landing-deployment-2026-11-08.md).

Pendant le redémarrage du pilote Devin, les sockets TCP récemment fermées
étaient prises pour un serveur encore actif. Le contrôle des ports utilise
désormais la même réutilisation d'adresse que le serveur : un listener actif
reste refusé, un port en TIME_WAIT peut être repris. **27 tests du lanceur**
passent, dont une régression avec de vraies connexions TCP. Le moteur a ensuite
redémarré et annoncé son état prêt ; aucune trace n'a été effacée.

## 2026-11-08 — Dictée mixte et progression native Devin

Les essais humains récents ont exposé trois défauts distincts. Gladia était
configuré en français seul et a mal transcrit le mot anglais « redeem ». Les
consignes du coach restaient anglaises. Deux essais coupon se sont arrêtés lors
de nouvelles dictées, sans crash ; une consigne informative non terminale pouvait
attendre indéfiniment une interaction. Un parcours d'introduction avec plusieurs
boutons « Next » successifs pouvait déclencher le garde-fou de répétition, même
si la page avait changé. Une autre trace avait un catalogue vide ; son origine
ne peut pas être attribuée à la notification lecteur d'écran sans autre preuve.

Le lanceur Devin utilise désormais `fr-en` : Gladia accepte les deux langues,
y compris dans une phrase, en direct comme en repli préenregistré. Le texte
transcrit n'est pas artificiellement traduit ; les réponses restent anglaises.
Un blocage explicitement déclaré par le planificateur termine le guidage sans
attendre un clic ni devenir une réussite. La répétition est maintenant évaluée
sur l'instruction et l'état observé de la page. Les autres garde-fous demeurent.

**180 tests ciblés passent** (guidage Cognition/natif, progression, arrêt final,
observation seule, voix et lanceur). Les tests Gladia utilisent des requêtes
simulées, sans micro ni appel payant : la qualité réelle de transcription et de
guidage reste à mesurer après relance. Les anciens épisodes et leurs labels
ne sont pas réécrits. Le corpus de scénarios contient maintenant six demandes
spécifiques à Desktop et distingue le coupon comme test de limite du pilote.

## 2026-11-08 — Intégration pour reprise par Tom

À la demande d'Edouard, intégration de la branche de travail avec les trois
derniers commits de `main` (jusqu'à `76519cd`). Les conflits du routeur, du moteur
de guidage et des tests AX ont été résolus en conservant les deux contributions :
réponses documentaires et parcours dynamiques de Matteo, coaching natif, feedback,
dictée bilingue et diagnostics de progression. L'intégration a été réalisée dans
un worktree séparé ; aucun pilote en cours n'a été redémarré pour cette fusion.

Validation de l'ensemble intégré : **1 250 tests Python passent, 3 sont ignorés,
14 sous-tests passent** ; **19 tests desktop**, **109 tests Vision Lab** et **5
tests landing** passent. Le typecheck TypeScript passe. La régénération des dix
contrats ne produit aucun changement. Ces contrôles sont hors ligne et ne
remplacent pas la recette humaine des scénarios Devin/Odoo.

L'historique est conservé par fusion, sans squash : certains lanceurs extraient
des révisions épinglées. Le lanceur macOS reste dépendant du checkout et de son
environnement local. Les secrets et épisodes privés ne sont pas inclus.

## 2026-11-08 — Devin : clic sans effet sur « Current plan »

Essai réel `sess_842b62fa7faa`, demande « What can I do here? ». Le coach a
proposé de cliquer sur « Current plan ». Edouard rapporte dans le chat :
« Rien ne change après le clic ». Le moteur était toujours en attente de la
première étape et aucune interaction cible n'avait été enregistrée. L'essai
a été arrêté proprement ; ses traces privées sont conservées. Son statut est
interrompu/abandonné, sans réussite vérifiée. Ce constat humain porte sur cette
étape ; aucun label d'utilité ni feedback saisi dans l'app n'a été inventé.
La durée d'attente de cet essai ne mesure pas la latence du modèle.

Deux défauts de code ont été identifiés : le catalogue AX ne transmettait pas
l'état activé/sélectionné des contrôles, et une cible invalidée pendant l'attente
ne pouvait plus déclencher de progression. Le nom « Current plan » ne prouve
pas que ce contrôle ouvre un écran ; nous n'avons pas établi qu'il était désactivé.

Le correctif conserve les états AX inconnus comme inconnus, refuse les clics sur
du texte ou un contrôle explicitement désactivé, et transmet au planificateur
l'absence de changement observé. Une reformulation ne suffit plus à recommander
à nouveau le même clic inefficace. Les champs restent un cas distinct : leurs
valeurs ne sont pas lues, donc un catalogue inchangé ne prouve pas l'échec d'une
saisie. Après invalidation de cible, une seule reprise de planification est
autorisée sur observation AX fraîche, sans confirmer l'action précédente.
Ces contrôles logiciels restent à confirmer par un nouvel essai humain.

Intégration des commits Matteo `fc8955a` et `1e36ce0` : nouvelles règles de
routage FR/EN, consultation des crédits distincte de leur activation, et
correspondance AX par mots entiers. Le pilote Devin utilise son propre chemin
de coaching ; ce routage ne suffit donc pas à expliquer/corriger l'essai raté.
Les snapshots de l'outil d'évaluation restent ignorés par Git, avec permissions
restreintes, URL nettoyée et nom de fichier indépendant de cette URL.

Validation intégrée après correction de compatibilité de l'affichage final :
**1 299 tests Python passent, 3 ignorés, 14 sous-tests passent** (agent, backend,
pilot et scripts). Pas de nouvelle mesure de qualité du modèle ni de validation
humaine déduite de ces tests hors ligne. Le benchmark de routage payant de Matteo
n'a pas été réexécuté pendant cette correction.

## 2026-11-08 — Devin : catalogue vide au démarrage du guidage

Essai humain `sess_9b610d04645f`, demande transcrite « Show me the available.
Conversation modes. ». Le pilote reconnaît la fenêtre native au premier plan,
mais ne retient aucun contrôle. Il termine bloqué avant la planification,
en 66 ms après approbation. Edouard signale le message d'accessibilité ; aucune
réussite ni utilité n'est déclarée. Les traces restent dans le dossier privé.

La permission AX a ensuite été vérifiée comme accordée. Un diagnostic local,
sans H ni lecture de valeurs de champs, retrouve 59 éléments, 53 éligibles et
49 visibles dans Devin. Le menu des modes s'ouvre via inspection technique,
sans sélectionner de mode ni démarrer de tâche. Cette vérification ne constitue
pas une réussite du coaching vocal. Les anciens compteurs ne permettaient pas
de distinguer une lecture transitoirement vide d'un filtrage de visibilité vide.

Le pilote réessaie désormais jusqu'à trois lectures, avec 150 puis 300 ms
d'attente interruptible, en revérifiant le focus et le périmètre à chaque fois.
Le chemin normal n'attend pas. Le journal et `/status` conservent uniquement les
compteurs et un motif technique (arbre vide, contrôles masqués, fenêtre non
active, etc.), sans libellé, URL ni valeur saisie. Le message n'attribue plus
automatiquement un catalogue vide à une permission manquante.

**188 tests ciblés passent**, dont récupération après lectures vides, arrêt
pendant l'attente, changement de périmètre, cause de filtrage et confidentialité
des diagnostics. La recette vocale de la version corrigée reste à effectuer.

## 2026-11-08 — Devin : menu ouvert mais consigne répétée

Essai humain `sess_176b3e7bf762`, demande transcrite « Show me the available
conversation mode. ». Deux interactions sur la cible sont bien enregistrées.
Après le premier clic, les métadonnées AX changent et le menu est ouvert, mais
le planificateur redemande « Click the 'Switch mode' popup button ». La garde
contre la répétition termine l'essai bloqué après environ 27 secondes depuis
l'approbation. Edouard signale le message et l'erreur ; aucun label de réussite
ou d'utilité n'est ajouté à sa place.

Diagnostic local : 65 éléments lus, 53 conservés, aucun rejet de visibilité.
Les quatre `AXMenuItem` « Agent », « Ask », « Code » et « Data » sont présents
dans le catalogue transmis. Le filtrage et la détection du clic ne sont donc
pas la cause de cette répétition. L'observation est figée dans le dossier privé,
sans valeur saisie ni image. Avec l'autorisation explicite d'Edouard, un rejeu
texte auprès de Holo4 reproduit la demande de rouvrir ce menu.

Le contexte distingue maintenant les options déjà visibles des boutons qui
ouvrent les menus. Le planificateur doit d'abord vérifier si l'écran répond à
une demande d'explication ou de liste ; il ne doit pas sélectionner une option
ni rouvrir son menu pour simplement la montrer. La présence d'options ne valide
jamais automatiquement une modification demandée. Les arrêts pour répétition
conservent aussi l'historique des interactions dans `steps_taken`.

Deux rejeux après correction, dont la formulation transcrite ci-dessus,
produisent une réponse finale « Ask and Agent », sans cible ni nouveau clic.
Latences de ces appels : 1,56 et 1,66 s, contre 3,64 s sur l'appel de reproduction
avant correction. Ce petit contrôle ne constitue **pas** un benchmark de latence :
réseau, cache et formulation peuvent intervenir. Les rejeux réutilisent une
observation réelle avec un historique reconstruit ; ce ne sont pas de nouveaux
essais humains. Leurs entrées et sorties restent privées, séparées des épisodes.

**191 tests ciblés passent**, notamment la progression du menu fermé vers les
options visibles, la réponse finale sans clic supplémentaire, la conservation
de l'historique en cas de blocage et la séparation entre options visibles et
réussite d'une modification. Le guidage vocal complet doit encore être retesté
par Edouard ; la vérification indépendante et l'utilité ne sont pas déduites de
ces rejeux.

## 8 novembre 2026 — CD et préparation multi-produit

CD : la PR #10 a été fusionnée sur main (`b751d80`). Le run Actions
`42448143936` s'est terminé en succès : tests de la homepage, publication des
sept fichiers autorisés, puis comparaison HTTPS octet par octet. La clé dédiée
refuse une commande libre `id`. Neuf tests du récepteur et cinq tests de la
homepage passent. Les autres blocs Caddy et les conteneurs sont préservés.

Le dernier essai vocal Devin `sess_05b59d921064` reste **escalated**, avec une
consigne demandant de remettre Devin au premier plan. Aucun feedback humain
n'était enregistré ni en cours de dictée lors du contrôle avant mise à jour.
Ce passage ne constitue pas une démonstration réussie du menu.

Le nouveau profil `auto` sélectionne H/Odoo/SAP/Devin à chaque nouvelle demande,
lie la tâche à ce produit et à sa surface, puis injecte les extraits du corpus
correspondant. Tests locaux : refus des origines inconnues et des logins,
isolation documentaire, changement de produit sans ancien historique, arrêt du
guidage si l'app change, conservation littérale du JSON documentaire et du texte
utilisateur. La recherche avec les quatre corpus réels retourne respectivement
3/4/3/4 extraits pour les questions H/Devin/Odoo/SAP préparées, sans appel modèle.

Le profil de démo active le slider en démarrant à 0 ; le pilote de recherche
observation seule garde son verrouillage. Les tests du renderer vérifient le
glisser et le clavier, le retour à 0, l'affichage du contexte et le maintien du
verrouillage historique. **Ces tests simulés ne prouvent pas un parcours vocal
réussi**. Les huit questions de `demo-eight-questions-2026-11-08.md` restent à
évaluer en répétition humaine, avec réussite et utilité labellisées séparément.


## Odoo auto-context — repeated CRM guidance, 2026-11-08

Human trial `sess_ed829556ca29`, 07:38–07:39 Europe/Paris (about 50 seconds):
Odoo and two local documentation excerpts were selected correctly. The transcript
was `Help me. opportunity Maison d'eau.`; it did not retain the full intended
Maison Aube question. The human reported **« Contexte Odoo, mais guidage incorrect »**.
Six instructions targeted the CRM header while the pipeline was already open.
Target clicks were observed, but changes in accessibility metadata kept allowing
that instruction. The run ended escalated/unverified; no success/usefulness labels
were fabricated. Original private events and report remain unchanged.

Corrections: track attempted click targets by visible page state independently of
geometry and AX traversal order; do not retry an earlier state when a menu cycles
open/closed. Preserve input editing and real navigation. Require the text planner
to state the current view and distinguish exact record names before choosing its
next action. Current screen evidence takes precedence over documentation recipes.
The Odoo knowledge page now explicitly starts at search when Pipeline is already
open. Final verification stops if automatic context has changed to another product.

Text-only Holo4 development replay, with a small manually transcribed list of
controls observed in the fictitious demo (not a replay of the complete captured AX
tree): an intermediate prompt still chose Comptoir Aube instead of Maison Aube.
With the factual-observation field added, the same request selected Rechercher…
and explicitly distinguished the names (1.91 s for that one model call). With the
original imperfect transcript and a prior CRM click, it also selected search
(1.21 s). These are **planner checks**, not a completed workflow, a speed benchmark,
or a human usefulness label. Private diagnostic output stays outside Git.

Offline validation: 154 targeted tests passed, including layout jitter, returning
to an earlier menu state, genuine next-page navigation, continued typing, and
rejecting verification on a different product. A new live voice/click trial is
still required; the original incorrect trial must not be counted as a success.


## Odoo search-target tracking — 2026-11-08, 07:48 Europe/Paris

Trial `sess_941d33ee2f5c` correctly transcribed “Help me find Maison Aube.” and
selected the Rechercher… field in the open CRM pipeline. A second voice input
interrupted that trial; `sess_729e820585a6` recorded the incomplete “me find” and
also selected search. The human reported the badge “Target changed. Confirm in
H Companion or stop”, which was not understandable. No completed search or task
success was verified. The second waiting trial was stopped through the local
control API to load a fix; both private archives remain intact, without invented
human success/usefulness labels.

Code diagnosis: the tracker received the chosen exact rectangle, but subsequent
name-only lookup discarded the target whenever another control shared its label.
Odoo exposes both a search button and an input named Rechercher…. A separate gate
allowed a fresh-observation retry only in native Devin, not automatic Odoo.

Fix: disambiguate matching controls with the original rectangle and retain the
observed role. Do not jump to a different same-named control; ambiguous or large
movements still invalidate the target. Automatic guide mode can request one new
plan after a fresh foreground read, even when the old target has disappeared.
This is explicitly **not** confirmation that the user acted. Product scope is
checked again by the runner. The fallback badge now states what to do without an
ambiguous request to confirm completion.

Validation: 178 targeted tests passed, then an added tracker-loop regression
passed with all 73 input/tracker tests. Tests use fake controls, not the user's
Mac. A live user retry of this version remains pending.


## 2026-11-08 — Creative documentation probes and Comfy preflight

Five real Holo4 cloud episodes; three initial probes ran concurrently in separate
browsers. Full private H archives retained for all five, including failed trials.
No authenticated Comfy/CapCut workflow or GPU job was run. No human success,
usefulness or training-consent label was synthesized.

| Scenario / local episode | Evidence review | Limitation |
| --- | --- | --- |
| CF-DOC-01 / `cloud_81ae6960fa694ff7` | Yes, documentation only | Managed packs / unsupported nodes answer supported by official page and frame 000004 |
| CF-DOC-02 / `cloud_4150bbe299bd458f` | Partial, documentation only | Queue modes and node help supported; added claim about default Run mode not established |
| CC-DOC-01 / `cloud_1555d6de9d55437c` | Unknown, infrastructure blocked | Repeated `scroll_web.scroll_element` schema errors; quarantined |
| CC-DOC-01 retry / `cloud_48ea9cb346ca4c89` | Unknown, infrastructure blocked | Explicit valid scroll example did not prevent recurrence; original failure preserved |
| CF-PUBLIC-01 / `cloud_b915062116ae4813` | Unknown, authentication pending | Actor reports login wall; retained frame only shows loading, so not independently verified from that frame |

Provider state `interrupted` on answered documentation trials is due to the runner
cancelling its owned idle session after receiving the answer and draining events;
see `completion_reason`. It is not a success label. Separate `agent-review.json`
files record the evidence-based judgments, with human guidance explicitly unvalidated.

Local inspection found Comfy Desktop v1.1.3 showing Comfy Cloud and an unsaved
Z-Image workflow. Chrome also opened the Cloud editor without a new login. Both
showed “Subscribe to Run”; no subscription or generation initiated. Chrome's AX
read exposed named workspace controls and some node labels, while the native
window read exposed only the outer shell. This does not prove that every graph
parameter is usable by the current AX coach.

Implementation: separate Comfy/CapCut knowledge contexts, bounded read-only probe
catalogue/launcher, product identity preserved in the shared tower, preparation
stage timings, reuse of an unchanged unique target after unrelated layout jitter,
and removal of the unused screen-difference watcher. 325 targeted offline tests
passed. A human voice/click trial is still needed to validate the latency fix.

### H session review: missing response text and target recovery — 2026-11-08

Human trial `sess_b784d78bf8ac` recognized clicks on Answer but repeated the
instruction and eventually escalated. The later `sess_1a5225af2124` exhausted
its target-reobservation budget. Its stopped trace is retained; no successful
human outcome or feedback label is inferred.

The browser catalogue excluded static text and the AX collector discarded
paragraphs over 120 characters. The planner could read controls but not the
response content. It now receives bounded, hit-tested page-text excerpts,
separately from actionable controls (maximum 6,000 characters / 32 excerpts).
Input values and input descendants remain excluded. Changes to those excerpts
invalidate stale plans and count as observed page changes, not task success.
The tracker can recover an exact anchored control omitted by its scoring
shortlist. A recognized interaction renews the one-reobservation budget;
consecutive invalidations without interaction remain bounded.

243 targeted offline tests passed. Three real Holo4 Models API planner calls
used synthetic replay inputs derived from observed non-secret labels, without
browser actions. First replay read the response but unnecessarily asked the
user to inspect it (1.595 s). After the prompt correction, the paired cases
returned: populated AGENT ANSWER -> direct informational answer, done=true
(1.596 s); no answer text -> click Answer, done=false (1.461 s). These are
individual planner latencies, not end-to-end voice latency or a human benchmark.
Replay records remain private under human-cognition/diagnostics. Live voice,
target placement and post-click continuation still need the human retest.

### H session review: empty terminal answer falsely reported as success — 2026-11-08

The human reported hearing “The page appears to answer the question; result
still needs verification.” Three retained trials (`sess_49ff4ccc3999`,
`sess_27e0f1b2cde7`, `sess_bc3c92ac3ade`) emitted that fallback and recorded
resolved with “Goal reached, as planned from the page.” These are defective
coaching outcomes, not validated successes or positive human labels. The last
transcript was the incomplete “does it still”; the first contained the complete
question. Original reports and traces remain unchanged.

Diagnosis: the planner's terminal summary was optional. The runner replaced a
missing summary with a generic sentence, ignoring any informational instruction,
and declared success. The schema now requires summary and the prompt requests
the concrete answer. The runner retains an informational instruction when the
summary is missing, otherwise allows one bounded repair and blocks on repeated
empty answers. Spoken and declared answers use the same text. An incomplete
question should request clarification, not infer a goal from the page.

124 targeted offline tests passed, including missing/invalid terminal summary,
bounded repair, repeated empty responses, menu answers and guide progression.
Two parallel real Holo4 Models API calls used the same synthetic replay fixture:
the complete Interrupted/answer question returned a direct factual summary
(1.732 s); “does it still” returned a clarification with done=false (1.662 s).
These are planner-only timings, not voice or end-to-end benchmark results.
Private replay: human-cognition/diagnostics/h-terminal-answer-replay-20261108.json.
The live voice retest remains pending; no human success label is inferred.

### Overlay readability and internal action narration — 2026-11-08

The human supplied a photo showing a clipped `write_desktop(...)` call in the
pencil note. Private trial `sess_5c2aaa849845` confirms that the active condition
was ACT / autonomy 2 and that a provider tool-call string reached narration.
This is an interface defect, not a new success/usefulness label for the trial.

The native overlay silently sliced its main note to 110 characters. Main and
explanatory text now retain their complete content, measured with the actual
font and available width. Long notes use numbered automatic pages, preferring
sentence boundaries; terminal notes remain visible long enough to read all
pages. Moving a tracked target does not restart pagination. Short annotation
labels and the live-transcription badge retain their existing compact format.
Planner instructions now request short plain-English guidance.

User-facing ACT narration uses local English descriptions of the tool type;
raw calls and arguments stay in the original trace, not in the voice, pencil
note or desktop status. No extra model call is needed for these transformations.

153 targeted offline tests passed. Native font metrics were checked at
1470×956, 800×600 and 600×500. Offscreen AppKit renders of the first and final
pages at 800×600 were visually inspected: text and the page indicator fit,
and the last sentence is retained. These renders are synthetic UI fixtures,
not screenshots of a successful human task. A live user retry remains pending.

### Documentation tabs and live autonomy reduction — 2026-11-08

The H profile now instructs GUIDE and ACT to preserve the product tab when
opening official H documentation. GUIDE asks the human to open/select a new
tab; ACT opens one before navigating. Once on the docs, subsequent navigation
reuses that tab. This is a model instruction, not deterministic tab interception;
the resulting Holo browser behavior still needs a live trial.

Audit confirmed that autonomy 0 starts GUIDE without takeover, 1 starts GUIDE
with takeover on a supported stuck condition, and 2 starts ACT. Lowering the
level previously did not stop an actor already running. It now invokes the
normal local stop gate and provider cancellation, silences narration, and asks
for a new guided request. Completed actions are not undone; cancellation of an
in-flight provider action is asynchronous. Traces are preserved.

192 targeted Python tests and 21 desktop tests passed, including actor
cancellation, takeover reduction, existing mid-guide escalation and docs policy
propagation. One additional regression passed for a remaining dynamic-guidance
140-character slice: complete notes now reach overlay pagination. The live
desktop keyboard control was observed delivering autonomy 1 to the running
engine while idle; a complete live three-level round trip was not established.
These checks are not human success/usefulness labels or a new task benchmark.

### H documentation passage and conversational delivery — 2026-11-08

Added a documentation reading policy: prefer visible section links, otherwise
use bounded, observed scrolling in ACT and leave the relevant passage visible.
A single small down/up preview is permitted only for general page overviews
with a restorable starting position; this optional preview remains untested.
GUIDE keeps human control and asks for explicit confirmation after manual
scrolling. The H generic navigation scope now explicitly includes its official
documentation rather than contradicting the separate-tab instruction.

147 focused offline tests passed, followed by 51 routing/procedure checks after
the scope adjustment. Closing notes now speak the actual guide answer first,
with conversational verification wording. Inconclusive reports stay qualified;
the fallback no longer claims a support handoff without evidence.

One initial cloud probe was stopped after a local tracking-script error; it is
not a result. Retest `876e2f44-8263-42e0-8663-1cbd23c10922` used one isolated H
browser, public H docs only, no login and no local Mac control (12-step / 90 s
limit). The exported trace shows three 600 px downward scrolls, cookie-banner
dismissal and a final 400 px adjustment. The final screenshot visibly contains
the Browser profiles heading and its complete relevant paragraph. Assistant
review: passage positioning passed; answer was too verbose and copied the
paragraph. H status is interrupted after its answer, not completed; the archive
is complete, and no human success/usefulness label is inferred.

The answer policy was tightened to two short sentences / 45 words without a
full-paragraph quotation. A real Holo4 Models API call on a synthetic text
fixture derived from that public section returned a direct 17-word answer in
3.605 s, done=true, with no unnecessary click. This is planner-only evidence,
not an end-to-end voice timing or a retest of ACT's final narration. Private
artifacts: human-cognition/diagnostics/docs-scroll. A desktop voice trial and
the optional down/up preview still need human observation.

### Interrupt on a new push-to-talk press — 2026-11-08

Previously, key-down silenced speech but interrupted the running task only once
a transcript reached the queue. The microphone's starting callback now invokes
the normal local stop gate/provider-cancellation path before opening audio or
waiting for transcription. This works without an overlay and while guiding,
acting or verifying. Short presses and microphone failures do not resume the
interrupted task. Its trace and abandoned status are preserved.

Starting, recording and transcribing suppress old speech and closing notes.
Request generations discard late transcripts, partial messages and routing
results superseded by a new press, so an earlier question cannot silently
restart behind the new dictation. A current transcript is still delivered
normally; human feedback remains separate from task success.

242 targeted offline tests passed, including a simulated actor that observes
the stop event and saves its report, slow microphone startup, late transcription,
short presses, microphone failure and guide/ACT/verification states. The small
talk-loop generation handoff was then rechecked with the spoken-command and
empty-transcript suites. No real provider cancellation latency or microphone
interaction is claimed here. An in-flight external action can finish before H
acknowledges cancellation; a live Option-right interruption trial remains pending.

### Natural speech and response format — 2026-11-08

Takeover tool statuses (including “Preparing the response…”) remain written
status information. They are no longer read aloud; one cached “Give me a moment,
I'll check that” acknowledgement is allowed per intervention instead. Guidance
and final answers keep their normal speech path.

Voice settings now offer Text only / Voice only / Both and retain the choice
across desktop reloads and agent restarts. Text only stops active speech; Voice
only hides note text while retaining target markers and operational statuses.
The original scene and report stay intact. A missing speaker retains written
output. The floating shortcut reminder expires after 10 seconds, including the
compact Magnet reminder, and does not reappear after each completed task.

Validation: 138 targeted Python tests and 23 desktop tests passed, covering
control API validation, mode transitions, mute compatibility, unavailable audio,
preference restoration, rejected changes, native target rendering, lossless note
restoration, shortcut expiry, and continued visibility of listening/error states.
The HTTP control tests required a local listening socket outside the sandbox;
the initial sandbox-only run could not bind that socket and was rerun successfully.
These are local software checks, not a new H benchmark or human usefulness label.

### Misleading context rejection on H Vaults — 2026-11-08

The user's photo showed H Platform's Vaults page with the local fallback asking
them to open a supported app and finish signing in. The runtime logged three
valid transcripts (cloud-agent help, then skill help), no intervention, and
“No supported product in front”. The same Vaults URL exclusion already existed
in commit 6cd4cc4, before the speech/display change in 14e2218. This is a local
routing rejection, not evidence of a Holo response or model regression.

Product identity is now separate from permission to inspect page content.
Protected H pages remain unread and cannot start an agent, but the UI reports
H Company · protected page, with a specific explanation and a relevant manual
exit (Skills, Agents or View documentation). Login, unknown origin, missing URL
and non-foreground windows have distinct messages. Only the product and reason
are logged; no URL/query or page contents enter the diagnostic.

154 targeted offline tests passed, including the exact skill/cloud/vault
questions, no AX walk on protected pages, documentation access, origin checks,
and the live-loop fallback without a fabricated run. No new model call or human
success/usefulness label was produced. The restriction itself remains: coaching
resumes after the user opens an allowed section or the documentation.

### Restore spoken explanations during an introductory tour — 2026-11-08

The user's real "show me around" trace contained useful public explanations of
Home, Projects, Agents, Sessions and Skills. Our presentation layer replaced
them with generic tool statuses such as "Selecting an on-screen control…".
The subsequent quiet-status change suppressed those spoken statuses without
restoring the explanations. This was a presentation regression, not missing
Holo content. The interrupted tour remains abandoned, without a success label.

Public provider content now has a separate narration field. Only that prose is
shown and spoken during ACT; tool arguments and private reasoning remain trace
data. Code/status-only fallbacks do not become coaching notes. Useful ACT final
answers are also retained alongside the independent verification qualification;
the report and its labels are unchanged. Introductory tours request two or three
areas with short explanations. This does not add a model call or deliberate wait.

Session guards prevent late events from an interrupted request replacing the
current narration. When the page changes, obsolete pointers disappear while
the explanation remains readable. Voice-only/text-only preferences and the
push-to-talk interruption behavior are preserved.

Local replay of the archived provider events restored all seven public
explanations to the presentation cache. The previous cloud/local answer also
survived the prose filter, with verification still false. Replay made no API
call and performed no desktop action; it did not play audio or establish human
usefulness. Live narration and screen/voice synchronization still need the
user's next tour trial.

Validation: 205 focused offline tests passed (156 presentation/final guidance/
interruption/preferences/routing checks, plus 49 speech/procedure checks).
Regressions include immediate post-action observations, generic actions not
prolonging old notes, tool-free explanations, old-session events, and ACT final
answers retaining their independently unverified status.

### Stable centered notes and conversational tour endings — 2026-11-08

Human feedback on the next welcome tour: notes first appeared beside controls,
then jumped to the upper center when their pointers expired. The final public
message contained useful Sessions prose followed by "Result: done", "Summary"
and "Steps performed". Our ACT prompt explicitly requested that report format,
and the terminal display then read the structured summary again. The run is
still escalated/unverified; the user's original wording was also imperfectly
transcribed. This UI fix does not change its result or infer a usefulness label.

Main notes and their explanatory text now use a stable upper-center position;
the control is framed separately without a long connector. Removing the target
preserves pagination and avoids reanimating the note. Voice-only still retains
the control frame. Native font/layout tests cover three screen dimensions.

ACT now requests a short conversational closing alongside the answer tool,
with audit fields confined to the structured answer. A local presentation filter
removes appended report sections while retaining the preceding public prose.
Once that closing is presented, the terminal view keeps it without replaying
the summary or interrupting its voice. The independent verification remains
visible and the complete report remains unchanged in the trace.
Verifier prose is retained in its trace and cannot replace the actor's closing;
the verification status badge remains available.

Validation: 131 focused offline tests passed after the final changes, including
closing/native-layout and actor/verifier narration isolation checks. Local
replay of the actual actor archive preserved four public explanations and a
21-word closing without the audit appendix. An initial replay selected the
verifier archive and was corrected to the actor archive. No external call or
desktop action was performed during replay. Live voice/layout validation awaits
the user's next trial; no latency or task-success improvement is claimed.

### Misheard welcome tour produced an unrelated travel answer — 2026-11-08

The user's photo and stored transcript match: the requested welcome tour became
"Hello, give me a quick welcome to Orkney." The selected product was correctly
H Company, but ACT answered with tourism information instead of checking the
meaning against the product context. The run was independently unverified and
escalated. The user's later Skills run completed with a satisfied verification;
neither run receives a new human usefulness label here.

Two fixes: automatic mode now supplies the supported products' proper names to
Gladia instead of the old Odoo/Acme vocabulary. Both live and fallback requests
keep gentle vocabulary intensity and preserve the provider transcript verbatim.
ACT and GUIDE now receive an explicit software-coaching scope: welcome/help
requests refer to the foreground product; unsupported names require one short
clarification, not an unrelated general-knowledge answer or a silent rewrite.
Real named records visible in a product remain valid. ACT reports clarification
before actions as blocked, avoiding a pointless result-verification pass. Its
question is presented without an additional failed-task announcement; the report
remains blocked. No extra classifier call was added to the app's normal path.

Validation: 181 focused offline tests passed, followed by 40 narration/grounding/
interruption checks after the final clarification-presentation change. Eight
Holo4 Models API calls used synthetic text observations only, without screenshots
or desktop control. The ambiguous phrase now asks about the intended H tour in
both modes; the final ACT probe was blocked with no steps, and GUIDE selected
an info question with no target and done=false. Normal welcome/Skills examples
stayed about H; an Odoo customer named Orkney was accepted when present in the
fixture. Earlier clarification probes were too wordy and the instruction was
tightened to one short question. These are prompt/interpretation tests, not an
end-to-end Agents or microphone benchmark. No stored audio is available to
prove improved recognition; a live voice retry is still needed.

## 2026-11-08 — H Platform coach V2 isolated branch

- Branch: `edouard/h-platform-coach-v2`, based on `0f1e727`. Previous harness kept intact for rollback.
- Trigger: human photos showed a Skills explanation paginating through seven pages, including a Markdown table. The requested welcome tour also suffered off-topic ASR clarification.
- New path: one bounded Holo4 Models API decision, compact H documentation, current AX controls/text, four recent interactions; existing PTT/TTS/overlay reused. No legacy procedure runner, automatic success verifier, or report narration.
- Offline verification: 91 Python tests (core, journal, runtime) and 23 desktop tests passed. Includes stale response cancellation, actual target clicks, fresh control remapping, private traces and explicit human labels. These tests do not establish live task success.
- Real provider probes: seven synthetic page/question cases, including the six proposed demos and an ASR-corrupted welcome request, all returned valid short decisions. API latency 6.0–10.7 s at concurrency 3. No real account contents, desktop effects or microphone in those probes. Private raw evidence retained outside Git.
- Additional probes: interrupted answer panel follow-up avoids repeated clicking. Guide-mode doc opening without a visible link still rejects malformed output; documented limitation. Sessions follow-up can propose opening a listed run beyond the original stop-at-list criterion.
- Startup: old idle runtime stopped without deleting its traces; dedicated V2 runtime and Electron profile launched on local port 8792. Real voice/guide/action rehearsal remains human validation, not yet marked successful.

## 2026-11-08 — Repair false screen-read errors in real V2 trials

- Four human trials produced three failures and one interruption. All five recorded observations read H Platform correctly; a guided click and the Sessions → Skills navigation were recorded.
- Four short replies were rejected by our parser: two solely for containing three sentences, one for unused `text: ""`, one for unused `text: "None"`. All target IDs were present. The generic screen-read error was incorrect.
- Repair: canonicalize empty/null spellings only for unused optional fields, keep actual typing values and action validation, retain the 32-word/220-character bounds but remove punctuation-count rejection. Distinguish observation, provider, model reply and refresh failures in diagnostics and public messages.
- No prompt-routing expansion, model change or larger narration limit. Original traces and human labels are untouched. Regression tests include literal typing of “None”, forbidden extra action arguments and safe diagnostic JSON.
- Validation: 126 targeted Python tests passed. All four actual rejected replies were replayed offline through CoachClient using MockTransport and their original associated observations: 4/4 accepted with valid targets and original raw replies preserved. No new model calls, desktop effects or human labels in this replay; microphone/overlay rehearsal still pending.

## 2026-11-08 — Five-scene H Platform coach instructions and runtime

- Added the requested welcome tour, temporary API key, cloud environment, coaching Skill and session quota journeys on `edouard/h-platform-coach-v2`. The briefing remains a curated H reference, not a claim to cover all product documentation.
- A tour is prepared in one Holo decision: one introduction and up to three independently revalidated sidebar highlights. The runtime waits for speech, makes no clicks, and adds no spoken recap. New dictation and Stop cancel the sequence.
- Skill body text is separate from speech and supports multiline Unicode. API-key creation waits for a human confirmation, then rechecks the foreground form/control. Unsupported one-day expiration must stop creation; its availability has not been established in the real UI.
- Added an H-only AX observation boundary for settings pages and secret-like text redaction before model context/journaling. The account quota is fetched read-only, only for relevant questions, with a short cache; it belongs to the configured API connection, not necessarily the browser account. No automated video masking is claimed.
- Offline validation: 186 targeted Python tests and 23 desktop tests passed. Includes the exact French welcome phrasing, stale tour targets, interruption, delayed confirmations, Unicode clipboard handling, private observations and quota failures.
- First real Holo4 synthetic-fixture batch, concurrency 3: 6/8 protocol-valid. Cloud incorrectly chose a tour; the Skill name combined `click` with typing text. Both were rejected before any action. An unavailable-expiry response also had misleading wording despite proposing no creation.
- Tightened action schema and instructions without adding a repair-model round trip. Three targeted real-provider reruns passed: cloud → Environments click (11.5 s), Skill name → literal type (11.0 s), unavailable expiry → explanation and no action (12.0 s). The first batch's three-point tour, multiline Skill body, key confirmation decision and quota response were valid. Raw fixtures/replies remain private outside Git.
- No real key/Skill creation, account mutation, paid agent job, microphone benchmark or human success label was produced by these probes. Live React/Monaco field persistence and the complete five-scene rehearsal remain to verify.
- A further Skill-body probe used only static page text and the runtime's actual interaction-history shape (no fictional field values): valid Body typing, 552 characters, no repeated Name/Description step, 25.2 s. This remains a material first-draft latency, not a speed improvement claim.
- The read-only live quota endpoint returned limit 10, active 0, available 10 at 09:52 UTC for Companion's configured API connection. No assumption was made about the account currently open in Chrome.
- A French welcome request initially produced a valid tour in French. After making the English-only narration instruction explicit, its targeted rerun returned an English introduction and three English sidebar explanations in 18.0 s. This is a provider fixture test, not a live voice rehearsal.

## 2026-11-08 — Live tour latency, French narration and mode diagnosis

- Human reported the live tour was acceptable but slow, and the subsequent API-key request stayed guided and spoke French. Actual traces confirm the key request was in `guide` (slider Show me); no autonomous creation was attempted. The wording promising to act was incorrect. The last step ended after H Platform lost foreground; a click does not establish task success. No human success label was synthesized.
- The running V2 does use Matteo's AX reader (`_read_browser_page` / `_walk`, originating at `d41eaca`) and sends no screenshot. Start-to-first-observation was 296 ms for the tour and 241 ms for the key request. Observation-to-complete-Holo-response was 19.534 s and 10.383 s respectively. These are not TTFT or end-of-dictation-to-audio measurements.
- Compact semantic AX payload: retain every ID, label, role, explicit enabled state and page text; keep geometry locally for target validation/execution. Removed redundant schema annotations and JSON whitespace. The same actual tour observation dropped from 10,838 to 7,817 provider input tokens; its one replay still took 18.57 s. This is not evidence of a robust latency improvement.
- V2 launcher now defaults Gladia to French/English code switching instead of the shared French-only default. Explicit environment language overrides remain respected. No stored audio establishes what language was actually spoken in the two preceding trials; microphone validation is still pending.
- Replaying the actual French key request plus French interaction history showed that stronger system wording alone still returned French. Explicit English output instructions in the current request then yielded English in both ACT (8.42 s, 7,841 input tokens) and GUIDE (8.03 s, 7,071 input tokens), without another translation/model call in the runtime. The GUIDE replay still used misleading “Let me click” wording, prompting an explicit imperative instruction.
- Offline checks: 188 targeted Python tests passed; launcher bilingual-default/explicit-override check passed without external calls. Provider replays used existing H-only observations, no desktop actions or resource creation. Private evidence remains outside Git.
- Final GUIDE-only replay stayed English but still said “Let me click” despite the explicit imperative rule (7.94 s, 7,100 input tokens). This narration-role defect remains unresolved; actual execution remains correctly gated by the selected mode. No extra repair call or silent language rewrite was introduced.

## 2026-11-08 — Lean H briefing and Voxtral transcription

- Clarified the original Matteo optimization: AX lookup first, visual grounding fallback when no target is found (`d41eaca`); later ambiguous matches use a small text call (`ea57f5c`). V2 reuses that AX reader but its absence of a screenshot fallback is specific to V2, not the entire original harness.
- Reduced system instructions plus H briefing from 2,565 to 540 words (16,936 to 4,058 characters). Kept three product distinctions, the sidebar navigation map, six official documentation URLs and essential action/mode constraints. All 106 observed controls remain available; no page-specific target was hard-coded.
- Real Holo probes, concurrent and without UI actions: English tour returned three valid highlights with 5,212 input tokens / 189 output in 18.04 s; English key request ACT returned valid API keys navigation with 5,150 input tokens / 119 output in 8.16 s. This is another ~33% input-token reduction, not a demonstrated latency win. The tour's introduction was generic; full live quality still requires rehearsal.
- Added Voxtral Mini Transcribe Realtime 3 over WebSocket during recording, with Mini Transcribe 3 as same-provider file fallback. French/English input uses automatic language detection; explicit en/fr settings still pin the language. Provider errors are sanitized, cancellation is bounded and partial output is never accepted as a completed transcript. No audio crosses to Gladia on a Voxtral failure.
- Mistral credentials and provider choice are stored in the private V2 `stt.env` with mode 0600, loaded by the launcher and excluded from Electron. The connected account's model list confirmed both models. Existing callers still default to Gladia unless configured otherwise.
- First smoke samples generated inside the sandbox were empty and therefore did not validate speech recognition. Non-empty macOS-generated samples were then paced at real time: English 3.91 s and French 2.84 s, both transcribed; final-text delay after audio was 1,002 ms and 1,553 ms. English file fallback completed in 717 ms. The French transcript omitted the accent in “où”; no speech-recognition accuracy benchmark is claimed.
- Removed an unnecessary wait for WebSocket closure after the final transcript. Final synthetic English repeat completed 699 ms after audio, with the full expected words. This is not a comparison against Gladia or a measurement on the user's microphone. No user recording was uploaded during these smoke tests.
- Validation: 222 targeted Python tests passed, including provider isolation, realtime event ordering, errors, cancellation, slow connection close, voice command races and coach regressions. Private synthetic audio/probe evidence remains outside Git.

## 2026-11-08 — First tour outline and visits to H Platform sections

- Human reported an acceptable but slow tour, with the first Agents outline missing, and requested opening the presented sections. The live trace had correct sidebar targets for all three points, 5,010 input tokens and 186 output tokens. Its 19.45 s measurement includes initial AX observation through the complete Holo decision; it is not TTFT or GPU-only time. Future records separate observation, model and fresh AX-read latency.
- Reproduced the missing outline offline: an intro without a target leaves a smaller stroke budget, which truncated the next scene's last-drawn outline even at complete reveal. Fixed complete-frame rendering; regression covers three outline styles.
- ACT tours now use one model decision, followed by fresh AX resolution, read-only sidebar navigation and local destination checks for Agents, Sessions and Skills. Narration starts after selection/content-heading evidence, and finishes before the next visit. GUIDE remains highlight-only. Stop/new dictation invalidates queued visits; foreground changes, ambiguous sidebar targets or navigation timeouts pause without repeated clicking.
- Offline validation: 286 targeted Python tests passed, including 39 navigation tests. A test caught and prevented a new empty-speech action-validation defect before deployment. No extra Holo calls occur between points in the synthetic navigation tests.
- Stopped the prior API-key request while awaiting confirmation, preserving its traces; no key was created by this update. Closed the blank form and manually opened Agents through browser UI. Reloaded the owned V2 backend with Voxtral and ACT mode. The new automated tour still needs a live human rehearsal; no success label or latency improvement was inferred from these checks.
- Prepared `docs/holo4-verda-latency-handoff.md` for a separate API H / existing Spark / Verda comparison. No GPU was provisioned and no dedicated-server speedup has been measured.

## 2026-11-08 — Validated tour reuse and autonomous API-key form preparation

- User reported the quick tour worked very well. Its real trace shows three locally verified section visits and completion. Initial timing: 464 ms observation, 19,061 ms Holo request. This confirms the main wait in this sample; it does not establish a general provider benchmark.
- Added a private 24-hour cache for generic welcome tours only, keyed by mode and a model/prompts fingerprint. It stores reviewed speech and semantic section labels/roles; every request resolves fresh sidebar IDs and the runtime still rereads targets before navigation. Targeted/mixed questions, missing/ambiguous sidebars or stale cache entries use Holo normally. Only completed tours are automatically saved. Seeded ACT from the completed, human-approved tour using a synthetic geometry fixture solely for serialization; no synthetic coordinates become runtime evidence. A synthetic cache lookup took 0.12 ms, not an end-to-end voice latency measurement.
- Latest key request was ACT throughout. Holo proposed navigation and opening the form, but our guard confused the list's “Create an API key” button with final credential creation. Added a narrow exception requiring positive API-key-list evidence and no visible form; preserved final confirmation and stale-target checks. Runtime now retains current list/form evidence when rebinding the guard's target ID.
- Tightened prompt: the slider decides who acts even for “show me”; explanations that end a request come after requested navigation; coaching rules in a new Skill are content to write, not a command for Companion to change modes.
- Real Holo calls on synthetic fixtures, concurrency 3, no desktop effects: Cloud → Environments click, 8.10 s; Skill → literal Name typing, 8.33 s. Quota navigated correctly but attributed API-connection counts to the browser plan. A strengthened-provenance replay also confused available slots with the limit. Removed unrelated API quota injection for “my current plan”. The final quota replay chose Billing & Subscription without asserting a number, 9.92 s. These checks validate first decisions only, not complete live workflows.
- Validation: 353 targeted tests passed in 1.54 s; after the quota change, 294 coach-specific checks passed in 0.52 s. API-key opening-vs-submission, reused frame IDs, cache re-grounding without HTTP, TTL, prompt invalidation and interrupt regressions are covered.
- Preserved and stopped the waiting key attempt, loaded the updated owned V2 backend in ACT with Voxtral, and left it ready for the user's next live repetition. No API key or Skill was created by these development checks; no human success labels were fabricated.

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

# Real run log

One line per run that actually drove H on the Mac. Simulated runs do not belong here.

| Date | Who | Scenario | Duration | Outcome (verified / escalated / stopped) | Human corrections | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| 2026-11-07 | Edouard / coding agent | Sonde visuelle Holo3.1 sur une image fictive : 6 bouteilles commandées, 4 reçues | 2 468 ms (requête) | verified : réponse « 2 bouteilles », aucune action desktop | Aucune | 544 tokens entrée, 10 sortie ; test API uniquement, pas une tâche métier complète |
| 2026-11-07 | Edouard / coding agent | Même image fictive, holo4-27b | 3 174 ms (requête) | verified : réponse « 2 bouteilles », aucune action desktop | Aucune | 544 tokens entrée, 10 sortie ; un seul appel, pas un benchmark |
| 2026-11-07 | Edouard / coding agent | Même image fictive, holo4-35b-a3b | 2 386 ms (requête) | verified : réponse « 2 bouteilles », aucune action desktop | Aucune | 544 tokens entrée, 15 sortie ; un seul appel, pas un benchmark |

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

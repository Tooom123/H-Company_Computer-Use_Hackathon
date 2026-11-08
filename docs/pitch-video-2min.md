# H Companion — conducteur de tournage, 120 secondes

Préparé le 8 novembre 2026. **Plan de tournage, pas compte rendu de deux démos déjà réussies.**
Le montage final dure exactement **02:00**, générique compris. Le script anglais ci-dessous
est la version privilégiée **Odoo + Devin**, à utiliser seulement après recette des prises.
H reste le moteur du compagnon ; sa plateforme constitue aussi le parcours de secours.

## Le propos

Une personne bloquée pose sa question, reçoit une indication contextualisée, agit elle-même,
contrôle le résultat, puis partage son retour. L'éditeur retrouve ce qui a posé problème.
Montrer **deux histoires complètes**, pas quatre logiciels ouverts sans résultat observable.
Le produit montré est le coaching GUIDE : ne pas monter des clics autonomes ACT comme s'ils
avaient été effectués par l'utilisateur.

Répartition : **Edouard** présente et pose les questions ; **Matteo** surveille le moteur,
la voix et les preuves de guidage ; **Tom** prépare landing, portail et montage. Une seule
personne pilote le Mac pendant une prise. Filmer l'équipe ensemble à l'ouverture et à la fin.

## Conducteur verrouillé à 02:00

| Début → fin | Durée | Image et action à filmer | Son / preuve à conserver |
| --- | ---: | --- | --- |
| 00:00 → 00:11 | 11 s | Équipe face caméra, Edouard parle ; noms discrets | Bloc A, problème + produit |
| 00:11 → 00:21 | 10 s | Hero animé de Tom : transformation Company → Companion et slogan ; transition vers l'app | Bloc B ; pas de statistiques ou tarifs de la landing |
| 00:21 → 00:52 | 31 s | Odoo : question orale, un repère réellement produit, clic humain, réception restante et quantités lisibles | Bloc C ; garder 2–3 s de réponse réelle du compagnon, sans doublage inventé |
| 00:52 → 01:19 | 27 s | Devin : session de démo, question, guidage, changement proposé et résultat de test effectivement visible | Bloc D ; garder 2–3 s de voix réelle ; aucun merge ni lancement de test |
| 01:19 → 01:36 | 17 s | Tom : document Markdown déjà chargé, dossier du passage, observations et retour humain enregistré | Bloc E ; même identifiant d'essai du début au dossier final |
| 01:36 → 01:54 | 18 s | Matteo face caméra, puis schéma simple : H → éditeur de logiciel → utilisateurs → retour produit/support | Bloc F ; cartouche « Proposed distribution model » |
| 01:54 → 02:00 | 6 s | Équipe puis logo/URL du projet vérifiée avant export | Bloc G ; écran final inclus dans ces six secondes |
| **Total** | **120 s** | **Deux parcours principaux** | **Pas de séquence ajoutée après 02:00** |

Les plans écran peuvent être des extraits de prises plus longues. Conserver la demande,
la consigne, l'action et le résultat dans leur ordre réel. Un saut d'attente porte
« Edited for length » ou l'accélération réelle. Ne pas afficher de chronomètre donnant
l'impression d'une exécution continue si le montage comporte des coupes.
Les deux brèves réponses de l'app passent dans les pauses des blocs C/D ; baisser la
voix off à ces endroits. Ne pas lire la narration et le compagnon simultanément.

## Script oral anglais — 222 mots

La demande entre guillemets est dite par Edouard dans la prise ; ne pas la lire deux fois.
Le commentaire décrivant une réussite ne doit être enregistré qu'après observation du résultat.
Les sons réels de l'app ne sont pas compris dans ce décompte : ils occupent les pauses prévues.

**A — 00:00–00:11**

Powerful software still leaves people stuck. We are Edouard, Matteo, and Tom, and we built H Companion: help, one key away.

**B — 00:11–00:21**

Ask a question by voice. The companion looks at your screen, explains the next step, and keeps you in control.

**C — 00:21–00:52**

In Odoo, one receipt is complete, but some ordered products are still missing. I ask: “Show me what is still to receive, without changing anything.” The companion guides me to the outstanding receipt. I follow the instructions myself. We check the remaining quantities on screen, instead of trusting a completion message.

**D — 00:52–01:19**

Now I am reviewing a Devin session. I ask: “Help me find the proposed changes and the evidence that tests passed.” H Companion shows me where to look. I inspect the changes and the available evidence before making my own decision. Nothing is approved or merged.

**E — 01:19–01:36**

On the company side, support can review the question, the trace, and feedback the user chose to share. Documentation provides context. Unknown outcomes remain unknown, and human feedback stays separate from the agent’s claims.

**F — 01:36–01:54**

Our proposed business model is distribution through software vendors: they provide documentation and offer contextual onboarding, configuration help, and support to their users. We would test usage based plans with real users, and measure adoption, repeat support requests, and churn risk.

**G — 01:54–02:00**

H Companion. Help inside the software you already use.

## Préparer les deux prises réelles

### Odoo : comprendre une livraison partielle

Reprendre [R04](scenarios/odoo-rich-scenarios.md), dont un ancien passage ACT a été
évalué réussi et conforme. Ce résultat ne valide pas notre nouveau parcours GUIDE.
Départ : commande portant exactement la référence fournisseur `DEMO-ACHAT-029`,
dans l'instance enrichie et la société fictive, avec la commande affichée.

La question courte du script se rapporte explicitement à **cette commande**. Le contexte
autorisé indique lecture seule, aucune validation de réception, et laisse le reliquat ouvert.
Preuve à filmer : lien commande → réception terminée → réception restante, produits et
quantités restantes lisibles sur la bonne fiche. Le seed annonçait 9 unités restantes
par ligne ; **relire l'état actuel**, ne pas souffler les nombres au modèle.
Ni nombre de produits ni numéro natif de transfert inventé.

Un utilisateur suit réellement la consigne. Après la prise, recueillir séparément
réussite, utilité et ce qui l'a aidé ; conserver les corrections éventuelles.
Si le routage de la nouvelle app pointe encore exclusivement vers H, Matteo doit
configurer le parcours Odoo puis le tester avant le tournage. Ne pas lancer le
pilote historique ACT pour imiter le coaching.

### Devin : examiner une proposition avant de lui faire confiance

Compte connecté ne signifie pas scénario prêt. Choisir une **session de démonstration
existante** contenant un changement et une sortie de test consultables, idéalement le
dépôt sandbox `Tooom123/hcs-sandbox-fake-crm`. Les notes de Tom indiquent une PR #1
issue d'un essai ; son état actuel et son droit de diffusion restent à contrôler.

Version détaillée pour la répétition :

> Devin says the task is done. Show me the proposed change and the actual test result,
> then help me decide what is still unverified. Do not post a review or merge anything.

Pour la prise courte, préparer la session correspondante et employer la question du
bloc D. Vérifier que « tests passed » correspond à une preuve effectivement présente.
Sinon dire « test results » dans la prise et le script ; ne pas en inventer.
Filmer un changement lisible, le résultat de test existant et au moins une limite
expliquée avec fidélité. La présence d'une PR ne prouve ni tests verts ni merge.
Ne pas déclencher **Analyze, Test app, Approve ou Merge**, ni une nouvelle session payante.
Le compagnon observe et guide ; il ne se substitue pas à une revue technique complète.

Repères documentaires : [outils de session Devin](https://docs.devin.ai/work-with-devin/devin-session-tools),
[Devin Review](https://docs.devin.ai/work-with-devin/devin-review). Relever les vrais libellés
dans le compte ; ce conducteur ne suppose aucun bouton non observé.

### Condition de sélection et secours

Avant montage, chaque prise doit montrer une instruction produite par H, l'action humaine,
le bon écran final et une trace associée. Une recette préalable puis la prise réussie
sont nécessaires ; l'objectif de répétabilité reste [trois passages](demo-checklist.md).
Si une prise échoue, conserver l'échec dans les traces et recommencer honnêtement.

Si Devin n'est pas prêt, **remplacer entièrement le bloc D par H**, aux mêmes 27 secondes.
Sur une session H de démonstration réservée, utiliser [HG02](scenarios/h-company-human-session.md) :
retrouver réponse et dernière étape, puis distinguer les faits visibles du statut final.
Ne pas ouvrir les clés API, les coffres ou les autres historiques.

Texte de remplacement D :

> Now I am reviewing an H Company session. I ask: “Show me the answer and the step
> that supports it.” The companion guides me through the actual trace. I can check
> what happened, and what remains uncertain, before deciding whether the task is complete.

Ce remplacement garde le script dans la plage 220–250 mots. Même exigence de prise GUIDE
réussie : l'ancien rapport technique resolved ne prouve pas à lui seul l'utilité du guidage.

**SAP est une autre substitution possible, pas un troisième parcours.** Si une recette
GUIDE réelle réussit, remplacer Odoo par l'explication des montants de `HOLO-1107`
([S03](sap-trial-handoff.md)) : valeur nette, valeur effective et conditions de paiement.
Le brouillon préparé est réel, mais aucun succès Holo SAP n'est établi dans ce handoff.
Ne jamais cliquer Order ; ne pas présenter le trial Fiori comme un ancien SAP GUI.
Réécrire et chronométrer seulement le bloc C, en gardant sa fenêtre de 31 secondes.

## Plan entreprise et limites des promesses

Le portail réellement présent expose import Markdown, recherche lexicale BM25, sessions,
captures autorisées, revues et labels distincts. Montrer un dossier autorisé et correctement
rattaché, pas des exemples simulés présentés comme de vrais utilisateurs. Si le retour vocal
n'est pas encore enregistré, le recueillir ; ne pas ajouter un faux label pour le tournage.
Le portail local peut se filmer sur `http://127.0.0.1:8771/company/live` et
`/company/documents` ; ces URL ne sont pas une version publique destinée au jury.

Le GTM proposé est **B2B2C** : H vend avec un éditeur, qui distribue l'assistant dans
son parcours produit et fournit documentation, version, rôle et permissions.
Premier pilote : un logiciel, un persona, quelques parcours, et un groupe de test consenti.
À tester commercialement : forfait éditeur + volume d'assistance, offre entreprise
avec déploiement dédié ; pas de tarifs inventés ni de vente conclue annoncée.

Cas d'usage à expliquer en entretien, sans les faire passer pour tous validés :
onboarding adapté au rôle, configuration sous-utilisée, découverte des nouveautés,
diagnostic et escalade, retours produit, friction et risque de départ. Recommandation
de plan ou geste commercial : proposition soumise aux règles de l'éditeur et à une
validation humaine, jamais réduction attribuée automatiquement dans cette démo.
Le RAG hybride, l'adaptation LoRA et une baisse du churn restent des pistes, pas des résultats.

La landing de Tom donne l'identité visuelle : filmer son **hero**. Son texte
Ask/Approve/Act décrit aussi la variante autonome, et les exemples « 6 emails / 3 days »,
« unlimited », prix et « verified every time » ne sont pas des résultats de notre campagne.
Éviter ces sections dans ce montage GUIDE ; ne pas déclencher le checkout.

## Ce que l'on peut chiffrer, à part de la promesse produit

La version principale du script ne contient aucun résultat chiffré. Pour un jury technique,
un insert optionnel de **4 s à l'intérieur du bloc E**, sans rallonger le film, peut montrer :

> Window crop: 1,816 → 1,286 input tokens (−29%). One fixed public page; five repeats per condition.

Source : [microbenchmark Holo4](holo4-latency-window-benchmark-2026-11-08.md).
C'est une image de documentation publique dans un bureau synthétique, pas un test de coaching.
Le centre prédit reste dans la cible, mais cela ne valide pas une tâche utilisateur.
Ne pas annoncer « DGX rend l'app trois fois plus rapide » : le premier fragment arrive
plus tôt, tandis que le JSON complet est proche entre fournisseurs. Crop et DGX ne sont
pas activés dans l'app du seul fait de ce benchmark.

Le [Vision Lab](point-projet-et-choix-demo-2026-11-07.md) donne un autre résultat,
distinct : tête à cinq zones, 18/21 crops contenant la cible entière, 2/30 replis,
40 % de surface moyenne conservée sur un participant et un parcours. Ce n'est pas
« 60 % de tokens économisés ». Garder ce laboratoire pour les questions ou une vidéo annexe.

Matteo annonce de nouveaux repères via **AX** et de la transcription en direct sur le
dernier code de l'équipe ; intégration en cours au moment de ce conducteur. Leur présence
dans le code ne prouve pas encore une meilleure précision ni une meilleure latence.
Filmer la version effectivement lancée et noter sa révision dans le journal de prise.

## Tournage pratique cette nuit

1. **Figer les prises.** Matteo contrôle version, source de connaissance, mode GUIDE/autonomie 0,
   micro, voix et Stop. Edouard prépare les deux pages de départ ; Tom prépare les dossiers portail.
   Vérifier que la voix choisie est autorisée ; une voix clonée ne remplace pas une réaction réelle.
2. **Enregistrer chaque écran intégralement**, avec audio système et micro séparés si possible.
   Cadrage 16:9, texte lisible, notifications fermées ; comptes de démo uniquement. Ne pas capturer
   login, clé, cookie, gestionnaire de mots de passe ou données hors périmètre.
3. **Valider puis enregistrer le feedback.** Noter logiciel, session_id, révision, état final,
   corrections et accord de diffusion dans un journal privé. Conserver les rushes privés ;
   ne pas les commiter. Pas de feedback positif imposé au testeur.
4. **Filmer caméra et landing en parallèle de la préparation**, pas avec deux agents contrôlant
   le Mac de démonstration. Garder le cadrage et la lumière identiques pour l'introduction et la fin.
5. **Monter sur les sept créneaux**, garder les clics et preuves décisifs à vitesse normale,
   sous-titrer en anglais, signaler coupes et accélérations. Si nécessaire, raccourcir une pause
   ou une phrase plutôt que rendre une preuve illisible.
6. **Contrôler l'export** : à 30 images/s, **3 600 images = 120,000 s** ; vérifier aussi la durée
   réelle du fichier, sans silence audio résiduel ni noir après l'écran final. L'équipe regarde
   une fois le film sans commentaire pour vérifier que problème, action humaine et résultat se comprennent.

**Blender reste une extension native optionnelle**, à évoquer en questions : montrer comment
trouver un réglage dans un logiciel créatif. Aucun nouvel agent, compte ou développement Blender
n'est nécessaire pour ce film. Ne pas afficher « works with Blender » sans essai réel.

Pour enregistrer la fenêtre Electron, démarrer cette prise avec `HCS_APP_CAPTURABLE=1` : la nouvelle interface est autrement protégée contre la capture. Ce choix de tournage ne prouve pas l’exclusion de l’interface dans une session normale ; rétablir la protection après la prise.

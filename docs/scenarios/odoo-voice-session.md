# Recette vocale Odoo — dix scénarios

Guide de séance du 7 novembre 2026 pour le pilote vocal implémenté dans la route
Electron `#voice`. La demande orale, sa correction, l’approbation du plan, le
feedback et l’export sont reliés au backend. Cette intégration ne signifie pas que
les dix scénarios ont déjà été réalisés et évalués par un utilisateur.
Le [guide de lancement](../../pilot/README.md) décrit sa configuration.
Les critères de correction et les procédures se trouvent dans
[la recette opérateur](odoo-scenarios.md). Ne pas lire leurs réponses attendues au
modèle pendant une demande de lecture.

## Avant de commencer

Ouvrir [Odoo démo](http://holo.localhost:18090/web/login) sur la société
**HACKATHON — Boutique Démo — DONNÉES FICTIVES**. Le Mac reste consacré à cet essai :
un seul humain ou agent agit à la fois. La préparation de la base et le contrôle de
son état se font avant l’enregistrement du parcours.

Ce pilote utilise uniquement **l’agent agit et tu observes**, avec **le desktop
plein écran** et `holo4-35b-a3b`. Les zones du Vision Lab ne sont pas intégrées à
ce parcours. Ce lot établit d’abord une référence de fonctionnement du moteur.

Sélectionner explicitement le numéro du scénario avant de parler. La transcription
ne doit pas pouvoir sélectionner une procédure plus large. Pour les scénarios
05–10, l’opérateur réserve une référence libre et l’app conserve **la même référence
de passage**. Dire « la référence du passage » doit désigner cette valeur affichée
et confirmée ; ne pas en inventer une à chaque demande.

## À chaque scénario

1. Sélectionne le scénario, clique **Dicter ma demande**, prononce la demande
   ci-dessous, puis clique **Terminer**. L’enregistrement s’arrête aussi à 60 secondes.
2. Relis la transcription, en particulier les noms, quantités et références.
   Corrige-la avant de confirmer. Le texte brut et la version corrigée sont conservés
   séparément ; le modèle reçoit la version confirmée.
3. Clique **Préparer le plan**, puis relis son périmètre. Place Odoo derrière le
   panneau et clique **Approuver et observer Odoo** : le panneau se masque et
   l’exécution démarre après trois secondes. Odoo doit être visible à ce moment.
4. Observe l’exécution. Si tu interviens, dis-le dans le feedback. En cas de problème,
   utilise **⌘⇧.** pour demander l’arrêt et attends sa confirmation avant de reprendre
   les commandes.
5. À la fin, le panneau revient. Clique **Dicter mon retour**, puis **Terminer**.
   Relis la transcription, choisis séparément réussite et utilité, puis clique
   **Enregistrer mon retour**. Attends **Retour enregistré avec cet essai.** avant
   de continuer. Un retour non confirmé n’est pas une validation utilisateur.

Le fournisseur de transcription est affiché dans l’app : Gladia si configuré,
sinon Whisper local. Avec Gladia, l’audio lui est transmis. Une copie de l’audio
et sa transcription sont conservées dans le dossier privé du pilote.

Ne pas rejouer automatiquement une étape qui crée ou valide un document : une
réponse incertaine exige d’abord de relire l’état existant.

## Les demandes à dire

### 01 — Lire un produit

> Je débute dans Odoo. Retrouve Holo Gingembre 33 cl, référence HACK-GING-033. Ouvre sa fiche et indique-moi son prix de vente et sa quantité en stock. Ne modifie rien et laisse les deux valeurs visibles.

### 02 — Comparer les stocks

> Compare les quantités en stock de Holo Gingembre 33 cl, Holo Pomme 75 cl et Holo Hibiscus 33 cl. Quel produit a le stock le plus faible ? Montre-moi où tu as trouvé les quantités, sans rien modifier.

### 03 — Retrouver un fournisseur

> Retrouve le contact de Fournisseur Holo Démo depuis Achats. Indique son adresse e-mail et laisse sa fiche ouverte. N’envoie aucun message.

### 04 — Traiter une référence introuvable

> Cherche exactement la référence HACK-INCONNU-999 dans les produits. Si tu ne la trouves pas, explique ce que je dois vérifier. Ne crée aucun produit et ne choisis pas un article ressemblant.

### 05 — Préparer un brouillon

> Prépare une demande de prix pour six Holo Gingembre 33 cl à Fournisseur Holo Démo, à quatre euros pièce. Utilise la référence du passage comme référence fournisseur. Enregistre le brouillon et montre le total. Ne confirme pas la commande et n’envoie pas d’e-mail.

### 06 — Confirmer la commande

> Reprends le brouillon portant la référence du passage et confirme cette commande. Ne réceptionne rien pour l’instant. Lis ensuite la quantité en stock de Gingembre et explique la différence entre une commande confirmée et une livraison reçue.

### 07 — Recevoir une partie de la livraison

> Sur la commande du passage, seulement quatre bouteilles sur six sont arrivées. Réceptionne ces quatre unités et conserve le reste en attente. Ne crée pas de nouvelle commande et ne change pas la quantité commandée.

### 08 — Comprendre ce qui reste à recevoir

> Sur cette commande, montre les réceptions et explique combien de bouteilles ont été reçues et combien restent à recevoir. Ouvre le reliquat correspondant, mais ne le valide pas.

### 09 — Recevoir le reliquat

> Les deux bouteilles manquantes sont arrivées. Termine la réception du reliquat existant de la commande du passage, sans créer une nouvelle commande ni une réception indépendante. Lis ensuite le stock de Gingembre.

### 10 — Faire le bilan

> Fais le bilan de la commande du passage : quantité commandée, montant et répartition des réceptions. Vérifie l’absence de doublon de commande avec cette référence. Donne aussi les stocks actuels de Gingembre, Pomme et Hibiscus, sans rien modifier.

## Ordre et état à respecter

| Scénarios | Dépendance avant de continuer |
| --- | --- |
| 01–04 | Session connectée, catalogue de référence contrôlé ; aucune mutation métier |
| 05 | Référence réservée et absente des documents ; base initiale contrôlée |
| 06 | Un seul brouillon enregistré par 05, contenu relu |
| 07 | Commande de 06 confirmée ; aucune réception déjà validée |
| 08 | Réception partielle de 07 vérifiée ; reliquat ouvert |
| 09 | Même état partiel encore valide ; reliquat identifié sans ambiguïté |
| 10 | Réception du reliquat de 09 vérifiée ; documents liés conservés |

Si une étape n’est pas vérifiée, la suivante reste bloquée. L’opérateur examine
le résultat avant de reprendre ; l’agent ne répare pas la base en arrière-plan.
Le cas 04 peut être une réussite de support lorsqu’une recherche valide établit
l’absence de la référence et que l’explication est correcte.

## Feedback oral après chaque demande

> J’ai observé [tout le passage / une partie / pas le passage]. Pour moi la tâche est [réussie / partielle / échouée / je ne peux pas juger]. L’aide était [utile / peu utile / je ne peux pas juger], parce que… J’ai dû intervenir [aucune fois / en faisant…]. Ce que j’aurais voulu à la place : …

La réussite et l’utilité sont deux questions différentes. Exemple : « La tâche a
l’air réussie, mais je n’ai pas regardé » conserve un résultat utilisateur **non
évalué**, même si la vérification objective a réussi. Ne pas transformer une
transcription hésitante en validation certaine. La personne confirme les labels
avant leur enregistrement ; le verbatim reste disponible pour les relire.

## Ce qui constitue la trace labellisée

Chaque épisode relie le numéro de scénario à sa procédure exacte, à une session
app et aux sessions H d’action et de vérification. Conserver le modèle/version,
mode, rôle, texte vocal brut puis confirmé, paramètres confirmés, version du YAML,
horodatages d’approbation et de fin, références d’images et d’événements, usage et
durées réellement rapportés. Documenter toute intervention ou relance.

Conserver séparément : déclaration de l’agent, verdict et preuves du vérificateur,
contrôle indépendant de l’opérateur, avis utilisateur et utilité. Un succès annoncé
ne remplace pas une preuve ; un désaccord ne doit pas écraser le verdict original.
La sauvegarde du feedback est confirmée par le backend. Le pilote conserve les
enregistrements dans `audio/`, les demandes, événements, rapports et labels dans
`episodes/`, puis les exports des sessions H dans `archives/`, sous
`~/Library/Application Support/HCompanionResearch/voice-pilot`.
L’export est asynchrone : son état doit être **complet** avant de considérer
l’archive récupérée. Un retour enregistré peut précéder la fin de cet export.

Les épisodes 05–10 partagent un `workflow_id` et une référence de passage. Les
regrouper dans le même lot d’entraînement ou d’évaluation. Dix demandes liées sur
une base préparée constituent un **pilote de développement**, pas un benchmark
représentatif d’Odoo entier. Garder ensuite des variantes inédites pour l’évaluation.
Les erreurs et escalades restent dans le journal, et seules des traces relues sont
candidates à l’entraînement. L’accord de réutilisation pour l’entraînement reste
distinct du feedback d’utilité et de l’envoi au support.
Les exports portent `ready_for_sft=false` : il faut encore vérifier les preuves,
sélectionner les traces et les convertir au format d’entraînement. L’audio et un
label de réussite ne constituent pas, seuls, une démonstration d’actions correcte.

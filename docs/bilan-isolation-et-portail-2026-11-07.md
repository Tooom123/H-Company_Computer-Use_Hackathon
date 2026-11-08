# H-Companion — navigateur isolé et portail entreprise

Point vérifié le 7 novembre 2026. Le socle est livré au commit `e127f4e`, puis
la navigation ciblée corrigée en v4 (`fab4527`), dans la
[PR de travail #4](https://github.com/Tooom123/H-Company_Computer-Use_Hackathon/pull/4).
**Dix scénarios v3 et deux retests v4 sont terminés, archivés et revus.** La série
v3 compte **3 réussites, 3 résultats partiels et 4 échecs** selon la revue IA.
Les deux retests v4 restent partiels. Aucun retour humain n’est inventé.

## Ce que l’équipe peut utiliser

- **Un navigateur isolé par worker.** Chrome fonctionne sans fenêtre visible,
  avec son propre profil, son canal H et des captures limitées au viewport Odoo.
  Le moteur Holo4 de Matteo choisit les actions ; le Mac reste disponible. Chaque
  épisode repart du CRM, puis acteur et vérificateur partagent le même onglet.
- **Une documentation locale versionnée.** Les fichiers Markdown sont découpés
  et recherchés par BM25. Les passages pertinents sont ajoutés automatiquement
  au contexte de chaque tentative, avec leurs sources et empreintes. Les traces
  distinguent cet ajout automatique d’un appel volontaire à `lookup_docs`.
- **Un portail entreprise à trois pages.** Configuration du périmètre en lecture
  seule ; import de documentation et recherche sourcée ; sessions avec rapport
  moteur, revue IA et feedback humain séparés. L’import est bloqué pendant une
  session. Les essais simulés et en quarantaine sont exclus des indicateurs de
  résultat ; les échecs et arrêts terminés restent dans les dénominateurs.
- **Des traces privées exploitables.** Demande, version du corpus, résultats,
  diagnostics et archives H sont conservés séparément. Une tentative défectueuse
  n’est pas remplacée par son retest. Aucun feedback humain n’est généré par le batch.

**500 tests automatisés passent**, complétés par la vérification visuelle du
portail avec les vrais rapports. Ce sont des contrôles d’intégration ; les résultats
métier mesurés sont détaillés ci-dessous.

## Ce que cela ne démontre pas encore

La recherche est **lexicale**, pas hybride. Fournir un extrait au modèle ne prouve
ni qu’il l’utilise correctement, ni qu’il améliore le résultat : il faudra comparer
les conditions avec et sans documentation sur des tâches réservées à l’évaluation.

Le mode **Guide-moi** est désactivé dans ce benchmark : l’utilisateur ne peut pas
suivre une fenêtre invisible. Les essais humains de coaching restent un parcours
distinct. Ce lot ne mesure ni l’utilité ressentie, ni les gains Vision Lab en tokens
ou latence. Il ne constitue pas une validation de LoRA ; aucun entraînement n’est
à présenter comme accompli.

Le portail sert une seule entreprise et un seul worker. Deux workers ont des
racines privées et des ports distincts, mais utilisent la même base Odoo. Le
périmètre est la lecture métier ; l’ouverture du chatter peut marquer les
notifications du compte fictif comme lues, exception explicite de v3. Les gardes
ne remplacent pas un rôle Odoo réellement limité à la lecture. Un profil Chrome
distinct n’est pas une sandbox du système d’exploitation.

## Résultats v3

Campagne du 7 novembre, **23:25–23:44 Europe/Paris**, sur deux workers. Les résultats
proviennent des archives et d’une revue IA indépendante ; ils restent à relire
par un humain. Le respect du périmètre décrit les actions et origines observées,
sans garantir l’exécution de toutes les consignes ni l’absence de toute mutation
possible. Les 15 contrôles de fixture des deux campagnes et retests concordent
avec le baseline. Ces contrôles couvrent les champs suivis, pas un diff intégral.

| Cas | Parcours | Moteur | Revue IA métier / périmètre | Durée / usage H | Feedback humain |
|---|---|---|---|---|---|
| R01 | Opportunité CRM Maison Aube | Escaladé | Partiel / conforme | 62,4 s · 110 676 / 4 337 | Non recueilli |
| R02 | Tâches en retard | Escaladé | Échec / conforme | 153,4 s · 688 399 / 7 529 | Non recueilli |
| R03 | Achat partiellement reçu | Résolu | Réussi / conforme | 147,4 s · 345 059 / 8 825 | Non recueilli |
| R04 | Reliquat de réception | Escaladé | Partiel / non conforme | 363,2 s · 920 338 / 31 626 | Non recueilli |
| R05 | Nomenclature d’un coffret | Résolu | Réussi / conforme | 51,8 s · 92 753 / 2 342 | Non recueilli |
| R06 | Devis existant | Escaladé | Partiel / conforme | 246,8 s · 921 139 / 13 497 | Non recueilli |
| R07 | Facture brouillon | Escaladé | Échec / conforme | 154,8 s · 692 197 / 7 222 | Non recueilli |
| R08 | Note de frais | Escaladé | Échec / conforme | 177,3 s · 681 253 / 8 103 | Non recueilli |
| R09 | Demande de maintenance | Résolu | Réussi / conforme | 53,6 s · 79 151 / 2 771 | Non recueilli |
| R10 | Rendez-vous calendrier | Escaladé | Échec / conforme | 101,0 s · 263 926 / 7 397 | Non recueilli |

Usage : tokens d’entrée / sortie retournés par H pour l’acteur et le vérificateur,
en ne sommant que le statut final de chaque session H. Cache et raisonnement sont
conservés séparément dans le bilan privé. Durée : approbation jusqu’au rapport,
hors préparation du navigateur et téléchargement des archives.
La série v3 totalise **4 794 891 tokens d’entrée, 93 649 de sortie et 0,7302 USD
rapportés par H**. Ce coût déclaré ne représente pas une facture vérifiée ni les
coûts d’hébergement, de transcription ou d’évaluation. Aucun gain documentaire
causal n’a été mesuré : tous ces essais utilisent le même corpus.

## Retests et apprentissages

La v4 (`fab4527`) autorise seulement deux actions de consultation Odoo que notre
garde bloquait : ouvrir les réceptions et ouvrir les factures. Le premier retest
R04 atteint le bon reliquat et le lien avec la réception terminée en **61,2 s**,
contre 363,2 s dans l’essai v3 défectueux. Le moteur le valide, mais la revue garde
un résultat **partiel** : l’acteur oublie d’énumérer les produits. Ce retest consomme
140 369 tokens d’entrée et 3 385 de sortie. Il ne remplace pas le résultat v3 et
ne mesure aucun gain de recadrage ou d’apprentissage du modèle.

Le retest R07 passe d’un échec à un résultat **partiel** : client, état Brouillon
et total 99,40 EUR sont retrouvés dans une liste, mais la facture n’est pas ouverte
et son lien à la vente reste non prouvé. Durée **252,7 s**, 803 767 tokens d’entrée
et 14 263 de sortie. Les deux retests ajoutent 0,1500 USD rapportés par H. Ils restent
des essais distincts, sans retour humain ni autorisation automatique d’entraînement.

Points précis à traiter ensuite : R01 confond un bouton « Terminé » avec l’état
d’une activité ; R02 échoue à isoler le projet ; R06 reste sur la liste sans ouvrir
la fiche ; R08 ne charge pas Notes de frais ; R10 confond la vue calendrier du CRM
avec l’application Calendrier et conclut à tort à l’absence du rendez-vous.
La recherche BM25 injecte bien les extraits dans H, mais sélectionne des
sections hors sujet sur le devis. Le moteur interprète aussi mal certaines réponses
brutes `result=partial`. Enfin, le vérificateur peut manquer une valeur hors viewport
ou valider trop largement à partir d’une fiche liée. Ces défauts doivent rester
distingués des réponses correctes et de l’utilité ressentie par l’utilisateur.

## Répartition proposée pour la suite

| Responsable | Prochain chantier | Résultat attendu |
|---|---|---|
| Matteo | Stabiliser acteur/vérificateur et les outils navigateur à partir des traces | Échecs explicables, réponses fidèles, aucun abandon silencieux |
| Tom | Faire évoluer le portail et les cas support | Synthèse des problèmes récurrents avec provenance, labels distincts et visibilité de la quarantaine |
| Edouard | Piloter scénarios, revue et repasse humaine | Choisir les parcours de démo, recueillir l’utilité réelle et préparer une comparaison documentaire contrôlée |

Décision commune après la campagne : prioriser une démo d’assistance fiable, puis
choisir entre coaching visible, comparaison documentaire et nouvelle expérience
Vision Lab. La préparation d’un jeu LoRA vient après revue, nettoyage et séparation
des données d’entraînement et de test.

**Prochain passage recommandé : R05, puis R09 et R03 avec un utilisateur.** Ces
trois parcours ont une réussite complète dans la série. La repasse doit vérifier
que l’aide est compréhensible et utile, pas seulement que l’agent sait exécuter.
Corriger ensuite le chargement des fiches Ventes/Notes de frais, le parsing des
réponses partielles et la sélection documentaire avant d’élargir le benchmark.

## Reprendre sans reconstruire le contexte

Depuis la racine `h-companion`, avec un environnement Python installé et les
variables locales préparées hors Git :

```sh
"$HCOMPANION_PYTHON" scripts/run-voice-pilot.py \
  --environment rich --transport browser \
  --browser-access-dir "$HCOMPANION_ACCESS_DIR" \
  --private-root "$HCOMPANION_WORKER_DIR" --port 8767
```

Le portail est accessible sur `http://127.0.0.1:8767/company` avec l’authentification
privée du worker. Ne pas placer les accès, tokens ou archives dans le dépôt. Pour
un second worker, changer **à la fois** la racine privée et le port. Le mode
`--without-docs` permet de préparer la comparaison sans documentation ; `--mock`
sert uniquement aux vérifications simulées.

- [Installation, règles et procédure du navigateur isolé](isolated-browser-pilot.md)
- [Les dix demandes Odoo et leurs critères](scenarios/odoo-rich-scenarios.md)
- [Protocole de revue indépendante](scenarios/rich-agent-evaluation.md)
- [Corpus fonctionnel Odoo 20](knowledge/odoo-rich.md)
- [Vision produit et choix de démo](point-projet-et-choix-demo-2026-11-07.md)

Les liens de cette note visent la branche de travail contenant le pilote. Avant
une publication sur `main`, vérifier que les fichiers liés y sont présents.

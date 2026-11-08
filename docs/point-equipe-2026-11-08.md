# H-Companion — point équipe du 8 novembre 2026

H-Companion doit aider une personne à utiliser un logiciel : montrer la prochaine
action, attendre l'utilisateur, vérifier l'écran et remonter les difficultés au
support. Les tests autonomes actuels évaluent les capacités nécessaires à ce
guidage ; ils ne démontrent pas encore son utilité pour une personne.

## Ce qui fonctionne et où le consulter

- Le laboratoire vision a testé une politique tête à cinq zones : sur le parcours
  42 rapporté par Edouard, 18/21 crops contiennent la cible entière, 2/30 captures
  sont des replis plein écran et la surface détaillée moyenne est de 40 %.
  Ce résultat géométrique individuel ne mesure ni les tokens économisés ni le
  succès d'une tâche métier.
- Les essais Odoo peuvent utiliser des navigateurs isolés sans immobiliser le Mac.
  La série enrichie de dix cas a obtenu trois réussites, trois résultats partiels
  et quatre échecs après revue IA ; deux retests restent partiels.
- La connexion H par Google/SSO fonctionne dans le cloud grâce à un profil dédié
  réduit aux cookies H. Le profil, les secrets et les captures restent hors Git.
- La tour de contrôle affiche questions, événements, captures autorisées,
  réponses, revues IA et feedback humain. Son style reprend la homepage de Tom.
  L'import Markdown et la recherche lexicale BM25 sont disponibles ; ce n'est
  pas encore une recherche hybride.
- L'app de coaching H est lancée localement en mode GUIDE : Holo4, onze documents
  H chargés, transcription Gladia configurée, autonomie zéro et
  `observe_only=true`. ElevenLabs n'est pas configuré : aucune réponse vocale
  de synthèse n'est disponible dans cette session. Le premier échange vocal
  guidé réel et son feedback utilisateur restent à faire.

Sur le Mac d'Edouard : [tour de contrôle](http://127.0.0.1:8771/company/live),
[sessions](http://127.0.0.1:8771/company/sessions),
[documents](http://127.0.0.1:8771/company/documents).
Ces adresses sont locales ; un collègue ne peut pas y accéder à distance avec
son propre `127.0.0.1`. Le lancement et l'authentification du portail sont décrits
dans [le mode d'emploi](native-cloud-pilot.md).

Le runtime du test humain utilise séparément le contrôle sur `127.0.0.1:8780`
et le backend sur `127.0.0.1:8781`. Les commandes de lancement et dix questions
progressives figurent dans le [parcours humain H](scenarios/h-company-human-session.md).
Le premier essai de dictée a révélé un conflit avec `⌘H`, qui masque la fenêtre
active sur macOS et a laissé l'enregistrement bloqué. Le lanceur utilise
désormais **Ctrl+Maj+H** ; le redémarrage et le premier échange guidé complet
restent à valider. Le défaut historique du CLI seul reste `⌘H`.

## Campagne H — résultats des essais autonomes

Audit des archives privées du 8 novembre : **13 exécutions, dix cartes HC01–HC10**.
Les six cas documentaires ont été lancés en parallèle ; après une sonde de
connexion, trois cas authentifiés ont tourné simultanément. Le plafond de dix
est disponible côté compte, mais dix simultanés n'ont pas été testés.

| Mesure | Valeur observée |
| --- | ---: |
| Archives complètes | 12/13 |
| Revues IA métier | 12 partielles, 1 indéterminée (ancienne connexion bloquée) |
| Périmètre respecté | 11/13 |
| Quarantaines | 2 : HC08 et HC10 |
| Feedback humain de cette campagne H | 0 |
| Trajectoires sélectionnées pour SFT | 0 |

HC08 a un résultat d'outil tronqué chez H : une nouvelle tentative de téléchargement
ne suffit pas à rendre cette archive complète. HC08 et HC10 restent conservés
privément, mais leur contenu est masqué dans le portail après des écarts au
protocole. Les quinze fiches historiques Odoo portent le portail à 28 fiches avant
les retests ; le compteur exclut les deux quarantaines. **Terminé ne veut pas dire
réussi.** Les chiffres détaillés et les identifiants figurent dans le
[journal](test-log.md).

Chaque épisode conserve requête/configuration, événements, images, rapport et
archive H avec manifeste. `agent-review.json` est une revue IA distincte de la
déclaration de l'acteur ; `labels.json` n'est créé que pour un retour effectivement
fourni par une personne. Le consentement et la sélection pour entraînement sont
séparés. Aucun label humain n'est déduit de nos revues.

## Corrections et intégration

Les campagnes H passent directement par le runner cloud natif en mode ACT.
Elles ne passent pas par la boucle GUIDE de Matteo. Les corrections prioritaires
sont donc :

1. **Harness cloud** : surveiller les sessions/pages autorisées par cas, détecter
   les outils exclus et arrêter les boucles d'erreurs de schéma ; conserver la
   preuve et la raison d'arrêt. Une détection après événement n'est pas un
   blocage réseau avant action.
2. **Contexte H et vérification** : séparer observation, hypothèse et inconnu ;
   ne pas prendre l'heure de création pour une durée, ni déduire des tokens d'un
   compteur visuel. Un statut Interrupted peut provenir de notre fermeture après
   réponse et ne démontre pas une panne métier.
3. **App de l'équipe** : tester maintenant un parcours GUIDE réel avec une
   personne, sur la version intégrée. Conserver le comportement
   « vérification indisponible = inconclusif » et enregistrer séparément son
   retour sur la réussite et l'utilité de l'aide.

Le dernier `origin/main` de l'équipe, `1f35eef`, a été intégré à notre branche
par le commit de fusion `b4ad15e`. Le raccordement du coaching humain H est
commité dans `4626800`. **75 tests ciblés et six tests desktop passent** ; une
vérification de l'interface avec réponses simulées n'a relevé aucune erreur
JavaScript. Ces contrôles ne constituent pas un essai vocal humain. Le total
historique de 838 tests ne doit pas être présenté comme la couverture de cette
nouvelle fonctionnalité.

La [PR n°4](https://github.com/Tooom123/H-Company_Computer-Use_Hackathon/pull/4)
regroupe les pilotes et le portail. Elle n'est pas fusionnée ; les nouveaux
commits locaux ne sont pas encore poussés. La résolution locale des conflits
ne met donc pas encore à jour son état distant. Après publication, obtenir la
revue d'un équipier avant fusion, conformément à `AGENTS.md`.

## Passage à SAP et répartition proposée

Les [douze cartes SAP](scenarios/sap-scenarios.md) sont rédigées. Elles ne sont
pas douze tests déjà prêts ou exécutés. SAP01–04 ont une cible observée ; les
autres nécessitent des contrôles ou des données de départ supplémentaires.
L'authentification SAP et le catalogue exécutable restent à raccorder au pilote.

Commencer par SAP01 (retrouver le brouillon), SAP05 (comprendre un filtre), puis
SAP03 (expliquer les montants), **en série sur le même compte** après contrôle
des cibles. Le brouillon et les préférences restent partagés entre navigateurs :
leur isolation ne suffit pas à permettre douze modifications parallèles. Pour
une modification, réserver un brouillon par essai et laisser Order à l'humain.

- **Tom** : revue/intégration portail et remontées support ; catalogue SAP,
  paramètres des cibles et admission des campagnes sans conflit de données.
- **Matteo** : boucle GUIDE de l'app, une instruction puis attente et contrôle
  visuel ; voix, arrêt et retour explicite en cas de blocage. Autonomie zéro pour
  le premier essai de coaching, avec le contrôle `observe_only` actif pour
  empêcher les actions de l'agent, y compris pendant la vérification. Vérifier
  ce comportement sur la première trace humaine.
- **Edouard** : premier parcours vocal H puis feedback oral et labels explicites
  de réussite et d'utilité ; ensuite connexion SAP et vérification des données
  de départ. La compréhension reste une appréciation à demander à la personne.
- **Agents de recherche/test** : revue des traces et archivage en parallèle sans
  piloter le Mac pendant le test humain. Les retests cloud H ne sont pas la
  priorité de cette session.

Priorité de démonstration : une tâche GUIDE utile et vérifiée, sa trace dans la
tour de contrôle, puis le feedback utilisateur. Le fine-tuning vient après la
constitution de trajectoires correctes et d'un jeu d'évaluation séparé.

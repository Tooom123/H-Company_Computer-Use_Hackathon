# Campagne Odoo enrichie : exécution et revue IA

Le 7 novembre 2026, Édouard a demandé une série séquentielle des scénarios,
évaluée par l’agent de développement, avant sa propre repasse. Cette campagne
est une séance de développement avec revue IA, pas un test utilisateur ni un
benchmark tenu à l’écart des ajustements de prompts.

## Exécution

Le compte H expose un quota **organisation de 10 sessions simultanées**, confirmé
par `Client.sessions.get_session_quota()` du SDK installé. Ce quota ne fournit
pas dix bureaux : souris, clavier et écran d’un même bridge desktop sont partagés.
La campagne utilise donc un seul épisode à la fois sur le Mac, en plein écran,
avec le moteur `b59ef01`, `holo4-35b-a3b`, l’adaptateur `pilot-bridge-health-v1`
et la fixture Odoo `20261107-v2.1`.

Le script `scripts/run-rich-batch.py` exige une approbation explicite pour le lot
en lecture seule, les IDs R01–R10 et le profil riche. Il attend la fin d’un épisode
avant le suivant, conserve les exports et vérifie le baseline via la commande
privée de statut Odoo. Il n’écrit aucun feedback utilisateur.

Le client Electron peut être fermé pendant ce pilotage ; le serveur reste ouvert.
Le Mac doit afficher la bonne démo, sans autre acteur. Le processus de lot demande
l’arrêt de l’épisode courant s’il reçoit une interruption clavier. Un fichier
`STOP` dans le dossier de campagne demande aussi l’arrêt ; contrôler ensuite que
le moteur confirme son état terminal avant de reprendre les commandes du Mac.

Exemple opérateur, depuis la racine du dépôt, avec un fichier JSON privé contenant
les arguments de la commande SSH `manage.py status` fournie par le handoff :

```sh
python scripts/run-rich-batch.py \
  --private-root "$HOME/Library/Application Support/HCompanionResearch/voice-pilot-rich" \
  --campaign rich-baseline-20261107 \
  --scenarios R02 R03 R04 R05 R06 R07 R08 R09 R10 \
  --approve-read-only \
  --state-check-command /chemin/prive/commande-status.json
```

Le dossier de campagne doit être nouveau. Aucun reset ni correction Odoo ne fait
partie de ce script. Les cas commencent depuis la page laissée par le précédent,
dans la même démo : ce contexte fait partie de la trace. Une future comparaison
contrôlée devra fixer les pages de départ et les dimensions du navigateur.

Le contrôle du baseline compare explicitement `snapshot` / `expected_snapshot`
et `counts` / `expected_counts`. Le code retour de `status` seul ne suffit pas.
Cette empreinte ne couvre pas tous les champs de tous les modules ; conserver
cette limite avec le résultat et compléter par revue des actions et lectures ciblées.

## Trois jugements différents

| Champ / fichier | Auteur et portée |
| --- | --- |
| `report.json`, `verification` | Vérificateur H : postconditions qu’il a pu observer dans ses vues |
| `agent-review.json`, `task_success_agent` | Relecteur IA : demande, réponse finale, actions, images et preuves indépendantes disponibles |
| `labels.json`, `task_success_user` / `useful` | Utilisateur : son appréciation explicite, recueillie séparément |
| `quarantine.json` | Exclusion de la trace ou revue de confidentialité encore nécessaire ; aucun effacement distant implicite |

Ne pas transformer une revue IA en feedback humain. Ne pas écraser le verdict
initial de H lorsqu’une seconde revue trouve un faux négatif. L’utilité pour
l’utilisateur reste inconnue tant qu’il n’a pas donné son avis.

Une revue IA indique `reviewer_type=ai`, sa méthode, les preuves, les limites,
les désaccords éventuels et l’un des résultats :

- **success** : tous les éléments métier demandés sont correctement restitués et étayés ;
- **partial** : bonne progression, mais réponse incomplète ou un critère demandé manque ;
- **failure** : mauvaise fiche, réponse erronée ou absence de résultat ;
- **unknown** : preuves insuffisantes pour trancher.

`scope_compliance_agent` qualifie séparément le respect du périmètre pendant le
parcours. Une réponse métier correcte peut provenir d'une trajectoire contenant
une sortie de périmètre ; elle ne devient pas pour autant une trace propre pour
l'entraînement. Distinguer une simple action dans l'interface du navigateur,
une autre origine réellement visitée et une mutation métier. Une cause ou un
effet non observé doit rester inconnu.

Le relecteur est distinct de l’acteur et de son vérificateur, mais connaît les
attentes du scénario : ce n’est pas une évaluation en aveugle. Il ne déduit pas
la réussite de `resolved` ni de l’affirmation de l’acteur. Il inspecte les captures
pertinentes et peut consulter un oracle en lecture seule de la démo.

Un champ visible dans une capture antérieure peut réfuter un échec du vérificateur
lié à une vue finale défilée. À l’inverse, une information retrouvée seulement par
le vérificateur ne répare pas une réponse finale incomplète de l’acteur.

La revue est stockée à côté de l’épisode et copiée dans son archive. Les données
brutes restent privées ; seuls les résultats agrégés et les changements de
procédure vont dans Git. `human_review_required=true` et `ready_for_sft=false`
restent en place. La sélection pour l’entraînement exige une revue et une
conversion supplémentaires, même lorsqu’un label de tâche est positif.

Les retests du 7 novembre utilisent la garde de bridge v2 (commandes shell et
fichiers bloqués). Après constat d'un premier plan hors Odoo, la série est arrêtée.
La v3 ajoute le contrôle Chrome actif avant les observations et actions ; ses
tests sont hors ligne, sans nouvelle exécution H pour la valider. Ne pas
réétiqueter les anciennes traces v1/v2 comme des traces protégées par v3.

## Itérer sans effacer les échecs

1. Faire un premier passage avec procédures et révisions fixes.
2. Distinguer problèmes de navigation, de réponse, de vérification et d’environnement.
3. Ajouter des indications procédurales utiles, sans fournir les réponses du test à l’acteur.
4. Rejouer les cas concernés sous de nouveaux IDs d’épisode et conserver les deux résultats.
5. Réserver de nouvelles fiches ou variantes pour mesurer la généralisation.

Changer le navigateur desktop pour dix navigateurs isolés constitue une autre
configuration expérimentale. Un navigateur cloud ne voit pas le localhost du Mac ;
il faut lui donner une route vers la démo. Le bridge navigateur local réutilise
un profil et un port par défaut : plusieurs sessions ne suffisent pas à obtenir
l’isolation. Voir la [documentation H du navigateur local](https://hub.hcompany.ai/agents-api/your-browser).

# PRD Assistant client pour logiciels

**Version de travail du 7 novembre 2026 — enrichie avec les réponses de l’équipe**

Une application installée sur le poste accompagne l’utilisateur dans la prise en main, l’usage et le dépannage de son logiciel grâce au computer-use de H. Elle adapte son aide au rôle et à l’objectif déclarés, agit avec l’accord du client et transmet à l’éditeur les difficultés, les résultats et les retours utiles. La vision couvre le support, l’adoption et la réussite client.

Le MVP proposé suit une seule histoire sur un logiciel : aider un persona à réaliser une tâche ou une configuration utile, vérifier le résultat, puis montrer un blocage transmis au support avec le contexte nécessaire. Les autres cas d’usage constituent des extensions du même produit.

## Problème et utilisateurs

Le support doit souvent reconstituer une situation à partir de descriptions incomplètes, de captures isolées et de nombreux échanges. L’utilisateur doit ensuite retrouver les contrôles et appliquer les consignes. L’éditeur dispose de tickets, mais leur contenu ne permet pas toujours de distinguer une confusion d’usage, une configuration incorrecte ou un défaut du logiciel. Au-delà des incidents, des utilisateurs découvrent difficilement les réglages utiles à leur métier ou les possibilités d’une nouvelle version. Ces besoins d’accompagnement et leur fréquence restent à valider avec des clients réels.

**Utilisateur principal :** une personne qui découvre un logiciel, veut mieux l’utiliser ou rencontre un blocage. Elle souhaite atteindre son objectif, comprendre l’aide proposée et garder la maîtrise des changements.

**Utilisateurs côté éditeur :** le support pour traiter les blocages, l’équipe customer success pour accompagner l’adoption, et l’équipe produit pour comprendre les difficultés et les demandes. Les fonctions commerciales deviennent pertinentes si la recommandation d’offre est développée.

**Hypothèse commerciale à valider :** l’éditeur du logiciel fournit l’assistant à ses clients et finance le service. Un pilote auprès d’un seul éditeur précède une offre couvrant plusieurs logiciels.

## Vision et carte des usages

| Usage envisagé | Aide apportée au client | Retour utile à l’éditeur | Place proposée |
| --- | --- | --- | --- |
| Onboarding personnalisé | Demander le rôle et l’objectif, expliquer les étapes pertinentes et aider à la première réalisation. | Étapes difficiles et objectif atteint ou non. | Peut porter l’histoire principale du MVP. |
| Configuration et découverte | Repérer un réglage pertinent pour le besoin exprimé, expliquer son intérêt et le configurer après accord. | Options recherchées, incomprises ou difficiles à régler. | Une tâche réversible dans le MVP. |
| Adoption des nouveautés | Relier une nouveauté documentée à un besoin, puis accompagner sa première utilisation. | Réactions et obstacles rencontrés pendant les sessions accompagnées. | Extension ; scénario possible si la version et la procédure sont connues. |
| Dépannage | Observer, expliquer, agir, vérifier ou transmettre à un humain. | Incident contextualisé et tentatives déjà réalisées. | Cœur du MVP. |
| Bugs et incohérences | Recueillir le symptôme et les étapes permettant de le reproduire. | Signalement qualifié avec preuves disponibles. | Catégorie de remontée ; le bug reste suspecté tant qu’il n’est pas confirmé. |
| Feedback direct | Recueillir et reformuler le retour du client, puis lui permettre de le corriger avant transmission. | Verbatim autorisé, résumé, fonctionnalité concernée et contexte. | Champ simple après l’intervention. |
| Recommandation d’offre | Comparer le besoin exprimé aux capacités et limites des offres de l’éditeur. | Besoin commercial qualifié et recommandation expliquée. | Après le MVP. |
| Insatisfaction et fidélisation | Comprendre la plainte, chercher une solution et, si les règles le permettent, proposer un geste commercial. | Motif d’insatisfaction et action proposée ou demandée. | Après le MVP ; aucune remise ou modification d’abonnement automatique dans la démo. |

La proposition commune est d’aider le client à obtenir un résultat dans son logiciel et de donner à l’éditeur un retour exploitable sur cette expérience. Une recommandation d’offre peut être un plan plus adapté ou moins coûteux ; elle ne doit pas être systématiquement une montée en gamme. Toute remise dépend de critères, plafonds et autorisations définis par l’éditeur.

Le MVP est déclenché par l’utilisateur. Les invitations proactives à découvrir une fonctionnalité et les campagnes liées aux nouvelles versions restent des extensions ; elles ne supposent pas une surveillance permanente du poste.

## Périmètre retenu et hypothèses

| Statut | Élément |
| --- | --- |
| Confirmé | Application téléchargeable, assistance par computer-use H dans le logiciel de l’utilisateur et remontées à l’éditeur. |
| Confirmé | Le client demande de l’aide et approuve l’intervention ; l’agent agit, puis vérifie le résultat. |
| Direction confirmée | En cas d’échec, escalade vers le support ; possibilité ultérieure pour un humain de superviser l’agent. |
| Confirmé | Équipe de trois personnes : Edouard, Matteo et Tom, polyvalents et accompagnés de coding agents ; un Mac disponible, premiers tests joués par l’équipe. |
| Vision élargie | Onboarding par persona, configuration, nouveautés, dépannage, feedback, recommandation d’offre et fidélisation. |
| Proposition pour le hackathon | Un logiciel, un persona, une tâche utile réussie et un blocage escaladé ; macOS en première plateforme. |
| Proposition technique | Interface Electron, composant Python local utilisant le SDK H, modèle hébergé et backend pour les sessions et remontées. |
| Proposition de restitution | Dossiers d’intervention, feedback simple et regroupement des difficultés dans un tableau de bord. |
| Décisions ouvertes | Environnement de test retenu, persona et tâches, attribution finale des responsabilités, niveau d’escalade démontré, destinataires et conservation des données. |

Le nom du produit, la tarification et une version Windows ne conditionnent pas la première démonstration.

## Choix du logiciel de démonstration

**Toporder et Odoo sont les candidats prioritaires ; Salesforce reste une alternative.** Edouard indique avoir accès à Toporder et cite également Odoo. L’équipe peut créer des comptes de test ou une copie ciblée pour la démo. Le choix n’est pas arrêté : il faut retenir un environnement pilotable sur Mac, réinitialisable, avec une tâche connue et des données fictives.

Toporder présente des caisses sur iPad et Android. Il faut confirmer l’accès à un back-office ou à une autre interface utilisable sur Mac avant de retenir ce terrain ; une démo du back-office ne prouverait pas le pilotage de la caisse sur tablette. [Présentation officielle de Toporder](https://toporder.fr/).

**Recommandation de départ : Odoo pour le prototype si un environnement de test est rapidement disponible.** Odoo Online fonctionne dans le navigateur ; sa documentation décrit la duplication d’une base avec une option de test désactivant les actions externes. Cela offre une piste pour rejouer un scénario dans le vrai logiciel. Les droits d’administration, l’hébergement et la version du compte doivent être vérifiés ; une base de test vierge avec données fictives évite de recopier des données clients. [Documentation Odoo Online 19.0](https://www.odoo.com/documentation/19.0/administration/install/online.html).

Salesforce propose des environnements Developer Edition pour expérimenter. Cela en fait une piste si l’équipe n’a pas de compte de test existant, sous réserve de l’activation et de la disponibilité des fonctions nécessaires au scénario. [Environnements de développement Salesforce](https://trailhead.salesforce.com/content/learn/modules/deep-dive-into-salesforce-contracts/create-update-and-manage-contracts-hoc).

Tester un logiciel web depuis l’application desktop reste compatible avec le projet. L’accès à un environnement réel, la répétabilité et la maîtrise du scénario priment sur le choix d’une application native.

**Ordre de préférence proposé :** un environnement de test du vrai logiciel déjà accessible ; puis un nouveau compte de test ; enfin une copie limitée aux écrans et comportements nécessaires. Toporder reste préférable si son accès de test sur Mac et un scénario maîtrisé sont déjà prêts.

Une copie ciblée permet de maîtriser l’état initial, les erreurs et la remise à zéro. Elle doit être présentée comme une application de démonstration inspirée du logiciel : elle valide le fonctionnement sur cette copie, sans prouver la compatibilité avec le produit original. Inutile de reproduire tout un ERP pour tester l’assistant.

Dans les deux cas, H doit réellement observer et agir ; le succès doit être vérifié après l’action. Les scripts de préparation ou de remise à zéro restent distincts de l’exécution montrée. Tester au moins deux variantes de données limite le risque d’un parcours qui ne fonctionne que sur un écran préparé.

## Parcours de la demande au résultat

1. **Démarrer.** L’utilisateur ouvre l’assistant, décrit son objectif ou son problème et identifie le logiciel concerné. Il précise son rôle lorsque cela aide à personnaliser l’accompagnement. L’application indique ce qu’elle peut observer et transmettre, puis vérifie les permissions nécessaires.

2. **Comprendre.** L’agent observe l’état visible et consulte les procédures correspondant au logiciel et à sa version. Il demande une précision si le résultat attendu est ambigu, puis adapte son explication au rôle déclaré.

3. **Proposer et faire approuver.** L’agent présente l’objectif et les modifications prévues. Le client approuve ce périmètre avant toute intervention ; une permission système ne remplace pas cet accord.

4. **Intervenir.** L’agent effectue les manipulations. L’interface affiche son état et permet l’arrêt. Une action qui dépasse le périmètre accepté nécessite une nouvelle décision.

5. **Vérifier.** L’application contrôle la postcondition définie pour le cas. Elle distingue résultat observé, déclaration de l’agent et confirmation éventuelle de l’utilisateur.

6. **Conclure ou escalader.** Si l’objectif est atteint, l’application présente les changements et leur vérification. Sinon, elle indique ce qui reste bloqué et prépare le dossier destiné au support. Une éventuelle reprise par un agent supervisé nécessite une nouvelle autorisation adaptée au périmètre.

7. **Restituer et écouter.** Le client peut confirmer l’utilité de l’aide et ajouter un retour libre. Le compte rendu alimente les dossiers de support et le regroupement des difficultés ; son feedback déclaré reste distinct des interprétations de l’agent.

## Exigences du MVP proposé

| Exigence | Critère d’acceptation |
| --- | --- |
| Déclenchement volontaire | Aucune intervention ne commence avant une demande explicite et l’autorisation prévue. Une permission système absente produit une explication utile. |
| Intervention réelle | H observe et agit dans le logiciel cible. Des entrées différentes produisent des résultats adaptés ; le parcours ne dépend pas d’une animation préenregistrée. |
| Procédure spécialisée | Le cas d’accompagnement et le cas bloqué ont un objectif, des préconditions, des actions autorisées et une condition d’escalade documentés. |
| Arrêt de l’intervention | Le bouton d’arrêt bloque localement les nouvelles commandes et demande l’annulation à H. Un message ultérieur ne relance rien sans nouvelle autorisation. Le délai est mesuré. |
| Vérification de résolution | Un résultat déclaré réussi par l’agent ne suffit pas. La postcondition est observée et conservée dans le rapport. |
| Gestion d’un blocage | L’agent s’arrête à une limite d’essais définie pour le cas, conserve les étapes utiles et indique clairement que le problème reste ouvert. Le dossier précise la décision attendue du support. |
| Compte rendu structuré | Chaque intervention produit un cas lisible : rôle déclaré, objectif, symptôme éventuel, actions, résultat, catégorie, preuves autorisées, feedback et besoin éventuel d’un humain. |
| Personnalisation et feedback | L’aide tient compte du rôle et de l’objectif explicitement fournis. Un retour libre peut être ajouté ; il n’est pas inventé à partir du comportement observé. |
| Regroupement simple | Deux cas similaires sont associés au même problème ; un cas différent reste distinct. Chaque groupe permet de consulter les cas sources. |
| Isolation des accès | Le tableau de bord exige une authentification. Aucun accès public aux traces ni clé H commune intégrée au binaire distribué. |

L’arrêt ne restaure pas les changements déjà effectués. Une interruption réseau empêche l’exécution de nouvelles commandes jusqu’à une reprise explicite.

## Informations remontées au support

Le compte rendu conserve : identifiant du cas, logiciel et version si disponibles, système, rôle déclaré si utile, type de session, objectif, symptôme éventuel, étapes tentées, résultat vérifié, catégorie, cause supposée lorsqu’elle est utile, procédure utilisée, références de preuve et feedback autorisé. Les types de session distinguent onboarding, configuration, support, découverte de nouveauté et feedback ; les intentions commerciales pourront être ajoutées plus tard.

Les catégories proposées sont : **usage, configuration, permissions, données, défaut produit suspecté, problème d’environnement, échec de l’agent, inconnu**. Le statut du cas reste séparé : **résolu, contournement proposé, escaladé, abandonné**.

Le tableau de bord présente les groupes de difficultés, le nombre de cas et d’utilisateurs distincts concernés, les procédures tentées, les résultats vérifiés et les retours exprimés. Il décrit les sessions assistées ; il ne mesure pas tous les usages du logiciel. Une fonctionnalité absente de ces sessions ne peut pas être déclarée sous-utilisée à l’échelle de la clientèle.

**Politique de données à décider :** résumé et étapes par défaut ; captures utiles transmises au support après accord spécifique. Les captures nécessaires à l’inférence H et les preuves conservées pour l’éditeur sont deux usages distincts à expliquer. Le masquage, les destinataires et la durée de conservation restent à fixer avant un pilote réel.

Une observation visuelle ne prouve pas une cause serveur. Les journaux réseau ou applicatifs éventuels nécessitent une collecte dédiée.

## Architecture proposée et limites de H

L’interface desktop gère la conversation, les autorisations, l’état et l’arrêt. Un composant Python local utilise H pour contrôler la machine. Le backend authentifie les utilisateurs, associe chaque session au bon client et stocke les incidents nécessaires au tableau de bord.

H fournit le [contrôle desktop](https://hub.hcompany.ai/agents-api/your-desktop), les [événements de session](https://hub.hcompany.ai/agents-api/sessions/event-object), les [outils personnalisés](https://hub.hcompany.ai/agents-api/custom-tools) et les [réponses structurées](https://hub.hcompany.ai/agents-api/structured-output). La connaissance du logiciel, le classement des incidents et les règles d’accès appartiennent au produit.

Pour le prototype, le SDK desktop peut accélérer l’intégration. Une garantie stricte « uniquement cette fenêtre » nécessite un contrôle effectif des captures et des actions ; une consigne dans le prompt ne suffit pas. La faisabilité de ce contrôle doit être vérifiée avant de le promettre.

Avec un modèle H hébergé, les captures et le contexte sont transmis à H même si la boucle d’agent tourne localement. Une architecture de distribution sans clé d’organisation embarquée, les conditions d’intégration du runtime et les permissions système doivent être validées avant de déployer l’app chez de vrais clients.

La [documentation des résultats](https://hub.hcompany.ai/agents-api/errors) distingue session terminée et succès métier. La [gestion des messages](https://hub.hcompany.ai/agents-api/sessions/send-messages) peut reprendre une session en pause ou terminée : l’application doit conserver son propre état d’autorisation.

## Connaissance du logiciel et personnalisation

Le computer-use permet d’observer et de manipuler une interface ; il ne fournit pas automatiquement les règles métier, l’historique d’usage, le rôle, les droits ou les offres commerciales du client.

Pour le MVP, préparer un dossier de référence limité au logiciel et aux deux scénarios : procédures vérifiées, version, préconditions, actions autorisées, résultat attendu et règle d’escalade. Le rôle et l’objectif viennent du client. Cette base peut rester un petit ensemble de documents ; une synchronisation complète de documentation n’est pas nécessaire à la démo.

Les extensions exigent des sources supplémentaires : notes de version approuvées pour les nouveautés, catalogue et éligibilité pour les plans, politique de remise pour la fidélisation, et données d’usage autorisées pour les recommandations fondées sur l’historique. Le produit doit distinguer information fournie, observation et hypothèse.

## Périmètre exclu de la première version

- Support universel de tous les logiciels et systèmes.

- Surveillance permanente de l’activité du poste.

- Publication simultanée macOS et Windows.

- Réparation autonome du code source du logiciel ou attribution de permissions supplémentaires.

- Paiements, suppressions irréversibles et changements sensibles dans les scénarios de démonstration.

- Apprentissage automatique publié sans validation à partir des incidents.

- Intégrations multiples avec des outils de ticketing.

**Escalade en deux niveaux.** Le socle proposé pour le MVP est un dossier dans le tableau de bord : objectif, état observé, actions tentées, blocage et décision attendue du support. La supervision humaine de l’agent est une évolution souhaitée ; son inclusion dans la démo reste à décider. Un dossier transmis ne doit pas être présenté comme une session de prise en main à distance déjà opérationnelle. L’envoi vers Zendesk, Intercom ou un autre outil dépendra du premier éditeur ciblé.

## Démonstration et critères de réussite proposés

**Cas réussi proposé :** un utilisateur présente son rôle et un objectif concret. L’assistant lui explique une fonction ou un réglage utile, obtient son accord, effectue une configuration réversible et vérifie le résultat. Une même histoire montre ainsi onboarding, découverte et exécution, sans construire trois parcours distincts. Le réglage exact reste à choisir et à valider sur le logiciel accessible.

**Scénario concret proposé si Odoo est retenu :** « Je suis nouveau commercial. Aide-moi à organiser la relance de l’opportunité Acme Démo à la date que je choisis. » Une opportunité fictive existe au départ. L’assistant explique les activités, confirme le titre, la date et le responsable, puis crée une activité de type tâche après accord. La preuve de réussite est sa présence sur la bonne opportunité, avec les bons champs, après réouverture de la fiche. Aucune relance externe n’est envoyée. Les activités liées aux opportunités sont documentées par Odoo ; ce scénario doit encore être essayé sur le compte retenu. [Activités CRM Odoo 19.0](https://www.odoo.com/documentation/19.0/applications/sales/crm/optimize/utilize_activities.html).

**Cas bloqué :** une limite réelle que l’agent doit reconnaître, par exemple une permission manquante. Le dossier transmis permet à un humain de reprendre sans refaire toute l’investigation.

Avant la démo, chaque cas dispose d’un état initial reproductible et d’un résultat attendu. Le cas résoluble doit réussir trois fois consécutivement depuis cet état ; les durées, corrections humaines et échecs sont consignés. Le cas bloqué doit produire une escalade sans fausse annonce de résolution.

Au moins trois sessions de test illustrent le regroupement : deux difficultés similaires et une différente. Toute donnée préparée est identifiée comme donnée de démonstration.

Les mesures techniques sont : proportion d’objectifs vérifiés parmi les sessions tentées, durée de bout en bout, interventions humaines, coût par session et complétude du dossier. Les objectifs de temps et de coût seront fixés après les premiers essais. Les tests joués par les trois membres valident la démo ; l’utilité, la confiance et l’adoption restent à évaluer auprès de vrais clients.

## Ordre de réalisation proposé

1. Choisir l’environnement accessible, le persona, la tâche utile, le blocage et leurs résultats attendus ; préparer les données et la remise à l’état initial.

2. Tester H directement sur ces cas et mesurer les limites techniques.

3. Construire un parcours complet avec interface, intervention, arrêt et vérification.

4. Ajouter le rapport d’incident, l’escalade et le regroupement simple.

5. Vérifier le démarrage depuis l’application empaquetée, les permissions et la répétabilité de la démo.

## Répartition proposée entre les trois membres

L’équipe réunit Edouard, Matteo et Tom, tous polyvalents, avec l’appui de coding agents. Elle dispose d’un Mac et jouera elle-même les scénarios. La répartition ci-dessous est une proposition de responsabilités, à permuter librement ; elle ne présume pas d’une différence de niveau technique. Electron et Python restent des choix proposés.

| Chantier | Responsable proposé | Livrable autonome |
| --- | --- | --- |
| Agent et intégration H | Matteo | Exécution réelle, procédures, vérification, arrêt local et compte rendu structuré. |
| Application utilisateur et intégration | Edouard | Demande, rôle, consentement, progression, arrêt, résultat et feedback ; pilote du premier parcours complet. |
| Support et données | Tom | Stockage, dossier d’escalade, tableau de bord, regroupement simple et préparation des données de démo. |

**Contrat commun à fixer avant de travailler en parallèle :** une demande porte un identifiant de session, le logiciel, le rôle déclaré, l’objectif et le périmètre approuvé. Les commandes couvrent démarrer, approuver et arrêter. Les événements exposent l’état, les étapes, le besoin d’un humain et la fin. Le rapport distingue résultat observé, succès déclaré, blocage, preuves autorisées et feedback.

Edouard et Tom peuvent développer avec des événements simulés explicitement identifiés pendant que Matteo teste H sur le Mac. Dès qu’une action réelle fonctionne, Edouard coordonne un premier parcours complet avec Matteo et Tom. Les essais qui utilisent le même Mac sont réservés et exécutés l’un après l’autre. Les événements simulés ne constituent pas une validation de l’intégration réelle.

**Premier jalon commun :** partir d’une demande dans l’application, réaliser une action réelle, vérifier l’état obtenu et afficher son compte rendu côté support. La supervision humaine en direct et les intégrations commerciales viennent après ce parcours.

**Organisation avec les coding agents :** chaque responsable donne à son agent un périmètre de code, un contrat d’entrée/sortie et un critère d’acceptation. Utiliser des branches ou worktrees séparés pour les modifications concurrentes, et désigner un propriétaire pour les fichiers partagés. Les humains vérifient les comportements et intègrent régulièrement ; la disponibilité de plusieurs agents ne dispense pas d’un premier parcours réel complet.

## Questions à trancher

**Avant de figer le MVP**

1. Retenir l’environnement concret : Toporder déjà accessible sur Mac, Odoo de test, ou copie ciblée en repli. Confirmer la version, le persona, la tâche utile, le blocage et la remise à zéro. Proposition de départ : Odoo avec une activité de relance sur une opportunité fictive, sous réserve d’un premier essai réussi.

2. L’escalade de la démo s’arrête-t-elle à un dossier exploitable par le support, ou inclut-elle déjà une supervision humaine de l’agent ? Le mode initial avec accord du client puis intervention est désormais confirmé.

3. Attribuer les responsabilités proposées — Matteo pour H, Edouard pour l’application et l’intégration, Tom pour le support et les données — et figer le contrat commun. L’identité des membres, leur polyvalence et l’usage de coding agents sont confirmés.

**Avant un pilote auprès de clients**

4. Qui propose l’installation, reçoit les dossiers et finance le service : l’éditeur, une équipe informatique ou l’utilisateur ?

5. Quelles actions sont autorisées et lesquelles exigent une confirmation supplémentaire ?

6. Quelles données sont envoyées à H, conservées par notre produit et visibles par le support ? Pendant combien de temps ?

7. Quelles procédures et informations de diagnostic l’éditeur peut-il fournir, et qui valide leurs mises à jour ?

8. Quel outil recevra les escalades, et quel gain le pilote doit-il démontrer : temps de résolution, diminution des échanges, qualité des dossiers ou fréquence des problèmes identifiés ?

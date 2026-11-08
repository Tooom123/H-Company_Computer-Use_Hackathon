# H-Companion — point projet et choix de démonstration

État vérifié le **7 novembre 2026**. Ce document distingue les résultats observés,
le code disponible et les prochaines étapes proposées.

Actualisation après cette note : le navigateur isolé, le portail documentaire et
la nouvelle campagne sont décrits dans le [bilan d’intégration](bilan-isolation-et-portail-2026-11-07.md).
Les états ci-dessous décrivent le point de départ de cette intégration.

## 1. Le produit et sa promesse

**Un assistant qui voit où l’utilisateur est bloqué dans un logiciel, lui explique
la prochaine étape, peut agir avec son accord et transmet un retour exploitable
à l’équipe support.** Dans le produit cible, l’éditeur fournit sa documentation,
ses procédures et les limites d’action. H-Companion doit associer ces connaissances
au contexte de l’écran et à la demande de l’utilisateur.

Deux usages complémentaires : **« Guide-moi »**, où l’utilisateur apprend et agit,
et **« Fais-le avec mon accord »**, où l’agent exécute puis vérifie. L’entreprise
récupère les difficultés rencontrées pendant les sessions assistées, les
escalades et le feedback ; cela ne représente pas toute l’utilisation du logiciel.

La valeur à prouver : meilleure réussite, moins de temps perdu et aide jugée utile.
L’existence de forums montre des difficultés ; elle ne prouve pas encore une demande
payante. La distribution envisagée est B2B2C : l’éditeur distribue son assistant
configuré à ses utilisateurs. Le prix et la volonté de payer restent à valider.

## 2. Quel terrain choisir ?

**Recommandation : conserver Odoo comme démonstration principale.** Nous possédons
déjà les données, les scénarios, le reset et les contrôles métier. Ajouter au plus
un deuxième parcours court, plutôt que préparer plusieurs logiciels simultanément.

| Terrain | Accès et intérêt | Décision proposée |
| --- | --- | --- |
| **Odoo enrichi** | Instance dédiée disponible, données métier fictives et résultats vérifiables | Démo et campagne principales |
| **SAP S/4HANA / Fiori** | Trial officiel de 30 jours, environnement partagé et parcours prédéfinis ; personnalisation et imports limités | Très bon cas entreprise ; essai exploratoire, pas remplacement du benchmark |
| **Salesforce** | Developer Edition gratuite pour développement/test, avec allocations limitées ; communauté Trailblazer | Prochain terrain CRM si nous voulons une validation externe |
| **n8n** | Community Edition auto-hébergeable ; cas parlants de mapping, conditions et erreurs de workflow | Bon candidat pour utilisateurs techniques, avec workflows et services fictifs |
| **HubSpot** | CRM gratuit et communauté d’entraide ; Breeze assure déjà une partie de l’aide contextuelle | Possible, mais démontrer un apport précis par rapport à l’assistant intégré |
| **Blender** | Application native gratuite, documentation et communautés Blender Artists / Stack Exchange / Reddit | Bon terrain desktop ultérieur ; demande un environnement graphique isolé |
| **H Company** | Documentation publique et plateforme à laquelle nous avons déjà accès | Court parcours d’onboarding ou de diagnostic pour le clin d’œil sponsor |

Sources d’accès et communautés : [SAP trial](https://www.sap.com/products/erp/s4hana/trial.html),
[FAQ SAP](https://www.sap.com/documents/s4hana-public-cloud-trial-faqs-1276934),
[communauté SAP](https://pages.community.sap.com/topics/s4hana-cloud),
[Salesforce Developer Edition](https://developer.salesforce.com/signup),
[Trailblazer](https://www.salesforce.com/blog/get-the-most-out-of-the-trailblazer-community/),
[n8n Community Edition](https://docs.n8n.io/deploy/host-n8n/community-edition-features.md),
[exemple de difficulté n8n](https://community.n8n.io/t/n8n-not-mapping-data-from-previous-nodes/43101/4),
[HubSpot gratuit](https://www.hubspot.com/products/crm),
[communauté HubSpot](https://community.hubspot.com/t/option-to-make-changes-to-hubspot-default-properties/140506),
[communautés Blender](https://www.blender.org/community/).

SAP intègre déjà [Joule](https://help.sap.com/docs/SAP_S4HANA_CLOUD/0f69f8fb28ac4bf48d2b57b9637e81fa/619518deb7284e6485b78383fa7a42b3.html),
n8n un [AI Workflow Builder](https://docs.n8n.io/build/ways-of-building-workflows/ai-workflow-builder.md)
et HubSpot [Breeze](https://www.hubspot.com/products/artificial-intelligence/breeze-ai-assistant).
Le positionnement doit porter sur le coaching contextualisé, la vérification et
la boucle support. SAP Fiori est web ; le trial ne fournit pas automatiquement
un ancien poste SAP GUI. Pour des tests reproductibles, il faut fixer données,
permissions, version et écran de départ, indépendamment de la présence d’IA.

Des sub-agents peuvent construire un **simulateur de quelques parcours**, mais
une réussite sur cette copie ne valide pas une réussite sur SAP ou Salesforce.
Les employer à préparer fixtures, scénarios et vérificateurs est plus utile ici.
Les systèmes hospitaliers anciens sont une piste ultérieure avec un partenaire métier.
Une exploration administrative peut utiliser une instance privée OpenEMR à données
fictives ; ses [démos publiques](https://www.open-emr.org/demo/) sont partagées et
réinitialisées, donc peu adaptées à notre benchmark. Cela ne reproduit pas un SI hospitalier réel.

## 3. Où nous en sommes réellement

| Brique | État observé |
| --- | --- |
| **Vision Lab** | Webcam, regard/tête, cinq zones stables, crops, coordonnées et cible rouge avec score automatique fonctionnent |
| **Dernier essai tête** | Cible entière dans 18/21 crops évaluables (86 %), 2/30 replis (7 %), surface détaillée moyenne conservée 40 %. Un participant et un parcours ; aucun gain de tokens ou latence Holo démontré |
| **Pilote vocal** | Interface Electron, transcription Gladia, approbation, actions Holo4, vérification, retour vocal et labels enregistrés |
| **Odoo enrichi** | Démo HTTPS disponible, dix scénarios R01–R10 en lecture seule, oracle métier et archives |
| **Campagne** | Dix premiers essais : 4 réussites métier selon la revue indépendante, dont 3 avec périmètre conforme ; puis 3 retests. Ce n’est pas un benchmark final |
| **Support entreprise** | API, SQLite, dashboard authentifié, regroupement des difficultés, escalades ; intégration Devin présente dans le code |
| **Connaissance** | Procédures fournies au pilote ; recherche documentaire encore `NoKnowledge`. Aucun RAG Odoo évalué |
| **Isolation** | Campagne arrêtée après captures hors périmètre ; traces concernées en quarantaine. Garde desktop v3 testée hors ligne, navigateur isolé encore à intégrer |
| **Entraînement** | Archives, revues IA et feedback humain lorsqu’il existe ; aucun dataset validé ni adaptateur LoRA entraîné. Les traces ne sont pas automatiquement admissibles à l’entraînement |

Références : [résultats Odoo détaillés](recette-odoo-enrichi-2026-11-07.md),
[journal Vision Lab](https://github.com/Tooom123/H-Company_Computer-Use_Hackathon/blob/f5ad7e1/docs/test-log.md),
[scénarios Odoo](https://github.com/Tooom123/H-Company_Computer-Use_Hackathon/blob/f5ad7e1/docs/scenarios/odoo-rich-scenarios.md),
[scénarios H Company](scenarios/h-company-scenarios.md).

Le pilote testé épingle le moteur **`b59ef01`** et le stockage **`bd3b2ca`**.
Au dernier fetch, `origin/main` était **`e46f9ee`** et `origin/matteo` **`0ffda3f`**.
Leurs ajouts ne sont pas validés par cette campagne. Intégrer les correctifs Matteo
en préservant la remontée support présente sur main. Le recadrage Vision Lab
n’est pas encore relié à la boucle autonome. Holo4 est également disponible sur
le DGX Spark ; la campagne décrite utilisait l’inférence H, pas le DGX.

## 4. Le portail web entreprise à compléter

Reprendre le dashboard de Tom et proposer trois écrans :

1. **Configurer l’assistant** : logiciel, domaine, rôle utilisateur, modes guide/action,
   opérations permises et conditions d’escalade.
2. **Charger la documentation** : Markdown, version, état d’indexation, question de test
   avec sources. Brancher `Knowledge.ask()` ; comparer ensuite recherche lexicale,
   vectorielle et hybride plutôt que supposer le gain.
3. **Comprendre les difficultés** : sessions, preuves autorisées, feedback humain,
   revue IA séparée, latences/coûts, groupes et escalades. Exclure simulations et
   quarantaines des indicateurs de réussite réelle.

L’import documentaire, le RAG et la séparation multi-entreprise restent à construire.
Commencer avec une entreprise pilote isolée ; avant de mutualiser, ajouter comptes,
rôles et filtrage par entreprise des documents, cas et fichiers.

## 5. Prochaine séquence et répartition proposée

1. **Matteo + intégration** : navigateur headless dédié, authentifié hors contexte du
   modèle, capturant uniquement la page. Acteur et vérificateur réutilisent ce
   navigateur ; un processus/profil par worker. Tester un cas puis deux workers.
2. **Édouard** : figer trois parcours de coaching Odoo avec un utilisateur novice,
   un objectif observable et une question de feedback. Démontrer « Guide-moi »
   autant que l’exécution autonome ; conserver Vision Lab comme expérience séparée.
3. **Tom** : relier les vrais rapports au dashboard, afficher les différents verdicts,
   compléter l’import documentaire minimal et les exports de traces.
4. **Équipe** : rejouer les dix cas avec versions et départs fixés, puis évaluer des
   variantes inédites. Mesurer réussite, temps, corrections humaines et utilité ;
   la réussite d’un agent seul ne prouve pas que l’utilisateur apprend mieux.
5. **Après cette validation** : collecter des traces propres et consenties, réserver
   un jeu de test avant entraînement, puis comparer modèle de base et adaptateur.

Pour les sponsors : un parcours H Company peut illustrer l’onboarding. La boucle
**H → difficulté détectée → support → Devin → proposition de PR** peut mieux
illustrer Cognition qu’un nouveau coach de son interface. La limiter à notre dépôt
de démonstration autorisé, avec bug volontaire clairement annoncé ; l’intégration
présente peut être simulée sans clé et n’a pas été validée par la campagne Odoo.

**Critère de fin du MVP :** une personne accomplit une tâche guidée sur le vrai
logiciel, le résultat est vérifié, son retour est enregistré et l’équipe support
retrouve un dossier compréhensible avec les sources documentaires utilisées.

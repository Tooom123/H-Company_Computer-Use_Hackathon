# Premier lot de démonstrations et de traces

État du 7 novembre 2026. Les consignes et procédures sont préparées pour le moteur
Matteo `185ab70`. Un test simulé ne constitue pas un passage réel Holo.

Le dernier essai humain Vision Lab est terminé : 18/21 crops évaluables contiennent
la cible entière, 2/30 replis, 40 % de surface détaillée moyenne conservée. Voir
[les mesures et leurs limites](../test-log.md#essai-humain-cinq-zones--dernière-capture-à-195927).
Ces chiffres ne mesurent pas encore les tokens ou la réussite d’une tâche Holo.
Le pilote réel **Odoo 01 est validé** : 10 EUR / 10 unités, quatre contrôles vrais,
26,40 s approbation → fin, puis revue indépendante. L’archive privée contient les
deux sessions H, 27 événements et 3 images référencées. Un passage interrompu et
deux escalades précédents sont conservés : fenêtre initiale hors scénario, prix
masqué à la fin, puis ambiguïté du vérificateur sur « Quantité disponible ».
Le YAML précise maintenant l’onglet final et le libellé exact du champ de stock.
Ces essais constituent du développement, pas un benchmark tenu à l’écart.

## Ordre de passage

1. Dernier essai Vision Lab : Tête → 5 zones stables, 800 × 600, cadre Écran,
   parcours 42, 30 secondes, contour masqué. Noter couverture des crops, replis
   et causes, surface et nombre de captures évaluables. Refaire ensuite le point
   continu avec la **même calibration** si une comparaison directe est recherchée.
   La surface seule n’est pas un gain de tokens.
2. Un passage Odoo 01 en lecture seule avec le moteur, puis vérification humaine
   et archive de ses sessions. Vérifier que les images et actions sont effectivement
   présentes avant de lancer le reste du lot.
3. Les autres demandes Odoo, puis H Company. Relire chaque résultat et son feedback
   avant l’essai suivant. Ne pas avoir deux agents qui pilotent simultanément le Mac.

| Lot | Consignes et critères | Exécution |
| --- | --- | --- |
| Odoo 01–10 | [Dix demandes exactes](odoo-scenarios.md) | Dix procédures distinctes ; les demandes 05–10 partagent un état métier et un `workflow_id` |
| H01–H08 | [Documentation H](h-company-scenarios.md) | `h_company_documentation`, question et titre de correction propres à chaque scénario |
| H09–H10 | [Agent View](h-company-scenarios.md#h09--revoir-ce-quune-session-a-réellement-fait) | `h_company_session_review`, deux sessions de démonstration préparées ; accès connecté requis |

Le rôle de l’utilisateur, le goal, le mode `act`/`guide`, le modèle, la procédure
et ses paramètres sont fixés avant chaque passage. Les valeurs attendues de lecture
et grilles de correction sont réservées au vérificateur et à la revue humaine.
Les YAML sont fournis dans ce dossier ; ils ne modifient pas automatiquement le
registre du moteur dans les autres branches.

## Modèle et origine des traces

Le premier lot peut employer `holo4-35b-a3b` via le moteur cloud existant. Le Spark
dispose déjà de la base Holo4-35B-A3B-NVFP4 ; la bascule vers ce serveur nécessite
son authentification normale et le runtime local. Ne pas télécharger un second
checkpoint par défaut. Le contexte et la précision de l’API ne sont pas présumés
identiques au serveur NVFP4 : cette bascule ne constitue pas un A/B de latence.

Les events et ressources du cloud sont exportables. Les sessions locales Spark
ne remontent pas automatiquement dans H Platform : elles ont besoin d’un recorder
local distinct. Langfuse pourra faciliter la revue et la comparaison, mais ne
remplace ni les octets des images ni les actions complètes.

Dans `185ab70`, le guide scripté avec `guide_steps` appelle directement Models API
pour localiser les contrôles : ces appels ne produisent pas de session Agents à
exporter. Leur recorder n’est pas encore ajouté. Utiliser **act** pour le premier
lot cloud exportable ; une session de vérification seule ne couvre pas les appels
du guide qui l’ont précédée.

Voir [le mode d’emploi de l’archive et des labels](../trace-capture-runbook.md),
puis [le protocole scientifique et LoRA](../lab-to-odoo-lora.md).

## Critère pour continuer après le premier épisode

- Le résultat demandé est vérifié ; sinon, conserver l’échec et sa cause.
- Le rapport distingue déclaration du modèle, vérification et avis utilisateur.
- Les fichiers image sont archivés avec empreintes, et les événements complets
  exportables sont présents ; tout manque ou troncature est signalé.
- Le retour utilisateur précise réussi / partiel / échoué, utilité et corrections.
- L’autorisation de réutilisation pour entraîner est distincte du partage au support.

Ce lot de vingt demandes est un pilote. Les étapes liées et leurs variantes
restent dans le même split ; elles ne sont pas vingt workflows indépendants.
La comparaison de fine-tuning utilise un test tenu à l’écart, pas ces mêmes
exemples utilisés à l’entraînement.

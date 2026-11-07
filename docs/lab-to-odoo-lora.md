# Du Vision Lab aux traces Odoo et au pilote LoRA

Décision de travail du 7 novembre 2026. Ce document distingue résultats observés,
travail à intégrer et expériences proposées. Aucun gain de tokens ou d’entraînement
n’est encore démontré. Les chiffres locaux sont dans [le journal](test-log.md).

## 1. Réduire la dépendance à une position précise de la tête

L’essai de 19:20 contient 14 replis sur 30 captures : 10 projections hors écran et
4 orientations hors du domaine appris. Les crops évaluables contiennent la cible
entière dans 10 cas sur 12. Notre hypothèse : **classifier une direction grossière
peut être plus stable que prédire un point précis**. Une baisse des replis seule
ne suffit pas ; la couverture doit rester bonne.

Ajouter un bras « cinq zones tête », en conservant le pointeur fin comme référence :

- apprendre centre et quatre coins depuis les poses des cinq cibles déjà calibrées ;
- conserver une zone neutre centrale et confirmer un changement pendant 250 ms ;
- orienté vers un coin : ancrer le rectangle demandé au coin, sans le faire glisser
  en permanence avec chaque prédiction ;
- au centre : crop central ; en mode Fenêtre, prendre les limites de la fenêtre
  visible au centre. Une fenêtre maximisée apporte peu ou pas de réduction ;
- visage absent, signal ancien, calibration manquante ou orientation extrême :
  repli explicite. Ne pas transformer toute absence de signal en « centre ».

Les cinq zones se chevauchent spatialement selon la taille du crop. Elles ne sont
pas nécessairement cinq tuiles disjointes de même surface. Un regard au bord entre
deux coins reste un cas difficile à tester. Le rectangle représente une sélection
d’image, pas une mesure certifiée de l’attention de la personne.

Test humain : même calibration, dimensions, écran, fenêtre et durée ; alterner
pointeur fin / zones et refaire plusieurs parcours, dont des graines jamais utilisées
pour ajuster les seuils. Publier couverture des crops, replis et raisons, surface,
changements parasites, disponibilité et temps de préparation. Conserver les cibles
de validation hors calibration. Le sélecteur ne reçoit jamais les coordonnées de
la cible rouge du benchmark.

## 2. Tester les tokens avec de vrais appels

Sur un petit jeu de captures Odoo figées, comparer à instruction, modèle, historique
et paramètres identiques : plein écran ; crop ; crop + aperçu global. Alterner
l’ordre des appels et répéter. Garder l’image exacte et son empreinte, ses dimensions,
les offsets, le modèle, la date et le contexte documentaire.

Mesures : `usage` réel renvoyé par H, temps de préparation, durée HTTP, réponse
correcte et nécessité de revenir au plein écran. L’usage d’entrée peut agréger texte
et images : ne pas l’appeler « tokens image » sans détail fourni par l’API. Compter
les aperçus globaux, relances et replis dans le total. La surface et la taille PNG
ne sont pas des compteurs de tokens. Le recadrage peut perdre un menu, un dialogue
ou le contexte nécessaire malgré une cible incluse.

Pour des actions : transformer les coordonnées du crop vers la capture source puis
vers l’écran logique, y compris redimensionnement. Un rectangle exact sans bonne
transformation des clics n’est pas une intégration de computer-use fonctionnelle.

## 3. Premier passage métier avec Matteo

Le remote `matteo` a été inspecté à `8bba047`. Son moteur propose déjà une API locale,
approbation, arrêt, modes `act` / `guide`, vérification distincte et feedback final.
Ses procédures présentes ciblent le CRM Odoo 19. Notre instance dédiée est Odoo 20
avec Inventaire / Achats / Ventes : ne pas lancer une procédure CRM par défaut.

Premier parcours : ouvrir Inventaire, rechercher `HACK-GING-033`, ouvrir la fiche,
lire le prix de vente et le stock disponibles. Baseline après reset : 10 € et 10
unités. Le [YAML lecture seule](scenarios/odoo_inventory_read_product.yaml) est destiné
au chargeur de Matteo. Son chargement, son interpolation et ses quatre vérifications
ont été validés offline contre les vrais modules `contract.py` et `procedures.py`
de `8bba047` (Python 3.13.7, Pydantic 2.10.3, PyYAML 6.0.3). Les valeurs attendues
sont présentes dans la vérification, absentes des instructions de l’acteur, du guide
et du plan. Le SDK `hai_agents` n’étant pas installé dans cet environnement de
validation, le cycle HTTP/mock complet reste à exécuter sur l’environnement de
Matteo avant le passage réel. La procédure n’a pas encore piloté Odoo avec Holo.

Deuxième parcours, après réussite du premier : achat 6 × 4 € = 24 €, réception de
4, reliquat de 2, réception finale. Les postconditions indépendantes sont stock
10 → 14 → 16, une commande, deux réceptions liées et Pomme/Hibiscus inchangés.
La procédure de préparation et de reset est dans [le handoff Odoo](odoo-live-test-handoff.md).
Chaque passage a un identifiant unique ; un seul acteur contrôle le Mac.

**Avant de démarrer le moteur inspecté : `HCS_AUTO_CLEANUP=0`.** Dans cette révision,
le nettoyage des sessions orphelines peut fermer des trajectoires distantes de la
clé sans identifier leur propriétaire. Ne pas perturber les sessions de l’équipe.

Matteo pilote actuellement le desktop via Agents API. Vision Lab envoie ses images
figées via Models API. Ce ne sont pas encore la même boucle : raccorder réellement
la source de screenshots et la conversion des actions avant de présenter un gain
de recadrage dans le moteur autonome. Ne pas multiplier les traces avant ce contrôle.

Le [SDK desktop officiel](https://raw.githubusercontent.com/hcompai/hai-agents-python/main/src/hai_agents_local/desktop.py)
expose `create_driver()` : un bridge personnalisé est une piste pour garder Agents
API, à valider sur la version installée. Geler crop, offsets et dimensions jusqu’à
l’exécution des actions correspondantes ; le mouvement suivant de la tête ne doit
pas changer la référence d’un clic déjà décidé. Commencer par une seule région avant
une composition aperçu + détail. Fixer aussi le modèle explicitement : Matteo utilise
par défaut `holo4-35b-a3b`, le Lab `holo4-27b`.

## 4. Constituer des traces exploitables

Commencer par 10–20 traces pilotes, puis viser environ 100 si le format est complet
et le temps le permet. Une trace est un épisode utilisateur, pas un screenshot.
À titre d’arithmétique de planning, 100 épisodes de 3–5 minutes représentent déjà
5–8 h 20 de contrôle séquentiel, hors resets, revue et corrections.

Conserver dans un stockage privé, hors Git :

| Niveau | Contenu minimal |
| --- | --- |
| Épisode | ID, scénario/famille/variante, fixture et état initial, version Odoo, objectif et rôle, consentement de collecte, date, versions du moteur/modèle/politique, `simulated` |
| Contexte | Version et empreinte de la doc, passages récupérés, instruction exacte et historique utile, schémas des outils |
| Décision | Image exacte vue par le modèle, crop/source/échelles, masque éventuel, réponse brute, action structurée, outil exécuté, résultat, timestamps, tokens et erreurs |
| Contrôle | Arrêts, demandes humaines, corrections et reprises, raison du repli, vérification de l’état Odoo |
| Fin | Résultat déclaré par l’agent, résultat objectivement vérifié, retour utilisateur `réussi / partiel / échoué`, utilité, commentaire, correction souhaitée |

Les rapports du moteur et le consentement de partage au support sont un début ; ils
ne prouvent ni la présence de chaque paire image/action, ni une autorisation de
réutilisation pour entraîner. Conserver séparément les consentements et les labels.
Un `useful=true` signifie utile, pas nécessairement tâche réussie.

Audit de `8bba047` : captures avant/après conservées ; arguments d’actions tronqués
à 80 caractères dans les étapes ; URLs de screenshots sans archivage exhaustif
garanti ; événements du serveur en mémoire ; coût extrait mais tokens non conservés.
Le feedback persiste `useful`, commentaire et permission de partage, sans renseigner
`verification.user_confirmed`. Ajouter un recorder brut au niveau des observations
et outils, puis un fichier de labels séparé, plutôt que croire ces rapports suffisants
pour le SFT. Le mode guide ne journalise pas automatiquement tous les clics humains.
Le backend de Tom (`origin/tom@bd3b2ca`) dispose déjà d’une ingestion de cas et
d’événements avec SQLite : à réutiliser pour le suivi, en gardant les images privées.

Pour le premier lot, une fiche Markdown courte, versionnée et propre à Odoo 20 peut
être injectée directement. Le moteur a une recherche web documentaire optionnelle,
pas encore notre ingestion Markdown + RAG hybride. Figer la documentation utilisée
avant de comparer les modèles. Le RAG reste approprié pour les procédures qui évoluent ;
le LoRA vise surtout le comportement et les décisions récurrentes.

SFT : garder les actions vérifiées ou corrigées. Une trace terminant par un succès
peut contenir des erreurs et des clics inutiles ; ne pas tout enseigner comme exemple
positif. Un label final négatif ne fournit pas automatiquement l’action correcte.
Conserver les échecs pour l’analyse, la collecte de corrections et l’évaluation.

## 5. Comparer sans apprendre les réponses du test

Figer avant entraînement une répartition indicative **60 entraînement / 20 validation /
20 test**, par groupes de tâches, variantes et sessions. Aucun frame voisin, même
épisode, même fixture copiée ou reformulation quasi identique ne doit traverser les
splits. Garder les variantes de test inédites et ne plus régler les seuils dessus.
Si le lot se réduit à cinq scénarios répétés, annoncer un pilote étroit, pas une
généralisation à Odoo ou aux logiciels métier.

Comparer base et adaptateur sur **le même test tenu à l’écart**, en repartant du même
état Odoo. Même modèle de base, même précision numérique, même serveur/matériel,
mêmes docs, politique d’image, budget d’actions, limites de temps et outils. Base API
H contre adapter sur notre GPU ne permet pas d’isoler un effet sur la latence.

Séparer les expériences : A/B des images à modèle fixe, ajout documentaire à modèle
fixe, puis LoRA à images/docs fixes. Mesurer réussite métier vérifiée, interventions,
nombre d’actions, tokens par tâche et par tâche réussie, durée totale et médiane/p95
des appels. Inclure les échecs et timeouts ; publier le nombre d’épisodes et les
résultats appariés. Vingt tests donnent une indication, pas un résultat robuste de papier.

## 6. LoRA cette nuit : possible sous conditions

Vérifications sur sources primaires du 7 novembre :

| Modèle | Poids et contraintes pertinentes |
| --- | --- |
| [Holo4-27B](https://huggingface.co/Hcompany/Holo4-27B) | Dense, poids BF16 publiés ; licence CC BY-NC 4.0. La commercialisation demande de traiter ces droits séparément. |
| [Holo4-35B-A3B](https://huggingface.co/Hcompany/Holo4-35B-A3B) | MoE, poids BF16 publiés ; Apache 2.0. « 3B actifs » ne signifie pas que seuls 3B paramètres occupent la mémoire. |

H décrit des experts LoRA dans [son entraînement Holo4](https://hcompany.ai/newsroom/holo4).
Cela soutient la faisabilité, pas une recette SFT Odoo prête à exécuter : les rubriques
Training des model cards ne donnent pas cette recette. Aucun endpoint public de
chargement de notre adapter n’a été trouvé dans la documentation examinée : prévoir
un serveur propre, suivant [l’inférence locale H](https://hub.hcompany.ai/agents-api/local-inference),
et vérifier le raccordement du moteur à son `base_url`.

Pile candidate à qualifier : Transformers + [TRL SFTTrainer](https://huggingface.co/docs/trl/main/en/sft_trainer)
+ [PEFT](https://huggingface.co/docs/peft/main/package_reference/lora), LoRA sur la partie
langage, encodeur visuel gelé, petites séquences, QLoRA si nécessaire et compatible.
Tester le processeur et le chat template, les tool calls, le masquage des labels et
la conservation des tokens image. Les poids seuls occupent environ 54,7 Go pour le
27B BF16 et 70,2 Go pour le 35B BF16 ; activations, buffers et optimiseur s’ajoutent.
Un GPU 80 Go est une cible de pilote, pas une garantie. Le 27B multimodal sur 24 Go
ne doit pas être promis avant un test de mémoire.

**Estimation conditionnelle, pas un benchmark mesuré :** 100 traces × 20 décisions,
dont 60 traces d’entraînement, sur 2 passages = 2 400 exemples traités. À 1 exemple/s,
c’est 40 min ; à 1 exemple/5 s, 3 h 20 ; à 1 exemple/20 s, 13 h 20. Installation,
téléchargement, préparation, évaluation et serving s’ajoutent. Le nombre d’images
et la longueur du contexte peuvent changer fortement ces durées.

Avant la longue exécution : charger le modèle, entraîner 20–50 microbatches
représentatifs après warm-up, mesurer pic VRAM et débit, sauvegarder/recharger
l’adaptateur, puis obtenir une action multimodale exploitable. Extrapoler depuis
le nombre réel d’exemples ; si ce contrôle échoue, garder le modèle de base pour la
démo et livrer le dataset/protocole comme résultat expérimental.

### Matériel confirmé : Spark 128 Go et crédits Verda

Edouard dispose d’un DGX Spark 128 Go, de 1 500 USD de crédits Verda et d’un accès
Colab. Contrôle SSH en lecture seule du 7 novembre : architecture ARM64, GPU GB10,
pilote 580.126.09, 121 Gio de mémoire système visible dont environ 45 Gio disponibles,
et environ 2,8 Tio de disque libre. Deux moteurs vLLM sont déjà actifs. Les images
ARM vLLM 0.28/0.30 et PyTorch NVIDIA 26.08 sont présentes ; cela ne valide pas encore
notre modèle. Aucun service, modèle chargé ou configuration distante n’a été modifié.

**Proposition : un seul H200 141 Go à la demande sur Verda.** Cette capacité laisse
plus de marge pour le LoRA multimodal que 80 Go, sans complexifier le pilote par du
multi-GPU. Prendre Holo4-27B dense comme premier candidat conserve la base du Lab ;
Holo4-35B-A3B reste l’alternative Apache 2.0. Figer le choix avant de collecter le
lot comparatif. Cette proposition n’est pas une validation du pic mémoire réel.

Tarifs publics USD relus directement le 7 novembre, hors stockage et sous réserve
du devis/éligibilité des crédits dans la console. Les extraits de moteur de recherche
affichaient des prix plus anciens : utiliser la page directe et confirmer avant création.

| Instance à la demande | USD/h | Calcul pour 8 heures |
| --- | ---: | ---: |
| H100 80 Go | 4,938 | 39,50 USD |
| **H200 141 Go** | **6,440** | **51,52 USD** |
| B200 180 Go | 9,138 | 73,10 USD |

Source : [tarifs Verda USD](https://verda.com/pricing?currency=usd). H200 pendant
12 heures représenterait 77,28 USD de calcul. Proposer une enveloppe initiale de
100 USD couvrant le pilote et une marge ; ce n’est pas un plafond technique déjà
configuré. Aucune instance n’est créée et aucun crédit n’est consommé par cet audit.
Privilégier on-demand pour ce premier passage ; les instances spot peuvent être
interrompues, selon [la documentation Verda](https://docs.verda.com/cpu-and-gpu-instances/set-up-a-gpu-instance/).

Commencer sur Verda par base BF16, LoRA langage avec encodeur visuel gelé, une requête
à la fois et contexte court représentatif des traces. Mesurer 20–50 microbatches,
recharger l’adaptateur, vérifier image + tool call, puis seulement lancer le lot.
Chronométrer la base et l’adaptation sur ce même serveur. Une réservation de huit
heures est une enveloppe de travail, pas une durée d’entraînement prédite.

Sur le Spark occupé, 45 Gio disponibles ne suffisent pas au 27B BF16 avec sa marge
d’exécution. H publie aussi des poids FP8/NVFP4 ; sa recette Holo4 exige vLLM 0.28+.
La commande Spark plus ancienne sur cette page sert Holo3.1 : ne pas la recopier
telle quelle. Les débits affichés pour Holo3.1 ne sont pas des mesures Holo4.
[Recette H](https://hub.hcompany.ai/agents-api/local-inference),
[playbook NVIDIA](https://build.nvidia.com/spark/vllm/intermediate).

La combinaison précise Holo4 + précision quantifiée + adapter + kernels GB10 reste
à qualifier. Première voie : base + adapter séparé sur la partie langage. En cas
d’incompatibilité du chargement, fusionner l’adapter dans une copie BF16 sur Verda,
puis qualifier le checkpoint et son éventuelle quantification. Conserver base et
adapter originaux ; une quantification peut modifier les résultats et nécessite
un nouvel A/B à précision identique. Voir [LoRA vLLM](https://docs.vllm.ai/en/latest/features/lora/)
et [fusion PEFT](https://huggingface.co/docs/peft/developer_guides/checkpoint).
Si la mémoire ou le portage Spark bloque, le serveur Verda validé peut servir la démo.

**Raccordement à Matteo : garder la boucle sur le Mac.** Le Spark expose l’API du
modèle, pas l’API Agents cloud. La voie documentée utilise `Client.local` avec
`Inference.self_hosted`, joignant le serveur Spark/Verda par tunnel SSH. Le modèle
de l’agent fixe le format Holo4 ; le nom du serveur sélectionne la base ou l’adapter.
Ce changement de client n’est pas encore implémenté dans le moteur audité.
[Runtime local H](https://hub.hcompany.ai/agents-api/local-runtime).

```python
from hai_agents import Client
from hai_agents_local.runtime import Inference

# Exemple de raccordement à qualifier, pas un script exécuté.
agent["model"] = "holo4-27b"
inference = Inference.self_hosted(
    "http://localhost:8000/v1",  # extrémité locale du tunnel
    model="hcompanion-odoo",    # nom effectivement servi
)
with Client.local(inference=inference) as client:
    # Créer la session selon le moteur et conserver approbation / arrêt / traces.
    pass
```

Colab reste utile pour inspecter/préparer le dataset ; le GPU et les limites d’usage
ne sont pas garantis sur les offres ordinaires. Il n’est donc pas le chemin principal
de cette nuit. [FAQ Colab](https://research.google.com/colaboratory/faq.html).

À la fin de la location Verda, sauvegarder et vérifier les artefacts avant de libérer
l’instance. **Un simple shutdown continue à facturer le calcul** : la documentation
demande la suppression de l’instance, en choisissant explicitement les volumes à
conserver. Les volumes conservés restent facturés. Aucune suppression automatique
n’a été programmée. [Cycle de vie Verda](https://docs.verda.com/cpu-and-gpu-instances/shutdown-hibernate-and-delete/).

## 7. Répartition et ordre de passage

| Responsable | Prochain livrable | Critère de fin |
| --- | --- | --- |
| Edouard | Comparaison pointeur/zones, scénario Odoo, recette humaine et labels | Scores exportables, premier épisode relu, aucun gain inventé |
| Matteo | Procédure Odoo 20, boucle agent, export image/action, adaptation de l’observation | Premier passage réel contrôlé ; trace rejouable ; arrêt fonctionnel |
| Tom | Persistance privée des traces, formulaire de résultat, vérificateur/agrégats | Agent déclaré / état vérifié / satisfaction séparés ; manifeste train/val/test |
| Chantier GPU en parallèle, après disponibilité connue | Mini-entraînement puis rechargement | Débit/VRAM mesurés, adapter utilisable et comparaison tenue à l’écart |

Priorité : un passage Odoo de bout en bout et quelques traces de qualité, puis la
collecte élargie. L’entraînement nocturne reste un pilote conditionnel ; il ne doit
pas empêcher de présenter demain le produit, ses retours utilisateurs et les mesures
réelles du Lab.

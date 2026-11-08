# Holo4 — DGX Spark, API H et recadrage de fenêtre

Mesures réelles du 8 novembre 2026. **Microbenchmark de localisation visuelle**,
pas une mesure de la boucle complète de coaching ni un test utilisateur.

## Résultat

Médianes de cinq répétitions mesurées par condition, après un échauffement.

| Image | Fournisseur | Premier fragment utile (TTFT reçu) | JSON de localisation complet | Temps total HTTP | Tokens entrée / sortie | Centre dans la cible |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Complète, 1470 × 956 | API H Models | 1,442 s | 1,714 s | 1,768 s | 1816 / 83 | 5 / 5 |
| Complète, 1470 × 956 | DGX Spark via Tailscale | 0,600 s | 1,705 s | 1,757 s | 1816 / 83 | 5 / 5 |
| Fenêtre, 1104 × 800 | API H Models | 1,376 s | 1,568 s | 1,624 s | 1286 / 83 | 5 / 5 |
| Fenêtre, 1104 × 800 | DGX Spark via Tailscale | 0,512 s | 1,617 s | 1,665 s | 1286 / 83 | 5 / 5 |

Le DGX commence plus tôt, mais sa génération du reste de la réponse prend plus
longtemps : le JSON utilisable arrive presque au même moment. Le premier fragment
contient des arguments d’outil, pas encore une phrase à lire à l’utilisateur.
Choisir le fournisseur sur le TTFT seul serait donc trompeur pour notre interface.

Le crop réduit les tokens d’entrée observés de **29,19 %** (1816 → 1286), avec
les mêmes 83 tokens de sortie. H distingue 1380 → 850 tokens image, soit
38,41 % de réduction pour la partie image seule. La surface diminue de 37,15 % :
ce n’est pas exactement le même indicateur. Le gain observé sur le JSON complet
est d’environ 0,15 s côté cloud et 0,09 s côté DGX ; ce petit échantillon ne prouve
pas un gain généralisable. Tous les centres prédits sont dans la cible attendue.

## Protocole et limites

- Modèle demandé : `holo4-35b-a3b` sur les deux endpoints. DGX : checkpoint
  NVFP4 existant, vLLM sur NVIDIA GB10 ; précision numérique cloud non confirmée.
- Une requête à la fois, clients HTTP persistants, ordre cloud/DGX alterné entre
  répétitions. Image complète testée avant crop : cet ordre peut introduire un biais.
- 20 réponses mesurées + 4 échauffements ; 2 appels de préflight supplémentaires,
  exclus du tableau. Aucun appel Agents API, clic ou action autonome dans ce test.
- Requête identique entre fournisseurs, image PNG identique, temperature 0,
  thinking désactivé, outil `locate`, maximum 128 tokens de sortie.
- Une seule image et aucun historique dans chaque appel. Aucun contexte RAG.
- Cible : bouton « Copy page », sans la flèche adjacente, dans la documentation
  publique H Cloud browser. La vérité de référence vient du rectangle DOM lors
  de la capture ; elle n’est pas transmise au modèle.
- La page publique est placée dans un **bureau synthétique neutre**. Le crop
  retire le pourtour sans modifier les pixels du document. Aucun bureau personnel,
  compte, clé ou donnée privée dans les images envoyées.
- Le cache est favorable à la répétition d’une même image. H rapporte 1056 tokens
  de préfixe réutilisés dans 2/5 essais complets et 3/5 essais crop ; les autres
  indiquent zéro. Le DGX ne renvoie pas ce détail.
- TTFT cloud complet : 1,292–3,127 s ; crop : 1,211–1,404 s. TTFT DGX complet :
  0,583–0,801 s ; crop : 0,509–0,658 s. Avec cinq essais, aucun SLA ni gain causal établi.
- Les temps commencent avant la requête HTTP : réseau, relais, attente, traitement
  image et génération inclus. Le tunnel SSH est persistant sur Tailscale, avec un
  relais authentifiant lié au loopback DGX. La clé vLLM reste sur le DGX.
- Relais, tunnel et jeton éphémère fermés/supprimés après mesure ; les serveurs
  Holo existants et l’application de coaching n’ont pas été reconfigurés.

Le GUIDE actuel réduit le screenshot à 1024 pixels de large. Ce test à 1470/1104
n’est donc **pas un A/B de l’application actuelle**. Pour le futur crop, conserver
une échelle commune et ne pas réagrandir chaque crop à 1024 : cela pourrait
annuler l’économie de pixels et de tokens. Refaire les mesures à la résolution
effective, sur plusieurs écrans et avec de vraies consignes.

## Ce que notre application envoie aujourd’hui

`HBackend.run_guidance` ouvre une session Agents API, avec observation desktop
fournie par le bridge. Chaque tour suivant utilise `handle.send_message` avec
un message textuel. Nous ne reconstruisons pas nous-mêmes un tableau de toutes
les images à chaque tour ; nous conservons cependant la même session H.
`from_index` est le curseur de lecture des événements, pas une limite au contexte
du modèle. La sélection des anciennes observations reste gérée côté H.

H documente le compactage automatique des longues sessions, sans exposer dans
les paramètres Agents examinés la politique exacte d’éviction des captures. On
ne peut donc pas affirmer « dernière image uniquement » pour le moteur actuel.
[Sessions H](https://hub.hcompany.ai/agents-api/sessions/overview).

Pour une boucle Models API que nous pilotons, H recommande **au plus trois
captures récentes**, les anciennes étant remplacées par un marqueur textuel.
Cela décrit une convention de boucle contrôlée par le client, pas une preuve du
fonctionnement interne de notre session Agents.
[Conventions Holo](https://hub.hcompany.ai/models-api/build-an-agent/core-concepts).

## Suite recommandée

1. Chemin court pour localiser un bouton : Models API, dernière image de fenêtre,
   état textuel compact et aucun raisonnement long ; mesurer sur de vraies demandes.
2. Historique du coach : résumé de la tâche, dernière instruction, interaction et
   résultat observé ; une image récente par défaut, jusqu’à trois si la transition
   demande une comparaison. Ne pas rejouer tout le raisonnement.
3. Crop immutable avec origine écran, dimensions, échelle, horodatage et identité
   de fenêtre. Transformer les coordonnées relatives au crop avant le dessin ;
   l’overlay actuel suppose encore le plein écran.
4. Conserver le chemin Agents pour les tâches qui demandent recherche, planification
   ou récupération après erreur. Comparer temps jusqu’à consigne utilisable,
   exactitude et coût, pas seulement premier token.
5. DGX comme variante locale à comparer, sans basculer automatiquement tout le
   coaching sur la seule base de ce microbenchmark.

## Reproduction et preuves

Script : `scripts/benchmark_holo_latency.py`. Il prend une image autorisée et
des endpoints OpenAI compatibles ; il ne capture pas l’écran. Les secrets viennent
de variables d’environnement ou d’un fichier privé, jamais des arguments ou logs.
Les résultats JSON restent hors Git ; le résumé Markdown ne contient pas l’image.

```sh
python scripts/benchmark_holo_latency.py \
  --image /chemin/prive/capture-publique.png --image-label h-docs-full \
  --target 'the Copy page button near the top right of the Cloud browser documentation, excluding its dropdown arrow' \
  --endpoint cloud=https://api.hcompany.ai/v1 \
  --endpoint dgx=http://127.0.0.1:PORT_LOCAL/v1 \
  --auth-env cloud=HAI_API_KEY --auth-env dgx=DGX_BENCH_TOKEN \
  --env-file /chemin/prive/benchmark.env \
  --trials 5 --warmups 1 --output-dir /chemin/prive/nouvel-essai
```

Le port local et son relais doivent être préparés séparément ; une clé factice
ne fonctionne pas avec le serveur vLLM privé existant. Le script ne modifie ni
les services GPU ni leur authentification.

Preuves conservées hors Git sur le Mac :
`~/Library/Application Support/HCompanionResearch/benchmarks/holo4-latency-2026-11-08/`
(`full-measured/results.json`, `crop-measured/results.json`, `comparison.json`).
Fixtures et manifeste : sous-dossier `fixtures/manifest.json` de cette archive privée.
Empreintes SHA256 :

- Complète : `73a5decff71bb0fa0ff0295543c11c3c9c2d9f7173ea5ca46a005555e9c44555`.
- Crop : `0dd266fa26d402298b7dc3bf142866fa4bee70d8de4282759e3f75417ddf997b`.

Ces preuves ne sont pas des labels humains et ne constituent pas
un dataset d’entraînement. Le score mesure seulement la localisation d’une cible
connue sur une image fixe.

Validation du script : **32 tests hors réseau passent**, notamment rôle initial
vide, contenu de raisonnement, arguments d’outil fragmentés, usage absent, flux
interrompu, nom d’outil incorrect, JSON final invalide et réponse tronquée. Une
réponse structurellement valide reste distincte d’un pointage géométrique correct.

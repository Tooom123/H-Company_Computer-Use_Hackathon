# Holo4 sur Verda : mission de comparaison de latence

État au 8 novembre 2026. Document de passation ; aucune instance créée ni dépense engagée par cette préparation.

## But et choix proposé

Comparer **la même décision du coach V2** sur l’API H, le DGX Spark existant et une instance Verda. Une machine dédiée peut améliorer le délai, mais le gain reste à mesurer. Le dernier tour réel rapporté a consommé **5 010 tokens d’entrée, 186 de sortie et 19,45 s entre le début de lecture AX et la réponse complète** : ce n’est ni un TTFT ni une mesure du calcul GPU seul. Les prochaines traces distinguent `observation_ms`, `model_ms` et la relecture AX `refresh.latency_ms`.

Commencer par **1 × H200 141 Go, Holo4-35B-A3B-FP8** ; alternative si indisponible : **1 × H100 80 Go, même FP8**. H publie ce checkpoint et recommande vLLM **0.28 ou supérieur** pour Holo4. FP8 est pris en charge sur Hopper. La marge mémoire du H200 facilite cet essai sans parallélisme entre GPU. [Checkpoint officiel](https://huggingface.co/Hcompany/Holo4-35B-A3B-FP8), [recette H](https://hub.hcompany.ai/agents-api/local-inference), [compatibilité FP8 vLLM](https://docs.vllm.ai/en/latest/features/quantization/fp8/).

Ne pas recopier aveuglément la configuration **NVFP4 du Spark Blackwell** sur un H100/H200. Les variantes, kernels et précisions diffèrent ; noter la quantification dans les résultats et vérifier la qualité des décisions.

Prix publics consultés : H200 **6,440 USD/h**, H100 **4,938 USD/h**, à la demande, hors stockage. Vérifier le prix et la disponibilité dans la console avant commande. À titre de calcul, deux heures de H200 représentent **12,88 USD de calcul**, pas un devis global. Fixer avec Édouard un plafond et une heure d’arrêt ; les crédits disponibles ne constituent pas un budget à épuiser. Préférer une instance non interruptible pour ce premier benchmark. [Tarifs Verda](https://verda.com/pricing).

## 1. Réutiliser d’abord le Spark

Le serveur existe déjà : ne rien supprimer et ne pas le réinstaller.

- SSH : `ssh dgx1` ; modèle servi : `holo4-35b-a3b`.
- Poids : `/home/dgx/dejabu-holo/Holo4-35B-A3B-NVFP4`.
- vLLM 0.28.0 ; API distante : `http://127.0.0.1:8011/v1`.
- Le port **8010 est Holo3.1**, pas Holo4.
- Authentification : `VLLM_API_KEY` dans le fichier privé `/home/dgx/dejabu-holo/holo.env`. Ne pas afficher ni committer sa valeur.

Tunnel persistant depuis le Mac :

```sh
ssh -N -T -o ExitOnForwardFailure=yes -o ServerAliveInterval=30 \
  -L 127.0.0.1:18011:127.0.0.1:8011 dgx1
```

Base URL cliente : `http://127.0.0.1:18011/v1`. Réutiliser une connexion HTTP ; ne pas lancer un processus SSH par requête. Le handoff privé complet est `/Users/edouardfoussier/code/deja-bu/out/bruxelles-convergence/docs/passation-holo4-dgx-spark-2026-11-07.md`. Ses petits tests texte/vision réussis ne valident pas encore notre contrat de tool calling.

## 2. Préparer Verda

Après validation du budget, choisir une région proche du Mac et une image CUDA/vLLM compatible avec le GPU. Épingler version d’image, révision des poids, pilote et paramètres ; commencer avec vLLM 0.28.0 pour réduire les différences avec le Spark, puis adapter si nécessaire en documentant pourquoi.

Configuration de départ à vérifier contre `vllm serve --help` de la version installée :

```sh
vllm serve Hcompany/Holo4-35B-A3B-FP8 \
  --served-model-name holo4-35b-a3b \
  --host 127.0.0.1 --port 8011 \
  --max-model-len 8192 --max-num-seqs 1 \
  --enable-auto-tool-choice --tool-call-parser qwen3_coder \
  --reasoning-parser qwen3 \
  --chat-template-content-format openai
```

Les parsers ci-dessus reprennent la configuration existante du Spark ; leur compatibilité avec le checkpoint et le schéma exact doit passer le test ci-dessous. Les 8 192 tokens couvrent la requête actuelle ; recontrôler cette limite si le contexte augmente. Ne pas réserver d’emblée le contexte maximal du modèle.

Configurer une **clé locale distincte** dans l’environnement privé du serveur. Accès depuis le Mac par tunnel SSH lié à `127.0.0.1`, sur un autre port local que le Spark. Aucun port d’inférence public sans authentification et TLS. Ne jamais réutiliser la clé cloud H pour un endpoint Verda.

## 3. Valider le contrat avant de brancher l’app

Le coach V2 appelle directement **Models API `/v1/chat/completions`**, pas la boucle Agents API. Le point d’intégration est `agent/src/hcs_agent/coach_v2.py` : à cette date, endpoint H fixé dans le client. Ajouter ensuite une configuration explicite fournisseur / base URL / clé / modèle, avec H comme valeur par défaut.

Rejouer une requête **synthétique** construite avec le véritable générateur du coach, sans piloter le Mac. Garder identiques :

- Prompt système, question, arbre d’accessibilité fictif, schéma `coach_step`, limites de sortie.
- `temperature: 0`, `tool_choice: "required"`, outil `strict: true`, `chat_template_kwargs: {"enable_thinking": false}`.
- Aucun screenshot pour cette première comparaison : le chemin actuel utilise les contrôles AX en texte.

Valider le résultat avec le parseur/Pydantic réel : un appel attendu, JSON conforme, texte anglais, IDs réellement présents dans la fixture, trois points maximum pour le tour. Une réponse texte libre rapide ne vaut pas une décision utilisable. La documentation vLLM distingue appels obligatoires, schéma strict et parsers : ne pas accepter silencieusement un serveur qui ignore ces options. [Tool calling vLLM](https://docs.vllm.ai/en/latest/features/tool_calling/).

## 4. Mesurer une comparaison reproductible

1. Créer une fixture de tour autour de **5 000 tokens** et deux fixtures courtes (question simple, prochaine étape). Conserver le même JSON par fournisseur, hors modèle et authentification. Une fixture synthétique proche du tour n’est pas la trace réelle des 19,45 s.
2. Tester à **concurrence 1**. Séparer démarrage/chargement du serveur, premier appel et régime chaud. Après échauffement, faire au moins **10 requêtes par cas et fournisseur** ; 10 donne seulement une première estimation de p95. Alterner les fournisseurs pour limiter les effets d’heure et de réseau.
3. Mesurer en SSE : premier delta utile de contenu/arguments, puis dernier delta et **décision complète validée**. Un événement vide ou de rôle ne compte pas comme TTFT. Vérifier que H accepte le streaming avec ces outils ; sinon marquer TTFT « indisponible », sans l’inférer de la durée totale.
4. Journaliser séparément appels avec préfixe répété et premiers préfixes. Noter cache activé, tokens cachés si exposés ou état « inconnu ». Un cache chaud n’est pas une mesure de départ à froid.
5. Rapporter p50/p95, tokens entrée/sortie réels, taux de décisions valides et erreurs. Le modèle peut produire des longueurs différentes même à température zéro : les 186 tokens historiques ne sont pas un quota à forcer. Mesurer aussi fin de dictée → première consigne affichée/audible une fois l’intégration validée.
6. Ensuite seulement, refaire une courte série à **concurrence 4**, en adaptant `max-num-seqs`. Le débit de batch ne remplace pas la latence d’un utilisateur seul.

CSV conseillé : `provider, model_revision, precision, runtime, fixture, cache_state, concurrency, input_tokens, output_tokens, ttft_ms, response_ms, valid_decision_ms, schema_ok, target_ids_ok, english_ok, error`.

Livrer script reproductible, fixture synthétique, tableau comparatif et recommandation. Garder clés, véritables captures/arbres AX et traces privées hors Git. Ne basculer la démo que si les décisions restent correctes et le gain se répète ; conserver le retour à H par configuration. Arrêter l’instance de benchmark à l’échéance convenue et vérifier les ressources de stockage encore facturées.

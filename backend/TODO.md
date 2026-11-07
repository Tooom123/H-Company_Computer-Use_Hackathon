# TODO — Tom (support, données, landing)

Périmètre (README, PRD) : stockage, dossier d'escalade, tableau de bord, regroupement simple, données de démo.
Mis à jour le 7 novembre 2026 (soir). Dépôt : dimanche 8 novembre, **14h00**.

## État du dépôt

`main` n'a toujours que le squelette (`84e2b83`). Rien n'est fusionné, aucune PR n'est ouverte.

| Branche | Qui | Contenu | Lien avec nous |
| --- | --- | --- | --- |
| `matteo` (26 commits) | Matteo | Agent H complet : modes `act` et `guide` (l'agent pointe, l'utilisateur clique), 5 procédures Odoo CRM, vérification en session H séparée en lecture seule, arrêt local, Linkup (`lookup_docs`), overlay. **Contrat étendu** : `mode`, `guidance`, `knowledge`, `timings.stop_latency_s`… | Nos 4 cas de démo valident aussi contre son nouveau schéma. Son agent **n'envoie pas** encore le rapport à `POST /cases`. |
| `edouard/gaze-desktop` (18 commits) | Edouard | Vision Lab Electron (WebGazer, calibration, zones de tête, recadrage, Holo Models API) et **pilote vocal Odoo** (Gladia → plan → approbation atteinte en réel). Scénarios Odoo inventaire et achats. | Le pilote embarque **notre `Store` (`bd3b2ca`)** directement, sans passer par l'API HTTP. |
| `edouard/gaze-research-protocol` | Edouard | Protocole de recherche du regard (doc) | — |
| `tom` | Tom | Backend support (`bd3b2ca`) + 1re landing | Utilisé par le pilote d'Edouard |
| `feature/tom-landing` | Tom | Landing stylo rouge, pompier, paywall Stripe + `POST /billing/checkout` | Modifs non commitées : ratures qui suivent le scroll, correction définitive |
| `feature/tom-gaze-heatmap` | Tom | Module heatmap ruche pour le tracker d'Edouard | À intégrer côté Edouard |

Technos partenaires présentes : **H** (obligatoire), **Gladia** (voix, Edouard), **Linkup** (Matteo), **Stripe** (nous).
Aucune trace de Devin pour le prix « Best Use of Devin ».

## Fait

- [x] Backend support : `POST /cases` / `/events`, auth, regroupement, dossier d'escalade, dashboard, cas de démo, 13 tests
- [x] Paiement Stripe Checkout en mode test (`/billing/checkout`, clés live refusées)
- [x] Landing : 3D, Company → Companion, ratures au scroll, pompier, offres
- [x] Heatmap du regard : module, page de test, 12 tests, README pour Edouard

## La suite, par priorité (barème : 50 % computer use + fiabilité)

### P0 — ce soir : que la démo de bout en bout passe par notre support

- [ ] **Commiter et pousser** les derniers correctifs de la landing (`feature/tom-landing`)
- [ ] **Contrats** : récupérer les schémas de `matteo` dans notre branche, relancer les tests du backend, vérifier qu'un vrai rapport de son agent passe la validation (`mode`, `guidance`, `knowledge`)
- [ ] **Brancher l'agent sur le backend** : à la fin d'une intervention, `POST /cases` avec `Authorization: Bearer $HCS_INGEST_TOKEN`. Le mieux : je propose à Matteo un petit client (`HCS_BACKEND_URL` optionnel, sans effet s'il est absent). Une fois le rapport final envoyé, le pilote d'Edouard peut aussi utiliser l'API plutôt que le `Store` en direct.
- [ ] **Premier cas réel** (non simulé) visible dans le dashboard, depuis le Mac de démo

### P1 — demain matin : ce que le jury verra

- [ ] **Dashboard** : afficher ce que l'agent apporte maintenant
  - le mode `guide` / `act`
  - les sources Linkup (`knowledge`) dans le dossier d'escalade : « ce que dit la doc » à côté du blocage
  - la latence d'arrêt mesurée (`timings.stop_latency_s`)
- [ ] **Regroupement sur cas réels** : au moins 3 cas réels, deux similaires et un différent (checklist de démo)
- [ ] **Ne pas montrer les données de démo pendant le pitch** : bouton ou `reset-demo` avant la présentation
- [ ] **Landing ↔ produit** : le bouton « Open the support dashboard » et le paywall fonctionnent sur la machine du pitch (clé `sk_test_` Stripe, backend lancé)

### P2 — si le temps le permet

- [ ] Champ `user_ref` dans le rapport (utilisateurs distincts), à proposer à Matteo
- [ ] Suivi en direct des sessions dans le dashboard (`AgentEvent`)
- [ ] PR `tom` → `main` relue par un coéquipier, puis `feature/tom-landing`

### À trancher avec l'équipe

- Qui fusionne quoi dans `main` avant 14h, et qui le contrôle ?
- La démo passe-t-elle par l'app Electron d'Edouard avec le pilote vocal, ou par l'API de Matteo ?
- Script de remise à zéro Odoo : aucune branche n'en a. Qui s'en charge ?

## Notes

- `uv run <script>` plante sans sortie dans notre environnement (code 120) : utiliser `.venv/bin/hcs-backend`.
- Ports : agent 8765, backend 8766, pilote vocal 8767, landing 5173, heatmap 5174.
- Convention de branches : `tom/<sujet>` est impossible tant que la branche `tom` existe, d'où `feature/tom-*`.

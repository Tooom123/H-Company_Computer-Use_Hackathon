# TODO — Tom (support & données)

Périmètre (README, PRD) : stockage, dossier d'escalade, tableau de bord, regroupement simple, données de démo.
Mis à jour le 7 novembre 2026.

## Fait (branche `tom`)

- [x] `POST /cases` : `InterventionReport` validé contre `contracts/`, stocké tel quel (SQLite, `runs/`)
- [x] `POST /events` : `AgentEvent` stockés par session
- [x] Authentification : jeton pour l'agent, login/mot de passe pour le support ; aucune lecture publique
- [x] Regroupement : même logiciel + même catégorie, puis similarité des mots-clés du blocage ; sources consultables
- [x] Dossier d'escalade JSON + Markdown : décision attendue, essais, étapes ; déclaré utilisateur / agent / observé séparés
- [x] Captures transmises au support seulement avec l'accord de l'utilisateur
- [x] Dashboard HTML : KPIs, groupes, cas, badges SIMULATED / DEMO
- [x] 4 cas de démo simulés (1 résolu, 2 permissions similaires, 1 configuration) + `seed-demo` / `reset-demo`
- [x] 11 tests (`uv run pytest backend`)

## À faire

- [ ] **Base Odoo de test** (bloquant) : obtenir URL + compte admin, puis créer les données fictives
      — opportunité « Acme Démo », commercial « Demo Sales », utilisateur aux droits limités pour le cas bloqué
- [ ] **Script de remise à zéro** dans `scripts/` (XML-RPC Odoo) : état initial reproductible, vérifié avant chaque run
- [ ] Brancher l'agent de Matteo : envoi du rapport final vers `POST /cases` (`Authorization: Bearer`, port 8766)
- [ ] Premier cas réel reçu de l'agent (non simulé) visible dans le dashboard
- [ ] Proposer à Matteo un champ `user_ref` dans `InterventionReport` (utilisateurs distincts) — remplace l'en-tête `X-HCS-User`
- [ ] Au moins 3 cas **réels** pour le regroupement : deux similaires, un différent (checklist de démo)
- [ ] Ouvrir la PR `tom` → `main`, relue par un coéquipier
- [ ] Optionnel : suivi en direct des sessions dans le dashboard (à partir des `AgentEvent`)
- [ ] Optionnel : 2ᵉ techno partenaire côté backend (ex. Linkup pour sourcer la « cause supposée »)

## Notes

- `uv run <script>` plante sans sortie dans notre environnement (code 120) : utiliser `.venv/bin/hcs-backend`.

# The Computer Use Hackathon — H Company × 42AI (Paris)

> Récap équipe · 7–8 novembre 2026 · À jour au samedi 7 novembre 2026
> Sources : PDF de kickoff, page Luma, mails des organisateurs, docs H Company. Les points marqués ⚠️ sont à confirmer.

---

## 1. L'essentiel

| | |
|---|---|
| **Lieu** | La Maison by Motier Ventures, 2 Rue des Mathurins, 75009 Paris |
| **Dates** | Samedi 7 nov 10h30 → Dimanche 8 nov 14h00 (dépôt) |
| **Organisation** | 42AI, powered by H Company |
| **Format** | Présentiel · 700 candidatures · ~100 builders dans la salle |
| **Équipes** | 1 à 4 personnes · acceptation **individuelle** (un coéquipier non accepté ne peut pas venir) |
| **Défi** | Construire un agent qui navigue sur des sites, applications de bureau ou interfaces logicielles pour accomplir une tâche réelle et utile |
| **Livrable** | Une démo qui montre clairement le problème, les actions de l'agent et le résultat |
| **Cagnotte** | 13 000 € en cash + crédits + avantages Morning |

---

## 2. Règles

- **H Company (computer use) : obligatoire.**
- **Deuxième techno obligatoire : Gladia ou Linkup.** Devin : crédits offerts, à utiliser. Stripe : optionnel (paywall, facturation).
- ⚠️ Le PDF de kickoff dit encore « au moins 4 des 5 technologies partenaires ». La règle mise à jour (H + au moins une autre) nous a été communiquée : **la faire confirmer aux mentors/organisateurs**.
- **Dépôt : dimanche 14h00 pile.**
- **Accès au lieu :** dernière entrée samedi 21h. Si on sort après 21h, retour impossible avant 8h dimanche. On peut rester sur place toute la nuit.
- À apporter : laptop, chargeur, casque-micro (salle bruyante).
- Wi-Fi, Discord et plateforme du hackathon : voir la slide « Let's Hack » du PDF.

---

## 3. Barème du jury

| Critère | Poids |
|---|---|
| **Usage du computer use** | **25 %** |
| **Exécution technique et fiabilité** | **25 %** |
| Utilité et impact | 20 % |
| Originalité et innovation | 15 % |
| UX et contrôle utilisateur | 10 % |
| Clarté de la démo et Q&R | 5 % |

> 50 % du barème porte sur le computer use et la fiabilité : une démo stable vaut plus qu'une démo ambitieuse qui plante.

---

## 4. Planning (heure de Paris)

| Samedi 7 nov | |
|---|---|
| 09:00 | Check-in |
| 09:45 | Kickoff, présentation des partenaires et des prix |
| **10:30** | **Début du hacking** |
| 12:30 | Déjeuner |
| 16:00 | Goûter |
| 19:00 | Dîner |
| 21:00 | Dernière entrée |

| Dimanche 8 nov | |
|---|---|
| 08:00 | Réouverture du lieu |
| 09:00 | Petit-déjeuner |
| 12:30 | Déjeuner |
| **14:00** | **Deadline de dépôt** |
| 14:30 | Premier tour de jury (Luma) |
| 15:45 | Pitchs finaux |
| 17:15 | Délibération du jury (Luma) |
| 17:45 | Annonce des gagnants |
| 18:00 | Drinks et networking |
| 20:30 | Fermeture |

**Temps de build effectif : ~27h30** (samedi 10h30 → dimanche 14h00).

---

## 5. Prix

| Prix | Montant |
|---|---|
| 🥇 1re place | 5 000 € par équipe |
| 🥈 2e place | 3 000 € par équipe |
| 🥉 3e place | 2 000 € par équipe |
| Best Use of **Gladia** | 1 000 € (Luma) · ⚠️ slides à jour : 3 000 $ de crédits STT |
| Best Use of **Devin** | 1 000 |
| Best LinkedIn Post | 500 € |
| Best X Post | 500 € |

**Morning (en plus de la cagnotte) :** 1 mois de Morning Nomade offert à chaque membre des 3 équipes du podium (pas pour un prix sponsor ou social seul) · −50 % sur les 2 premiers mois pour tous les participants (formulaire communiqué sur place).

---

## 6. Technos partenaires

| Partenaire | Ce que c'est | Notes utiles pour nous |
|---|---|---|
| **H Company** *(obligatoire)* | Agents computer use propulsés par les modèles Holo | Agents API (`hub.hcompany.ai/agents-api`), clés et crédits sur `platform.hcompany.ai` (code promo à saisir dans Billing). Démos : `github.com/hcompai/agents-api-demos`. Environnements : navigateur cloud, **Chrome local** (SDK Python), **bureau local** (écran principal uniquement). Pilotage en cours de session, outils custom, sous-agents, skills. Limites vues sur la capture : Free ≈ 60 sessions/mois et 3 simultanées · Builder 20 $/mois ≈ 1 000 sessions et 10 simultanées. |
| **Gladia** | Speech-to-text temps réel et asynchrone, 100+ langues, diarisation, audio intelligence | Selon leur doc : partiels très rapides, timestamps par mot, code-switching, vocabulaire personnalisé, sentiment. Prix « Best Use of Gladia ». |
| **Cognition (Devin)** | Ingénieur logiciel autonome (Cloud, Desktop, CLI) | Crédits offerts. À utiliser pour le code ennuyeux (scripts de pannes, HUD, tests) et **garder la trace des sessions** pour le prix. |
| **Linkup** | API de recherche web pensée pour les agents | Réponses sourcées ou JSON structuré, endpoint de fetch. |
| **Stripe** *(optionnel)* | Infrastructure de paiement | Billing avec compteurs d'usage (facturation « à la résolution »), Checkout en mode test. Issuing for agents : ⚠️ accès à vérifier avec le mentor Stripe. |
| **Morning** | Coworking à Paris | Avantages ci-dessus (pas une techno). |

---

## 7. Notre sujet *(à ajuster)*

> ⚠️ Section rédigée d'après la dernière piste discutée : **support IT / client à distance par FaceTime, sur parc 100 % Mac**. Corriger si le sujet retenu est différent.

**Pitch en 3 phrases.** Un employé (ou client) sur Mac appelle un agent par FaceTime. L'agent voit son écran partagé, diagnostique à voix haute, et, avec l'accord de l'utilisateur, prend la main à distance pour résoudre le problème. Il vérifie l'identité de l'appelant, trace tout ce qu'il fait et ne facture que les problèmes résolus.

**Pourquoi c'est du computer use pur.** L'écran du client arrive comme un flux vidéo dans une fenêtre FaceTime : pas de DOM, pas d'API. L'agent H pilote le bureau du Mac « support » (écran, souris, clavier) et agit à travers ce flux.

**Autonomie graduée (UX / contrôle)**
1. **Niveau 0** : l'agent parle seulement.
2. **Niveau 1** : il **dessine** sur l'écran du client pour montrer le bouton.
3. **Niveau 2** : il demande le **contrôle à distance** (prompt Apple, accepté par l'utilisateur).

**Architecture**
```
Mac "client" (cassé par script)  ⇄  FaceTime  ⇄  Mac "agent"
                                                   ├─ H desktop agent (computer use)
                                                   ├─ Gladia : écoute temps réel (audio FaceTime via périphérique virtuel)
                                                   ├─ TTS : voix de l'agent + narration pendant les actions
                                                   ├─ HUD de statut caché à la capture d'écran de l'agent
                                                   └─ Journal + ticket + compteur de résolutions (Stripe)
```

**Briques à construire**
- **Banc de pannes** (Devin) : scripts qui cassent le Mac de démo de façon répétable (mauvais périphérique audio, permission refusée, imprimante bloquée…) et le réinitialisent.
- **Vérification d'identité** : code affiché sur un canal authentifié, appareil connu ; **jamais de contournement de MFA**.
- **Linkup** : recherche de l'erreur ou du symptôme dans la doc Apple, avec sources.
- **Stripe** : un événement de compteur par panne résolue, facture en mode test.
- **Relais vers un humain** : résumé, état de l'écran, étapes déjà tentées.
- **Journal complet** des actions de l'agent (piste d'audit) et ticket automatique.

**Pistes bonus**
- Jour 1 d'un nouvel arrivant : l'agent guide dans les approbations que le MDM ne peut pas faire (enrôlement, permissions caméra / micro / enregistrement d'écran).
- Support accessible par défaut : un appel vocal est accessible à ceux pour qui un portail de tickets ne l'est pas.
- Même moteur pour le support client d'un éditeur de logiciels Mac.
- Chaque résolution devient une recette réutilisable.

**Métriques à afficher**
- Taux de résolution sur N pannes, rejouées plusieurs fois.
- Temps moyen de résolution.
- Nombre d'actions de l'agent et nombre d'interventions humaines.
- Zéro action hors périmètre.

---

## 8. Comment on adresse le barème

| Critère | Notre réponse |
|---|---|
| Computer use (25 %) | Interface en pixels uniquement (flux FaceTime), plusieurs applications (FaceTime, Réglages Système, applis tierces) |
| Fiabilité (25 %) | Banc de pannes rejoué, métriques de réussite, mode de repli, vidéo de secours |
| Utilité (20 %) | Les MDM ne peuvent pas accorder caméra / micro / enregistrement d'écran ; les agents d'IT helpdesk actuels agissent par API dans Slack / Teams |
| Originalité (15 %) | Voix + écran + mains, autonomie graduée Apple-native, vérification d'identité, facturation à la résolution |
| UX / contrôle (10 %) | Trois niveaux d'autonomie, consentement natif Apple, arrêt immédiat en raccrochant |
| Démo (5 %) | « J'appelle mon Mac cassé » : une histoire de 15 secondes puis l'action |

---

## 9. Plan de route

**Samedi**
- 10h30 → 13h : deux Macs prêts, FaceTime + partage + contrôle fonctionnels, agent H qui clique dans la fenêtre partagée.
- 13h → 19h : voix (Gladia + synthèse vocale), niveau 1 (annotation) et niveau 2 (contrôle), 3 pannes de base reproductibles.
- 19h → minuit : vérification d'identité, journal / ticket, compteur Stripe, banc de pannes complet.

**Dimanche**
- 8h → 11h : 20 exécutions chronométrées, métriques, correction des échecs, vidéo de secours enregistrée.
- 11h → 14h : README, pitch, posts LinkedIn / X (GIF de 30 s), **dépôt avant 14h00**.

**À couper en premier** : fonctionnalités bonus, pas le protocole de mesure.

---

## 10. Risques et garde-fous

- **FaceTime / partage d'écran instable** : des utilisateurs signalent des pannes du partage via Messages sur Sequoia et Tahoe. Tester le chemin FaceTime tout de suite ; plan B : partage VNC par adresse IP.
- **Deux Macs nécessaires** (macOS 14 ou plus selon Apple ; une source dit 15), compte Apple dédié à l'agent.
- **Permissions macOS** de l'agent sur le Mac « support » (accessibilité, enregistrement d'écran) : à tester.
- **Limites Apple du contrôle à distance** : pas de modification du compte Apple, pas de paiements, pas d'effacement ; Touch ID désactivé pendant la session. Raccrocher met fin au contrôle.
- **Données et confiance** : Macs de test uniquement, aucune donnée personnelle, consentement et bandeau si l'appel est enregistré.
- **Ingénierie sociale** : l'agent ne contourne jamais la MFA et ne prend pas une demande verbale pour une approbation.
- **Concurrence** : on n'a pas vérifié en profondeur le marché ; ne pas affirmer « premier ».

---

## 11. À faire dans l'heure

- [ ] Faire confirmer la règle des technos (H + 1 autre) aux mentors.
- [ ] Récupérer la clé API H et saisir le code de crédits.
- [ ] Choisir la 2e techno obligatoire (Gladia ou Linkup) et créer le compte.
- [ ] Tester FaceTime : appel, partage d'écran, demande de contrôle, sur les deux Macs.
- [ ] Tester l'agent H sur le bureau local (écran principal).
- [ ] Demander au mentor Stripe l'accès à Issuing for agents (si utile) et la facturation à l'usage en mode test.
- [ ] Lancer Devin sur le banc de pannes.
- [ ] Répartir les rôles (agent / voix / banc de pannes / UI-démo-pitch).

---

## 12. Liens

- Docs Agents API : `https://hub.hcompany.ai/agents-api`
- Plateforme H : `https://platform.hcompany.ai`
- Démos H : `https://github.com/hcompai/agents-api-demos`
- Plateforme du hackathon : `https://builderbase.com/event/h-company-42ai-computer-use-agents-hackathon` ⚠️ (lien reconstitué d'après une slide)
- Docs Apple : « Request or give remote control in FaceTime on Mac »

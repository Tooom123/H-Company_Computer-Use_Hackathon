"""H support tasks, with operator-only answer rubrics and explicit account bindings.

Loading a card never starts a session. The default view is safe to give the actor;
the evaluator must opt in to the rubric. Public tickets are synthetic fixtures,
not claims about a customer's account or evidence of successful human coaching.
"""

from copy import deepcopy
import re
from string import Template
from urllib.parse import parse_qsl, unquote, urlsplit


DOCS_ORIGIN = "https://hub.hcompany.ai"
PLATFORM_ORIGIN = "https://platform.hcompany.ai"
CATALOG_VERSION = "2026-11-08.1"
_URL_BINDINGS = {"session_url", "comparison_session_url"}
_ID_BINDINGS = {"session_id", "comparison_session_id"}
_GUARD = (
    " Réponds en français en t'appuyant sur les pages consultées et cite leurs liens. "
    "Reste dans les origines autorisées. Ne crée, ne modifie, ne relance et ne supprime "
    "aucune ressource. N'ouvre ni facturation, ni gestion des clés, ni contenu d'un coffre. "
    "Ne révèle aucun identifiant secret. Les exemples de configuration restent des "
    "brouillons dans ta réponse ; n'exécute aucune commande. Si une preuve n'est pas "
    "accessible, indique ce qui manque au lieu de l'inventer."
    " Sépare explicitement Observations, Hypothèses et Inconnues. Pour chaque état "
    "ou mesure réel, cite une preuve accessible (écran, événement de trace ou relevé "
    "API déjà fourni), avec son libellé et son unité ; sinon écris inconnu. Ne fais "
    "pas d'appel API pour compléter ces données. Les nombres d'un ticket fictif "
    "sont les données de l'exercice, pas des observations du compte. Une heure "
    "affichée n'est pas une durée : calculer une durée exige deux bornes dont le "
    "sens est établi et que tu cites. Ne déduis jamais des tokens ou un coût du "
    "temps, des pixels ou du nombre de captures. Un statut terminal, y compris "
    "interrupted, ne suffit pas à prouver un échec ni une réussite métier. Examine "
    "la réponse, les preuves et leur chronologie ; si la cause de clôture n'est "
    "pas observable, elle reste inconnue. Une explication plausible ne devient "
    "pas un constat, et une information absente ne devient pas zéro."
)


def _case(number, title, question, page, family, criteria, sources, *, bindings=()):
    authenticated = bool(bindings)
    return {
        "id": f"HC{number:02d}",
        "title": title,
        "prompt": question + _GUARD,
        "source": "h-company",
        "catalog_version": CATALOG_VERSION,
        "task_kind": "account_readonly" if authenticated else "public_docs",
        "fixture_kind": "operator_bound_demo_session" if authenticated else "synthetic_support_ticket",
        "comparison_family": family,
        "start_url": "$session_url" if authenticated else DOCS_ORIGIN + page,
        "allowed_origins": [DOCS_ORIGIN, PLATFORM_ORIGIN] if authenticated else [DOCS_ORIGIN],
        "requires_auth": authenticated,
        "required_bindings": list(bindings),
        "requires_reference": False,
        "max_steps": 32,
        "max_time_s": 240,
        "expected_criteria": criteria,
        "reference_urls": [DOCS_ORIGIN + source for source in sources],
    }


_CASES = [
    _case(1, "Ma démo marche sur mon Mac, pas dans le navigateur cloud",
          "Ticket fictif : Odoo s'ouvre sur http://holo-rich.localhost:18091 sur mon Mac, "
          "mais une session H cloud ne le voit pas. Un collègue doit exécuter plusieurs "
          "tests sans immobiliser mon écran. À partir de la documentation, diagnostique "
          "le problème et compare deux architectures : accès local et navigateur cloud "
          "isolé. Donne un brouillon de configuration du navigateur pour la solution "
          "cloud avec une URL HTTPS fictive, explique comment gérer la connexion, puis "
          "propose trois vérifications avant de lancer. Ne tente pas d'ouvrir l'URL locale.",
          "/agents-api/browser/configuration", "network_and_runtime",
          ["Explique que localhost désigne l'hôte du navigateur ; un tunnel local au Mac n'est pas accessible depuis un navigateur cloud.",
           "Distingue host user_device du navigateur cloud par session ; conseille une URL HTTPS accessible au cloud pour l'isolation demandée.",
           "Le brouillon nomme un environnement web, host cloud, un mode d'observation et start_url ; aucune URL privée réelle n'est inventée.",
           "Sépare accessibilité réseau, authentification et disponibilité des données de démonstration ; distingue vault_id et browser_profile_id."],
          ["/agents-api/browser/configuration", "/agents-api/local-runtime", "/agents-api/vaults/overview"]),
    _case(2, "Dix places annoncées, mais mes tests attendent ou reçoivent 429",
          "Ticket fictif : le quota renvoie limit=10, active=4, available=6. Je veux "
          "garder deux places libres pour mes collègues et lancer douze cas indépendants. "
          "Combien de nouveaux workers lancer immédiatement ? Explique un ordonnanceur "
          "qui conserve cette réserve, puis compare queued, plan_limit, capacity et "
          "queue_full. Un appel de création a aussi expiré sans réponse : explique comment "
          "le retenter sans créer un doublon. N'interroge pas le quota réel et n'arrête "
          "aucune session. Termine par un tableau symptôme / vérification / action.",
          "/agents-api/sessions/quota", "quota_and_retry",
          ["Calcule quatre nouveaux workers au maximum pour le relevé fourni, avec relecture du quota et prise en compte des autres producteurs.",
           "Explique la file par défaut et queue=false ; ne lance pas les douze d'un coup si la réserve doit être garantie par l'ordonnanceur.",
           "Distingue plan_limit (user/org), capacity (platform), queue_full (org) et évite de conseiller l'arrêt des sessions locales contre capacity cloud.",
           "Prévoit backoff/Retry-After et même Idempotency-Key sur une relance de création ambiguë ; sépare données fictives et quota réellement observé."],
          ["/agents-api/sessions/quota", "/agents-api/plans-and-limits", "/agents-api/errors", "/agents-api/sessions/create"]),
    _case(3, "Une connexion réussie ne survit pas au prochain test",
          "Ticket fictif : la première session cloud a pu se connecter, la suivante "
          "redemande le mot de passe. Je veux quatre navigateurs isolés sans mettre le "
          "mot de passe dans le prompt ni écraser le profil d'un collègue. Explique la "
          "différence entre coffre de connexion et profil de navigateur, les options à "
          "renseigner explicitement, et le comportement souhaité de persistance. Une "
          "page affiche un code OTP : qui doit intervenir ? Prépare une procédure de "
          "diagnostic, sans visiter de page de connexion ni créer de coffre.",
          "/agents-api/browser/profiles", "authentication_and_profiles",
          ["Distingue credentials vault de cookies/local storage du browser profile ; ne promet pas qu'un vault conserve automatiquement une session connectée.",
           "Utilise un profil explicitement choisi ou vault_id, évite use_default_browser_profile implicite et laisse persist_browser_profile désactivé pour ces lecteurs concurrents.",
           "Explique le remplissage des secrets hors contexte du modèle et le matching des hôtes sans prétendre qu'un chemin URL restreint le coffre.",
           "Traite l'OTP/SSO comme un besoin de mécanisme autorisé ou d'intervention humaine ; n'invente pas de mot de passe ni de disponibilité d'un profil."],
          ["/agents-api/browser/profiles", "/agents-api/browser/configuration", "/agents-api/vaults/overview"]),
    _case(4, "Le JSON est valide et la session completed, est-ce réussi ?",
          "Ticket fictif : notre dashboard met toutes les sessions completed au vert. "
          "L'une renvoie un JSON conforme mais outcome=partial ; une autre échoue avec "
          "answer_validation ; une troisième reste awaiting_tool_results. Conçois la "
          "logique de statut et le rapport de support pour ces trois cas. Montre un petit "
          "schéma de réponse avec résultat déclaré, preuve observée et information "
          "manquante. Explique où diagnostiquer les appels d'outils et pourquoi une sortie "
          "structurée seule ne prouve pas le résultat métier. Ne soumets aucun outil.",
          "/agents-api/structured-output", "status_schema_and_evidence",
          ["Distingue status terminal, outcome auto-déclaré et réussite métier vérifiée ; completed/partial n'est pas un succès vérifié.",
           "Distingue answer_validation côté session de AnswerValidationError SDK ; propose de conserver l'erreur/payload expurgé plutôt que de valider aveuglément.",
           "Explique awaiting_tool_results : vérifier l'appel en attente et le worker chargé de répondre, sans confondre avec une panne de capture ou relancer à l'aveugle.",
           "Le schéma/rapport conserve declared_outcome et observed_result séparés et prévoit inconnu/manque de preuve ; il n'encode pas success=true par défaut."],
          ["/agents-api/structured-output", "/agents-api/errors", "/agents-api/sessions/overview", "/agents-api/custom-tools"]),
    _case(5, "Exporter une trace complète pour comprendre puis entraîner",
          "Ticket fictif : nous avons gardé seulement la réponse finale et un lien de "
          "screenshot qui expire. Nous voulons revoir une session et préparer ensuite "
          "des exemples d'entraînement. À partir de la documentation, écris un plan "
          "d'export reprenable : événements paginés, ressources, ordre des actions et "
          "observations, identifiants et provenance. Précise les contrôles pour savoir "
          "si l'archive est complète, et les labels qu'un humain devra encore fournir. "
          "Utilise uniquement des identifiants fictifs, ne télécharge pas de vraie trace "
          "et ne présente pas toute réponse finale comme un exemple d'entraînement valide.",
          "/agents-api/sessions/events", "trace_export_and_provenance",
          ["Parcourt toutes les pages d'events et traite changes comme suivi live, sans assimiler la première page à une archive complète.",
           "Résout les références de ressources (bucket/key ou file_id) et conserve les octets ; un lien S3 présigné temporaire n'est pas une archive durable.",
           "Préserve session/event IDs, ordre, observation liée à l'action, config/modèle/révisions et mesures disponibles ; indique manquantes les métriques absentes.",
           "Vérifie comptages, pagination, intégrité/empreintes et ressources manquantes ; sépare audit privé, données expurgées et export entraînement autorisé.",
           "Sépare réussite vérifiée, utilité humaine et provenance du label ; exclut les trajectoires fausses/incomplètes d'une SFT de succès et réserve des familles au test."],
          ["/agents-api/sessions/events", "/agents-api/sessions/resources", "/agents-api/sessions/event-object", "/agents-api/observe-and-steer"]),
    _case(6, "La même consigne change de comportement après une mise à jour",
          "Ticket fictif : deux agents utilisent la skill acme/support. Après une "
          "modification, une campagne n'est plus reproductible. Je veux corriger la "
          "documentation tout en conservant une baseline stable. Explique quand les "
          "références de skills sont résolues, propose une baseline épinglée et une "
          "candidate séparée, puis liste les métadonnées à conserver par session. "
          "Comment éviter qu'une édition concurrente écrase celle d'un collègue ? "
          "Prépare le protocole A/B et des fragments de configuration, sans enregistrer "
          "de skill, modifier d'agent ni activer de routine.",
          "/agents-api/skills/overview", "skill_revision_and_reproducibility",
          ["Explique nom nu latest contre name:N ; résolution à l'écriture de l'agent et à la création de session.",
           "Épingle une révision explicite pour la baseline et conserve dependency_revisions observées, pas seulement les noms demandés.",
           "Cite ETag/If-Match pour les éditions concurrentes sans effectuer de mutation.",
           "Compare même fixture/prompt/browser/model/politique de capture ; distingue changement de docs, modèle, skill et harness et réserve un jeu test non entraîné."],
          ["/agents-api/skills/overview", "/agents-api/skills/update", "/agents-api/sessions/retrieve"]),
    _case(7, "Vérifier ce que l'agent a réellement fait",
          "Ouvre uniquement la session de démonstration $session_id à $session_url. "
          "Retrouve la demande, le résultat déclaré et un couple observation/action "
          "pertinent dans sa trace. Explique ce que l'écran prouve réellement, ce qu'il "
          "ne permet pas de conclure, et la prochaine vérification métier. Cite les "
          "repères visibles (étape, horodatage ou identifiant), sans relancer la tâche.",
          "", "account_evidence_review",
          ["Reste sur la session autorisée et identifie sa demande sans parcourir les sessions d'autres utilisateurs.",
           "Sépare réponse finale, statut/outcome et preuve d'une action/observation précise, avec repère de trace visible.",
           "Énonce une conclusion vérifiable et les limites ; l'absence d'accès/preuve reste inconnu, jamais réussite inventée."],
          ["/agents-api/observe-and-steer", "/agents-api/sessions/events", "/agents-api/errors"],
          bindings=("session_id", "session_url")),
    _case(8, "Diagnostiquer un signalement sans provoquer une nouvelle exécution",
          "Ouvre uniquement l'essai de démonstration $session_id à $session_url. "
          "L'utilisateur dit : « rien ne s'est passé ». Retrouve la dernière étape "
          "observable, le statut et les erreurs réellement visibles, puis confronte-les "
          "à la documentation officielle sur https://hub.hcompany.ai. Vérifie si une "
          "réponse est présente avant de conclure à un blocage. Rédige un ticket : "
          "symptôme rapporté, faits observés, hypothèses, inconnues et prochain test "
          "minimal. Si aucun message d'erreur n'est visible, indique seulement cette "
          "absence et ce qu'il faudrait observer pour établir une cause. N'annule, "
          "ne relance et ne reprends pas la session.",
          "", "account_failure_diagnosis",
          ["Cite statut et éventuel code d'erreur réellement observés ; absence d'erreur visible et statut interrupted ne prouvent ni panne technique ni réussite métier.",
           "Localise la dernière réponse/action/observation et sa chronologie. Pour une fixture answered-then-closed, ne transforme pas la clôture après réponse en échec : la cause answered_then_cancelled_for_terminal_confirmation connue du juge ne doit pas être devinée par l'acteur si elle n'est pas visible. N'invente ni timeout, ni quota, ni défaut de livraison à partir d'un statut ou d'heures affichées.",
           "Consulte la documentation officielle et sépare faits, hypothèses et inconnues dans le ticket. Propose le plus petit contrôle permettant de départager les hypothèses sans le lancer ; si accès ou preuve manque, conserve cette limite et ne fabrique aucune cause."],
          ["/agents-api/errors", "/agents-api/sessions/overview", "/agents-api/custom-tools"],
          bindings=("session_id", "session_url")),
    _case(9, "Comparer deux essais sans inventer un gain de performance",
          "Compare uniquement les deux essais de démonstration $session_id à "
          "$session_url et $comparison_session_id à $comparison_session_url. "
          "L'équipe pense que le second est plus rapide et moins cher. Vérifie si les "
          "demandes et conditions sont comparables, relève résultat, durée et usage "
          "réellement affichés, puis indique quelles conclusions sont justifiées. "
          "Sépare temps d'attente et exécution si ces données sont disponibles. "
          "N'ouvre pas la facturation et ne transforme pas une taille d'image en tokens.",
          "", "account_paired_comparison",
          ["Identifie les deux sessions et vérifie tâches/états initiaux/configurations comparables avant tout pourcentage.",
           "Reporte mesures/unités visibles et valeurs manquantes ; pas de tokens/coûts déduits de pixels ou du nombre de captures.",
           "Vérifie résultat métier ou marque sa vérification manquante ; un essai plus court mais échoué n'est pas un gain équivalent.",
           "Ne généralise pas deux essais en preuve statistique ni capacité d'action en efficacité pédagogique."],
          ["/agents-api/observe-and-steer", "/agents-api/sessions/retrieve", "/agents-api/sessions/event-object"],
          bindings=("session_id", "session_url", "comparison_session_id", "comparison_session_url")),
    _case(10, "Préparer une reproduction fiable pour le support",
          "À partir de la seule session de démonstration $session_id à $session_url, "
          "prépare une fiche de reproduction pour un collègue. Relève les métadonnées "
          "visibles : agent/modèle, environnement, mode d'observation, dimensions, "
          "skills et révisions. Repère ce qui pourrait varier à la prochaine exécution. "
          "Distingue les valeurs présentes dans la trace de celles qu'un opérateur "
          "devra obtenir autrement. Propose un brouillon de checklist, sans exporter "
          "de cookies, révéler de secret ni créer un nouvel essai.",
          "", "account_reproduction_audit",
          ["Lie la fiche à la session autorisée et à ses preuves ; aucune métadonnée non visible n'est inventée.",
           "Distingue agent demandé, modèle effectivement observé et révisions résolues si disponibles ; précise les inconnues.",
           "Liste dépendances de reproductibilité (état du logiciel, viewport/mode, authentification sans secret, version du harness).",
           "Livre une checklist exploitable, sans mutations ni export d'identifiants/cookies."],
          ["/agents-api/sessions/retrieve", "/agents-api/skills/overview", "/agents-api/browser/configuration"],
          bindings=("session_id", "session_url")),
]


def _validate_binding(name: str, value: str) -> str:
    if not isinstance(value, str) or value != value.strip():
        raise ValueError(f"Invalid binding: {name}")
    if name in _ID_BINDINGS:
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", value):
            raise ValueError(f"Invalid session identifier: {name}")
    elif name in _URL_BINDINGS:
        parsed = urlsplit(value)
        decoded_path = unquote(parsed.path)
        if (parsed.scheme != "https" or parsed.netloc != "platform.hcompany.ai"
                or parsed.username or parsed.password or any(ord(c) < 32 for c in value)):
            raise ValueError(f"Expected an official HTTPS Agent View URL: {name}")
        if decoded_path in ("", "/") or re.search(
                r"(?:^|/)(?:settings|billing|vaults?|credentials?|api-keys?|auth)(?:/|$)", decoded_path, re.I):
            raise ValueError(f"Expected a scoped session URL, not account settings: {name}")
        if any(re.search(r"token|secret|password|api.?key|authorization|^code$", key, re.I)
               for key, _ in parse_qsl(parsed.query) + parse_qsl(parsed.fragment)):
            raise ValueError(f"Secret-bearing query parameters are not permitted: {name}")
    else:
        raise ValueError(f"Unknown binding: {name}")
    return value


def _view(card: dict, include_verifier: bool) -> dict:
    result = deepcopy(card)
    if not include_verifier:
        result.pop("expected_criteria")
        result.pop("reference_urls")
    return result


def load_sponsor_catalog(*, include_verifier: bool = False) -> list[dict]:
    """Return six runnable public tasks and four unbound account cards.

    Account cards are UI descriptions only until get_sponsor_scenario binds them.
    Runnable means structurally ready, not that authentication or quota was checked.
    """
    return [dict(_view(card, include_verifier), ready=not card["required_bindings"])
            for card in _CASES]


def get_sponsor_scenario(scenario_id: str, *, bindings: dict[str, str] | None = None,
                         include_verifier: bool = False) -> dict:
    """Return an actor card; require explicit, non-secret session bindings for auth cases.

    Origin checks are a catalogue input guard, NOT a browser/network access control.
    The operator must verify that each Agent View URL refers to the supplied demo ID.
    Runtime must still gate authentication and enforce navigation/action scope.
    """
    source = next((card for card in _CASES if card["id"] == scenario_id), None)
    if source is None:
        raise ValueError(f"Unknown sponsor scenario: {scenario_id}")
    values = bindings or {}
    required = set(source["required_bindings"])
    if set(values) != required:
        raise ValueError(f"Bindings must be exactly {sorted(required)}")
    validated = {name: _validate_binding(name, value) for name, value in values.items()}
    result = _view(source, include_verifier)
    result["prompt"] = Template(result["prompt"]).substitute(validated)
    result["start_url"] = Template(result["start_url"]).substitute(validated)
    result["bindings"] = validated
    result["ready"] = True
    return result

"""Resolve the demo product from observed foreground identity, never from the utterance.

Selection happens for each new request. Its product and surface stay bound to
that request; switching applications is not permission to move a running task.
"""
from dataclasses import dataclass
import re
from urllib.parse import unquote, urlsplit

from .contract import InterventionRequest, Mode


@dataclass(frozen=True)
class AppProfile:
    software: str
    label: str
    surface: str = "browser"
    bundle_id: str | None = None


PROFILES = {
    "h-company": AppProfile("h-company", "H Company"),
    "cognition": AppProfile("cognition", "Cognition / Devin"),
    "odoo": AppProfile("odoo", "Odoo · enriched demo"),
    "sap": AppProfile("sap", "SAP · Velotics trial"),
    "comfyui": AppProfile("comfyui", "Comfy Cloud · experimental"),
    "capcut": AppProfile("capcut", "CapCut Web · experimental"),
}
HOSTS = {
    "hub.hcompany.ai": "h-company", "platform.hcompany.ai": "h-company",
    "app.devin.ai": "cognition", "docs.devin.ai": "cognition",
    "cognition.ai": "cognition", "www.cognition.ai": "cognition",
    "cognition.com": "cognition", "www.cognition.com": "cognition",
    "holo-demo.62.83.79.254.sslip.io": "odoo",
    "my426318.s4hana.cloud.sap": "sap",
    "cloud.comfy.org": "comfyui", "docs.comfy.org": "comfyui",
    "www.capcut.com": "capcut", "capcut.com": "capcut",
}
DOC_HOSTS = {"hub.hcompany.ai", "docs.devin.ai", "cognition.ai", "www.cognition.ai",
             "cognition.com", "www.cognition.com", "docs.comfy.org"}
NATIVE_BUNDLE = "com.exafunction.windsurf"


def retrieval_query(text: str, software: str) -> str:
    # Local docs include French terminology. Expand retrieval only: the user's
    # goal and authorization stay verbatim, with no extra model call or network.
    aliases = {
        "odoo": {r"purchase|receiv|backorder": "achats commande réception reliquat quantités",
                 r"crm|opportunit|follow.up": "CRM opportunité activité relance échéance",
                 r"stock|product": "inventaire produit stock unités",
                 r"project|overdue|task": "projet tâche échéance étape statut"},
        "cognition": {r"mode|ask|agent": "choisir Ask Agent modes",
                      r"command|session|output|waiting|error": "lire session commandes sorties erreur",
                      r"review|file|change|test|diff": "modifications fichiers tests revue vérifier"},
    }
    extra = [words for pattern, words in aliases.get(software, {}).items() if re.search(pattern, text, re.I)]
    return " ".join([text, *extra])


def _profile_for_identity(info) -> AppProfile | None:
    """Recognize the product without authorizing access to its page contents."""
    if info is None or not info.is_front:
        return None
    if getattr(info, "native", False):
        if getattr(info, "bundle_id", None) == NATIVE_BUNDLE:
            return AppProfile("cognition", "Devin Desktop", "native", NATIVE_BUNDLE)
        return None
    try:
        parsed = urlsplit(info.url)
        if parsed.username or parsed.password:
            return None
        software = HOSTS.get(parsed.hostname)
        if parsed.scheme == "http" and parsed.hostname == "holo-rich.localhost" and parsed.port == 18091:
            software = "odoo"
        elif parsed.scheme != "https" or parsed.port not in (None, 443):
            return None
        if not software:
            return None
        return PROFILES[software]
    except (TypeError, ValueError):
        return None


def _restricted_section(info) -> str | None:
    if getattr(info, "native", False):
        return None
    parsed = urlsplit(info.url)
    if parsed.hostname in DOC_HOSTS:
        return None  # documentation about a vault is not a user's vault
    match = re.search(
        r"(?:^|/)(auth|login|signin|sign-in|credentials|secrets|vaults?|api-keys?|tokens?|billing|payments?|security)(?:/|$)",
        unquote(parsed.path).lower())
    return match.group(1) if match else None


def profile_for_page(info) -> AppProfile | None:
    profile = _profile_for_identity(info)
    return profile if profile and not _restricted_section(info) else None


class ContextUnavailable(ValueError):
    """An actionable local routing explanation, not a model answer or task result."""
    def __init__(self, message: str, *, reason: str, profile: AppProfile | None = None):
        super().__init__(message)
        self.status = {"mode": "automatic", "sources": 0, "availability": reason,
                       "label": f"{profile.label} · {reason.replace('_', ' ')}" if profile else "Select the product window"}
        if profile:
            self.status["software"] = profile.software


def unavailable_context(info, question: str = "") -> ContextUnavailable:
    profile = _profile_for_identity(info)
    section = _restricted_section(info) if profile else None
    if section in ("auth", "login", "signin", "sign-in"):
        return ContextUnavailable(f"You're on {profile.label}'s sign-in page. Finish signing in, then ask again.",
                                  reason="sign_in", profile=profile)
    if section:
        # These hints use only the question and known navigation, never vault contents.
        if profile.software == "h-company" and section in ("vault", "vaults"):
            if re.search(r"\bskills?\b", question, re.I):
                message = "For help with a skill, open Skills in H Company's sidebar, then ask again. I don't inspect the Vaults page."
            elif re.search(r"\b(?:cloud|agents?|browsers?|navigateur|nuage)\b", question, re.I):
                message = "For help running a cloud agent, open Agents in H Company's sidebar, then ask again. I don't inspect the Vaults page."
            else:
                message = "You're on H Company's Vaults page. Open View documentation, then ask again; I can explain vaults without inspecting credentials."
        else:
            message = f"I recognize {profile.label}, but I don't inspect credential, security or billing pages. Open another section or its documentation, then ask again."
        return ContextUnavailable(message, reason="protected_page", profile=profile)
    if info is None or not getattr(info, "is_front", False):
        return ContextUnavailable("Bring the product window to the front, then hold the talk key and ask again.", reason="not_in_front")
    if not getattr(info, "url", "") and not getattr(info, "native", False):
        return ContextUnavailable("I couldn't identify the active browser tab. Wait for the page to load, then ask again.", reason="page_unavailable")
    return ContextUnavailable("This window isn't one of the demo products. Switch to H Company, Odoo, SAP, Devin, Comfy Cloud or CapCut, then ask again.", reason="unsupported_product")


def request_matches_page(request: InterventionRequest, info) -> bool:
    """Do not apply automatic demo scoping to legacy requests."""
    if not request.parameters.get("automatic_context"):
        return True
    profile = profile_for_page(info)
    return bool(profile and profile.software == request.software
                and profile.surface == request.parameters.get("context_surface")
                and (profile.bundle_id or "") == request.parameters.get("context_bundle_id", ""))


def make_request(text: str, info, knowledge, previous: InterventionRequest | None = None):
    profile = profile_for_page(info)
    if profile is None:
        raise unavailable_context(info, text)
    if not text.strip():
        raise ValueError("Please say a question.")
    try:
        answer = knowledge.ask(retrieval_query(text, profile.software), software=profile.software, depth="fast")
    except Exception:
        answer = None  # missing documentation is not an accessibility failure
    docs = answer.as_text(4)[:9000] if answer and answer.answer else ""
    # A follow-up may use the previous goal only within the same product AND surface.
    prior = previous.goal if previous and previous.software == profile.software and (
        previous.parameters.get("context_surface") == profile.surface) else ""
    request = InterventionRequest(software=profile.software, goal=text, procedure_id="generic",
        mode=Mode.guide, autonomy=0, parameters={
            "automatic_context": "1", "context_surface": profile.surface,
            "context_bundle_id": profile.bundle_id or "", "context_label": profile.label,
            "doc_context": docs, "previous_goal": prior,
        })
    status = {"mode": "automatic", "software": profile.software, "label": profile.label,
              "surface": profile.surface, "sources": len(answer.sources) if answer and answer.answer else 0,
              "selected_at": "request", "request_id": request.session_id}
    return request, status


class ProductKnowledge:
    """Delegate retrieval to separate, already tenant-bound local corpora."""
    simulated = False

    def __init__(self, corpora):
        self.corpora = dict(corpora)

    def ask(self, query, software=None, depth="standard"):
        selected = self.corpora.get(software)
        return selected.ask(query, software=software, depth=depth) if selected else None

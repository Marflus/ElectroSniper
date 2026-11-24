from __future__ import annotations

import re
import unicodedata

from electrosniper.config import Settings
from electrosniper.models import FilterResult, RawListing


def normalize_text(text: str) -> str:
    if not text:
        return ""
    nfkd = unicodedata.normalize("NFKD", text.lower())
    cleaned = "".join(ch for ch in nfkd if not unicodedata.combining(ch))
    cleaned = re.sub(r"[^a-z0-9\s\+\-/]", " ", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()


# Exclusions strictes : catégorie -> liste de regex
STRICT_EXCLUSION_GROUPS: list[tuple[str, list[str]]] = [
    (
        "Alimentation / chargeur / câble",
        [
            r"\balimentation\b",
            r"\balim pc\b",
            r"\bbloc secteur\b",
            r"\bbloc d alimentation\b",
            r"\bchargeur seul\b",
            r"\bchargeur secteur\b",
            r"\btransformateur\b",
            r"\badaptateur secteur\b",
            r"\bcable\b",
            r"\bcables\b",
            r"\bcordon\b",
            r"\brallonge\b",
            r"\bmultiprise\b",
            r"\badaptateur\b",
            r"\bconvertisseur\b",
        ],
    ),
    (
        "Téléphone / smartphone",
        [
            r"\biphone\b",
            r"\bsmartphone\b",
            r"\btelephone portable\b",
            r"\bgalaxy s\d",
            r"\bgalaxy a\d",
            r"\bgalaxy z\b",
            r"\bgalaxy note\b",
            r"\bredmi\b",
            r"\bxiaomi mi\b",
            r"\bpoco\b",
            r"\bhuawei p\d",
            r"\bhuawei mate\b",
            r"\bgoogle pixel\b",
            r"\boneplus\b",
            r"\boppo\b",
            r"\bhonor \d",
            r"\bwiko\b",
            r"\brealme\b",
            r"\bvivo\b",
            r"\bmotorola\b",
            r"\bnokia\b",
            r"\bblackberry\b",
        ],
    ),
    (
        "Visserie / accessoires / boîtes vides",
        [
            r"\blot de vis\b",
            r"\bvisserie\b",
            r"\bboite vide\b",
            r"\bemballage vide\b",
            r"\bnotice seule\b",
            r"\bmanuel seul\b",
            r"\bcoque\b",
            r"\bhousse\b",
            r"\betui\b",
            r"\bprotection ecran\b",
            r"\bverre trempe\b",
            r"\btelecommande seule\b",
            r"\bsupport mural\b",
            r"\bstickers?\b",
            r"\bsac aspirateur\b",
            r"\bfiltre seul\b",
            r"\bsacoche\b",
            r"\bsac de transport\b",
            r"\bmallette vide\b",
            r"\bcoffret vide\b",
            r"\bvalise vide\b",
            r"^batterie\b",
            r"\bbatterie seule\b",
            r"\bbatterie d origine\b",
            r"\bairpods?(?!\s+max)\b",
            r"\becouteurs?\b",
            r"^jeu\b",
            r"^jeux\b",
            r"\bliste des partenaires\b",
        ],
    ),
    (
        "Écran / dalle physiquement cassé(e)",
        [
            r"\becran casse\b",
            r"\becran fissure\b",
            r"\becran brise\b",
            r"\becran pete\b",
            r"\becran explose\b",
            r"\becran fendu\b",
            r"\bdalle hs\b",
            r"\bdalle cassee\b",
            r"\bdalle fissuree\b",
            r"\bdalle brisee\b",
            r"\bvitre cassee\b",
            r"\bvitre fissuree\b",
            r"\blcd casse\b",
            r"\btactile casse\b",
            r"\btache d encre\b",
        ],
    ),
    (
        "Imprimante / scanner",
        [
            r"\bimprimante\b",
            r"\bphotocopieur\b",
            r"\bscanner\b",
            r"\bcartouche d encre\b",
            r"\btoner\b",
            r"\bdeskjet\b",
            r"\bofficejet\b",
            r"\becotank\b",
            r"\bpixma\b",
            r"\blaserjet\b",
        ],
    ),
    (
        "TV / moniteur",
        [
            r"\bteleviseur\b",
            r"\btv\b",
            r"\bsmart tv\b",
            r"\bqled\b",
            r"\boled tv\b",
            r"\bmoniteur\b",
            r"\becran pc\b",
            r"\becran gamer\b",
            r"\becran gaming\b",
            r"\becran 24\b",
            r"\becran 27\b",
            r"\becran 32\b",
            r"\becran 34\b",
            r"\becran incurve\b",
        ],
    ),
    (
        "Objet trop volumineux / gros électroménager",
        [
            r"\blave linge\b",
            r"\bmachine a laver\b",
            r"\blave vaisselle\b",
            r"\brefrigerateur\b",
            r"\bfrigo\b",
            r"\bcongelateur\b",
            r"\bseche linge\b",
            r"\bfour encastrable\b",
            r"\bcuisiniere\b",
            r"\bgaziniere\b",
            r"\bplaque induction\b",
            r"\bhotte aspirante\b",
            r"\bclimatiseur\b",
            r"\bradiateur\b",
            r"\bchauffe eau\b",
            r"\btondeuse\b",
            r"\bmotoculteur\b",
            r"\bgroupe electrogene\b",
            r"\bcompresseur\b",
            r"\bscie sur table\b",
            r"\bvelo electrique\b",
            r"\btrottinette\b",
            r"\bhome cinema colonne\b",
            r"\bpiano droit\b",
            r"\bbaby foot\b",
        ],
    ),
    (
        "Annonce de recherche ou service de réparation",
        [
            r"\brecherche\b",
            r"\bje recherche\b",
            r"\bachete vos\b",
            r"\brachat\b",
            r"\brachete\b",
            r"\bje rachete\b",
            r"\bachete tout\b",
            r"\brachete tout\b",
            r"\bje achete\b",
            r"\bj achete\b",
            r"\bachat cash\b",
            r"\bservice de reparation\b",
            r"\bje repare\b",
            r"\batelier reparation\b",
            r"\bdevis gratuit\b",
        ],
    ),
]

# Détection de matériel déjà ouvert / bricolé / passé chez un pro
ALREADY_OPENED_PATTERNS: list[tuple[str, str]] = [
    (r"\bdeja ouvert\b", "Déjà ouvert"),
    (r"\btente de reparer\b", "Tentative de réparation"),
    (r"\bessaye de reparer\b", "Tentative de réparation"),
    (r"\bvu par un reparateur\b", "Passé chez un réparateur"),
    (r"\bdiagnostic (d un )?reparateur\b", "Diagnostic pro déjà fait"),
    (r"\bdevis reparateur\b", "Devis réparateur existant"),
    (r"\bcarte mere hs\b", "Carte mère annoncée HS"),
    (r"\bbricole\b", "Appareil bricolé"),
    (r"\bdemonte\b", "Déjà démonté"),
    (r"\bdessoude\b", "Composant déjà dessoudé"),
    (r"\bmanque des vis\b", "Vis manquantes (déjà ouvert)"),
    (r"\birrecuperable\b", "Annoncé irréparable"),
]

# Catégories intéressantes et mots-clés associés
CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "consoles": [
        r"\bps5\b", r"\bps4\b", r"\bps3\b", r"\bps2\b", r"\bplaystation\b",
        r"\bswitch\b", r"\bnintendo\b", r"\bgame boy\b", r"\bgameboy\b",
        r"\b3ds\b", r"\b2ds\b", r"\bdsi\b", r"\bwii u\b", r"\bgamecube\b",
        r"\bpsp\b", r"\bps vita\b", r"\bxbox\b", r"\bsteam deck\b", r"\brog ally\b",
        r"\bconsole\b", r"\bmanette\b", r"\bdualsense\b", r"\bdualshock\b",
        r"\bjoy con\b", r"\bjoycon\b", r"\bvolant logitech\b", r"\bthrustmaster\b",
        r"\bfanatec\b",
    ],
    "informatique": [
        r"\bmacbook\b", r"\bimac\b", r"\bmac mini\b", r"\bthinkpad\b",
        r"\bpc portable\b", r"\bordinateur portable\b", r"\blaptop\b",
        r"\bpc gamer\b", r"\bpc fixe\b", r"\bmini pc\b", r"\bnuc\b",
        r"\bcarte graphique\b", r"\brtx\b", r"\bgtx\b", r"\bradeon\b", r"\brx \d{3,4}\b",
        r"\bnas\b", r"\bsynology\b", r"\bqnap\b", r"\basus rog\b", r"\bmsi\b",
        r"\bdell xps\b", r"\bprecision\b", r"\blatitude\b", r"\bprobook\b",
        r"\belitebook\b", r"\bzenbook\b", r"\bchromebook\b", r"\bclavier mecanique\b",
        r"\bserveur\b",
    ],
    "outillage": [
        r"\bmakita\b", r"\bdewalt\b", r"\bmilwaukee\b", r"\bbosch pro\b",
        r"\bbosch gsr\b", r"\bbosch gbh\b", r"\bfestool\b", r"\bmetabo\b",
        r"\bhilti\b", r"\bryobi\b", r"\bhikoki\b", r"\bparkside\b",
        r"\bperceuse\b", r"\bvisseuse\b", r"\bperforateur\b", r"\bmeuleuse\b",
        r"\bdisqueuse\b", r"\bscie circulaire\b", r"\bscie sauteuse\b",
        r"\bscie sabre\b", r"\bponceuse\b", r"\bdefonceuse\b", r"\bcle a choc\b",
        r"\bboulonneuse\b", r"\bmultitool\b", r"\boutillage\b", r"\belectroportatif\b",
    ],
    "audio": [
        r"\bampli\b", r"\bamplificateur\b", r"\bmarantz\b", r"\bdenon\b",
        r"\bonkyo\b", r"\byamaha\b", r"\bpioneer\b", r"\btechnics\b",
        r"\bplatine vinyle\b", r"\bplatine dj\b", r"\bcontroleur dj\b",
        r"\btable de mixage\b", r"\bsynthetiseur\b", r"\bsynthe\b",
        r"\bboite a rythme\b", r"\bpedale guitare\b", r"\bmulti effet\b",
        r"\benceinte\b", r"\bsonorisation\b", r"\bsonos\b", r"\bbose\b",
        r"\bjbl\b", r"\bmarshall\b", r"\bdevialet\b", r"\bharman kardon\b",
        r"\bcasque audio\b", r"\bcasque bluetooth\b", r"\bwh 1000\b",
        r"\bairpods max\b", r"\bsennheiser\b", r"\bfocal\b", r"\bbeyerdynamic\b",
        r"\binterface audio\b", r"\bcarte son\b", r"\bfocusrite\b",
    ],
    "photo": [
        r"\bappareil photo\b", r"\breflex\b", r"\bhybride\b", r"\bobjectif\b",
        r"\bcanon eos\b", r"\bsony alpha\b", r"\bsony a\d", r"\bnikon\b",
        r"\bfujifilm\b", r"\blumix\b", r"\bolympus\b", r"\bleica\b",
        r"\bgopro\b", r"\binsta360\b", r"\bdrone\b", r"\bdji\b", r"\bmavic\b",
        r"\bmini \d\b", r"\bcamescope\b", r"\bflash cobra\b", r"\bstabilisateur\b",
        r"\bgimbal\b", r"\bronin\b",
    ],
    "petit_electro": [
        r"\bmachine a cafe\b", r"\bexpresso\b", r"\bdelonghi\b", r"\bjura\b",
        r"\bsaeco\b", r"\bkrups\b", r"\bsage barista\b", r"\bbreville\b",
        r"\bkitchenaid\b", r"\bkenwood\b", r"\bthermomix\b", r"\bmonsieur cuisine\b",
        r"\brobot patissier\b", r"\brobot cuiseur\b", r"\bdyson\b", r"\bshark\b",
        r"\baspirateur balai\b", r"\baspirateur robot\b", r"\broborock\b",
        r"\broomba\b", r"\bairwrap\b", r"\bairfryer\b", r"\bninja\b",
        r"\bnettoyeur vapeur\b", r"\bkarcher\b", r"\bcentrale vapeur\b",
    ],
    "tablettes": [
        r"\bipad\b", r"\bgalaxy tab\b", r"\btablette\b", r"\bsurface pro\b",
        r"\bsurface go\b", r"\bwacom\b", r"\bxp pen\b", r"\bhuion\b",
        r"\bkindle\b", r"\bkobo\b", r"\bremarkable\b",
    ],
}

# Signaux confirmant un état défectueux / à réparer
DEFECT_SIGNALS: list[str] = [
    r"\bhs\b",
    r"\bh s\b",
    r"\ben panne\b",
    r"\ba reparer\b",
    r"\bpour pieces\b",
    r"\bpieces detachees\b",
    r"\bdefectueux\b",
    r"\bdefectueuse\b",
    r"\bne s allume\b",
    r"\bs allume plus\b",
    r"\bne fonctionne plus\b",
    r"\bfonctionne mal\b",
    r"\bmarche plus\b",
    r"\bne charge plus\b",
    r"\bprobleme\b",
    r"\bsouci\b",
    r"\bpanne\b",
    r"\bdrift\b",
    r"\bclignote\b",
    r"\bsurchauffe\b",
    r"\bcode erreur\b",
    r"\berreur\b",
    r"\bcasse\b",
    r"\bfaux contact\b",
    r"\bport hdmi\b",
    r"\bport usb\b",
    r"\bconnecteur\b",
    r"\bbatterie hs\b",
    r"\bbatterie faible\b",
    r"\bventilo\b",
    r"\blecteur hs\b",
    r"\bne lit plus\b",
    r"\bpas d affichage\b",
    r"\becran noir\b",
    r"\bblod\b",
    r"\byold\b",
    r"\bsans image\b",
    r"\bplus de son\b",
    r"\bfuit\b",
    r"\bfuite\b",
    r"\bnon teste\b",
    r"\bvendu en l etat\b",
]


def _matches_any(text: str, patterns: list[str]) -> str | None:
    for pat in patterns:
        if re.search(pat, text):
            return pat
    return None


def evaluate_listing(raw: RawListing, settings: Settings) -> FilterResult:
    title_norm = normalize_text(raw.title)
    desc_norm = normalize_text(raw.description)
    full_text = f"{title_norm} {desc_norm}".strip()
    cond_norm = normalize_text(raw.condition_label)

    # 1. Prix
    if raw.price < settings.min_price_eur:
        return FilterResult(
            accepted=False,
            reject_reason=f"Prix trop bas ({raw.price:.0f}€ < {settings.min_price_eur:.0f}€)",
        )
    if raw.price > settings.max_price_eur:
        return FilterResult(
            accepted=False,
            reject_reason=f"Prix au-dessus du plafond ({raw.price:.0f}€ > {settings.max_price_eur:.0f}€)",
        )

    # 2. Livraison obligatoire si activée
    if settings.require_shipping and not raw.shipping_available:
        return FilterResult(
            accepted=False,
            reject_reason="Livraison indisponible (remise en main propre uniquement)",
        )

    # 3. Exclusions strictes
    for group_name, patterns in STRICT_EXCLUSION_GROUPS:
        if group_name in {"Alimentation / chargeur / câble", "Visserie / accessoires / boîtes vides"}:
            if _matches_any(title_norm, patterns):
                return FilterResult(accepted=False, reject_reason=f"Exclu : {group_name}")
        else:
            if _matches_any(full_text, patterns):
                return FilterResult(accepted=False, reject_reason=f"Exclu : {group_name}")

    # 4. Catégorie cible
    matched_category = "autre"
    best_hits = 0
    for cat, patterns in CATEGORY_KEYWORDS.items():
        hits = sum(2 for p in patterns if re.search(p, title_norm)) + sum(
            1 for p in patterns if re.search(p, desc_norm)
        )
        if hits > best_hits:
            best_hits = hits
            matched_category = cat

    if matched_category == "autre":
        return FilterResult(
            accepted=False,
            reject_reason="Hors catégories ciblées (consoles, info, outils, audio, photo, petit électro, tablettes)",
        )

    # 5. Vérifier qu'il s'agit bien d'un objet défectueux / pour pièces
    is_parts_condition = any(
        k in cond_norm for k in ["piece", "parts", "hs", "reparer", "panne", "not working"]
    )
    has_defect_signal = is_parts_condition or (_matches_any(full_text, DEFECT_SIGNALS) is not None)
    if not has_defect_signal:
        return FilterResult(
            accepted=False,
            category=matched_category,
            reject_reason="Aucun signal de panne/HS détecté",
        )

    # 6. Détection "Déjà ouvert / passé chez un pro"
    already_opened = False
    opened_reasons: list[str] = []
    for pat, label in ALREADY_OPENED_PATTERNS:
        if re.search(pat, full_text):
            already_opened = True
            if label not in opened_reasons:
                opened_reasons.append(label)

    opened_reason = ", ".join(opened_reasons)
    if already_opened and settings.exclude_already_opened:
        return FilterResult(
            accepted=False,
            category=matched_category,
            reject_reason=f"Exclu (déjà ouvert) : {opened_reason}",
            already_opened=True,
            opened_reason=opened_reason,
        )

    return FilterResult(
        accepted=True,
        category=matched_category,
        already_opened=already_opened,
        opened_reason=opened_reason,
    )

"""Part 7b: the categories (menus) of the app and the rules that sort a document into them.

Decided with the user on 2026-10-14 (analysis in notes/data_organisation.md):
- category = subject, decided by the Techniques de l'Ingénieur (TI) reference code when there is one
  (its letters are the TI collection: D = génie électrique, H = informatique...), otherwise by the
  folder name, otherwise by the title;
- subcategory = first keyword rule that matches the title + folder + file name, else "Général";
- source = "Techniques de l'Ingénieur" / "Livres" / "Divers": the app can show TI as its own menu;
- themes = cross-domain topics (THEMES below: welding, optics, sensors...), 0..n per document.
To change where one document goes, edit data/catalog_overrides.csv instead of this file.
"""
import re
import unicodedata

GENERAL = "Général"

# key: (label, [(subcategory, [keywords])...]). Keywords match the START of a word in the
# normalised text (lowercase, no accents): "asservi" matches "asservissement". First match wins.
CATEGORIES = {
    "ELEC": ("Électrotechnique & énergie électrique", [
        ("Normes, CEM & sécurité électrique", ["normalisation", "certification", "conformite", "compatibilite", "blindage", "feu", "essais",
            "explosib", "essais d environnement", "organisation"]),
        ("Électronique de puissance & convertisseurs", ["convertiss", "onduleur", "redress", "hacheur", "alimentation a decoupage",
            "alimentations a decoupage", "electronique de puissance", "electonique de puissance", "thyristor", "igbt", "gradateur",
            "regulateurs statiques", "semi conducteur", "composants actifs", "composants passifs", "outils d analyse"]),
        ("Machines électriques & commande", ["machine", "moteur", "alternateur", "turboaltern", "micromoteur", "asynchrone", "synchrone", "actionneur",
            "variateur", "atv", "entrainement", "pas a pas", "commande", "transformateur", "vectoriel", "mmc", "fuite"]),
        ("Réseaux & installations électriques", ["reseau", "installation", "distribution", "protection", "cable", "poste",
            "tarification", "schema", "neutre", "harmonique", "appareillage", "disjoncteur", "eclairage", "centrale",
            "surtension", "conducteur", "energie reactive", "controle commande", "surete", "stabilite", "recepteur", "source",
            "giude de conception", "guide de la mes"]),
        ("Stockage & usages de l'électricité", ["accumulateur", "batterie", "pile", "plasma", "electrotherm", "chauffage",
            "induction", "four!", "fours!", "microgenerat", "micropile", "microbatter", "consom", "ressources energ",
            "supercondensateur"]),
        ("Électrotechnique générale", ["electrotechni", "electricite", "notions de base", "generalite", "materiaux",
            "magnet", "electromagnet", "dielectri", "isolant", "supraconduct", "arc electrique", "champ electrique", "grandeurs",
            "mesure", "cao!", "optique", "mathemat", "unites", "bobine"]),
    ]),
    "ELN": ("Électronique & télécoms", [
        ("Électronique de puissance & énergie embarquée", ["hacheur", "redresseur", "onduleur", "motorisation", "vehicule",
            "accumulateur", "chargeur", "batterie", "alimentation"]),
        ("Conception, fiabilité & normes", ["dissipation", "contraintes climatiques", "protection", "vibrations", "chocs",
            "normalisation", "organismes", "symboles", "documentation", "interconnexion", "fiabilit", "puce", "reutilisation",
            "conception electronique", "assemblage", "aspects industriels", "conception de cartes"]),
        ("Optoélectronique & optronique", ["opto", "optron", "laser", "fibre", "photo", "affich", "ecran", "cristal liquide", "led!",
            "infrarouge", "ultraviolet", "intensificateur", "lidar", "optique", "camera", "vision", "oeil", "terres rares",
            "reflexion", "refraction", "veille et alerte", "acousto optique"]),
        ("Hyperfréquences, antennes & électromagnétisme", ["hyperfrequence", "antenne", "micro onde", "mmic", "guide d onde",
            "electromagnet", "propagation", "radar", "circuits passif"]),
        ("Signal, image & télécoms", ["signal", "signaux", "image", "telecom", "transmission", "modulation", "radio", "audiovisuel",
            "video", "son!", "codage", "multimedia", "television", "enregistrement", "restitution", "transduction", "emission",
            "emetteur", "frequence", "compression", "impression", "fm!"]),
        ("Électronique numérique", ["numerique", "logique", "microprocesseur", "memoire", "programmable", "fpga", "asic"]),
        ("Composants & circuits", ["composant", "transistor", "diode", "amplificat", "circuit", "semi", "silicium",
            "condensateur", "resistance", "carte", "connecti", "integre", "oscillat", "filtre", "bruit", "dielectri", "magnet",
            "conduct", "materiaux", "impulsion", "puissance", "technolog", "capteur", "ferrite", "ferromagn", "ferroelectr",
            "varistance", "inductance", "transformateur", "supraconduct", "microsysteme", "acousto", "ultrason", "dispositif",
            "polymer"]),
    ]),
    "INFO": ("Informatique", [
        ("Réseaux, protocoles & sécurité", ["reseau", "protocole", "internet", "tcp", "communication", "securite", "message",
            "routage", "atm!", "ethernet", "web", "applications et services", "messagerie", "client serveur", "crypto"]),
        ("Systèmes d'exploitation", ["systeme d exploitation", "systemes d exploitation", "systme", "unix", "windows", "noyau"]),
        ("Architecture & matériel", ["processeur", "microprocesseur", "memoire", "stockage", "peripherique", "architecture",
            "performance", "disponibilite", "serveur", "bus", "parallel", "disque", "machine", "ordinateur"]),
        ("Données, documents & images", ["donnees", "base", "document", "multimedia", "acquisition", "restitution",
            "information", "sgbd", "image", "format", "svg", "xml"]),
        ("Logiciel & programmation", ["langage", "programm", "logiciel", "objet", "compil", "ada", "java", "algorithm", "specification",
            "genie logiciel", "test", "conception", "cobol", "fortran", "pascal", "lisp", "prolog"]),
    ]),
    "AUTO": ("Automatique, robotique & informatique industrielle", [
        ("Robotique", ["robot"]),
        ("Automates, réseaux de Petri & productique", ["automate", "grafcet", "automatisme", "sequenti", "api!", "petri",
            "automatisation", "atelier", "flexible", "evenements discrets"]),
        ("Informatique temps réel & industrielle", ["temps reel", "calculateur", "informatique industriel", "bus", "can!",
            "supervision", "reseaux locaux", "ordinateur", "algorithmique", "logiciel", "numerique", "programmation",
            "peripherique", "reactif", "langage", "communication", "a120"]),
        ("Asservissements & régulation", ["asservi", "regula", "pid", "commande", "stabilite", "lineaire", "automatique",
            "laplace", "rappels mathematiques", "identification", "systeme", "observateur", "optimal", "flou", "transformation",
            "correction", "frequentiel", "intelligence artificielle", "fusion",
            "optimis", "aleatoire", "multiagent"]),
    ]),
    "MES": ("Mesures, métrologie & contrôle", [
        ("Contrôle non destructif", ["non destructif", "ultrason", "radiograph", "ressuage", "foucault", "magnetoscop", "cnd"]),
        ("Acoustique & vibrations", ["acousti", "accousti", "vibrat", "bruit"]),
        ("Thermiques", ["temperature", "thermom", "thermocouple", "thermoelectri", "pyrometr", "thermique", "chaleur", "calorim", "thermophys",
            "humidit", "hygrom"]),
        ("Débit, pression & niveau", ["debit", "pression", "niveau", "fluide", "anemom", "volume", "compteur", "detection de gaz",
            "vide!", "hydraulique", "pneumatique", "vitesse"]),
        ("Optique & rayonnements", ["optique", "photometr", "radiometr", "interfer", "laser", "lumiere", "rayonnement", "couleur",
            "colorim", "spectr", "imagerie"]),
        ("Électriques & instrumentation", ["electrique", "tension", "courant", "puissance", "impedance", "oscillo", "instrumentation",
            "radiofrequence", "enregistr", "frequence", "capteur", "multimetre", "analyseur"]),
        ("Dimensionnelles & mécaniques", ["dimension", "longueur", "rugosit", "etat de surface", "forme", "angle", "force",
            "couple", "deformation", "extenso", "masse", "pesage", "contrainte", "acceler", "deplacement", "mecanique",
            "tridimensionnel", "coordonnees", "jauge", "position"]),
        ("Méthodes, statistiques & traitement du signal", ["statisti", "incertitude", "etalon", "reference", "organisation",
            "terminolog", "metrologie", "traitement du signal", "filtrage", "numerique", "transmission", "stockage",
            "visualisation", "temps", "mesure", "depouillement", "conditions particulieres"]),
    ]),
    "MECA": ("Génie mécanique & calcul", [
        ("Tuyauterie, réservoirs & appareils à pression", ["tuyaut", "reservoir", "robinet", "supportage", "appareils a pression",
            "enceintes sous pression", "chaudronn", "canalisation", "compensateurs", "fluide hydraulique", "fluides hydrauliques",
            "appareillages de controle des fluides", "pression"]),
        ("Conception & CAO", ["conception", "cao!", "cfao", "dao!", "dessin", "cotation", "tolerance", "design", "bureau d etudes",
            "courbes et surfaces", "modelisation geometrique", "maquette", "prototyp", "ingenierie", "cetim"]),
        ("RDM & calcul de structures", ["resistance des materiaux", "resistances des materiaux", "resistance de materiaux", "rdm",
            "calcul de structure", "calcul des structures", "elements finis", "poutre", "plaque", "coque", "flambement", "elasticit",
            "structure", "timoshenko", "mecanique appliquee", "contrainte", "deformation"]),
        ("Rupture, fatigue & milieux continus", ["rupture", "fatigue", "endommag", "milieux continus", "plasticit", "fissur",
            "mecanique continu", "fluage", "comportement", "thermomecan"]),
        ("Éléments de machines & transmissions", ["engrenage", "engrenges", "roulement", "palier", "etancheit", "joint", "guidage",
            "vis!", "boulon", "assemblage", "ressort", "accouplement", "embrayage", "frein", "courroie", "chaine", "transmission",
            "arbre", "came!", "cames!", "reducteur", "immobilisation", "clavet", "lubrifi", "tribolog", "frottement", "usure", "cons machines",
            "technologie mecanique", "construction mecanique", "construction industrielle", "elements de machines", "piece",
            "variateur", "butee", "cardan", "ecrou", "goupille", "rivet"]),
        ("Mécanique générale & vibrations", ["mecanique generale", "dynamique", "cinemat", "vibration", "gyroscop", "rotor",
            "mecanique du solide", "statique", "choc", "equilibrage", "balourd", "acoust"]),
        ("Formulaires & aide-mémoire", ["formulaire", "aide memoire", "memotech", "guide de mecanique", "guide du calcul"]),
    ]),
    "ENER": ("Énergétique, fluides & machines thermiques", [
        ("Technique du vide", ["vide!"]),
        ("Moteurs thermiques", ["moteur", "diesel", "essence", "combustion", "suralimentation", "transvasement", "turbocompress",
            "allumage", "carburat"]),
        ("Pompes, turbines & compresseurs", ["pompe", "turbine", "compresseur", "ventilat", "turbomachine", "eolien", "volumetrique",
            "machines hydrauliques", "soufflante", "aube", "cavitation"]),
        ("Thermique, froid & climatisation", ["thermique", "froid", "frigori", "chaleur", "echangeur", "climatis", "chauffage",
            "habitat", "isolation", "refriger", "combustible", "chaudiere", "vapeur", "cycle", "thermodynam"]),
        ("Hydraulique & mécanique des fluides", ["hydraul", "fluide", "ecoulement", "oleohydraul", "hydrolog", "tuyaut", "vanne",
            "robinet", "canalisation", "jet", "aerodynam"]),
        ("Pollution & énergie", ["pollution", "emission", "energie", "nucleaire", "solaire", "atmospher"]),
    ]),
    "FAB": ("Fabrication : usinage, soudage, fonderie, formage", [
        ("Soudage & assemblage", ["soud", "brasage", "collage", "assemblage", "rivet", "sertissage"]),
        ("Fonderie & moulage", ["fonderie", "moulage", "coulee", "moule", "noyau", "sable", "cire perdue"]),
        ("Usinage & machines-outils", ["usinage", "tournage", "tour", "fraisage", "fraiseuse", "percage", "pecage", "rectif",
            "machine outil", "outil", "coupe", "ajustage", "electroerosion", "decoupage", "taillage", "alesage", "commande numerique"]),
        ("Formage & travail des métaux", ["forg", "lamin", "emboutiss", "tole", "feuille", "mise en forme", "extrusion", "filage",
            "trefil", "pliage", "fritt", "poudre", "plasticit", "lubrification", "estampage", "matricage", "formage", "cintrage"]),
        ("Méthodes, gammes & productique", ["gamme", "analyse de fabrication", "productique", "methode", "ofppt", "analyse de produits",
            "fabrication"]),
    ]),
    "METAL": ("Matériaux métalliques & traitements", [
        ("Traitements de surface & revêtements", ["surface", "revetement", "depot", "decapage", "electrolyt", "galvan", "peinture",
            "metallisation", "immersion", "pvd", "cvd", "chromage", "nickelage", "zingage", "anodis", "phosphat", "email",
            "protection et deco", "projection thermique"]),
        ("Corrosion & protection", ["corrosion", "protection cathodique", "oxydation"]),
        ("Traitements thermiques", ["trempe", "revenu", "recuit", "traitement thermique", "traitements thermiques", "cementation",
            "nitrur", "carbonitrur", "durcissement", "four", "austenit", "thermochimique"]),
        ("Essais & caractérisation", ["essai", "durete", "analyse", "dosage", "inclusion", "caracteris", "metallograph",
            "microscop", "diffraction"]),
        ("Métallurgie & propriétés", ["propriet", "acier", "fonte", "alliage", "alumin", "cuivre", "titane", "nickel", "magnesium",
            "zinc", "plomb", "etain", "metal", "etat metallique", "diagramme", "metallurg", "materiau", "solidification",
            "diffusion", "dislocation", "transformation"]),
    ]),
    "PLAST": ("Plastiques & composites", [
        ("Soudage & assemblage des plastiques", ["soud", "collage", "assemblage"]),
        ("Composites", ["composite", "fibre", "renfort", "stratifi", "sandwich", "preimpregn"]),
        ("Plasturgie : injection, extrusion, mise en œuvre", ["injection", "extrusion", "extrud", "moulage", "thermoform",
            "soufflage", "calandr", "mise en oeuvre", "finition", "conception des pieces", "recyclage", "rotomoulage", "moule",
            "plasturgie", "procede", "usinage", "peinture", "decoration", "metallisation", "reglementation alimentaire"]),
        ("Chimie, propriétés & essais", ["chimi", "propriet", "essai", "analyse", "adjuvant", "adjuvent", "vieilliss", "rheolog",
            "physico", "stabilis", "charge", "plastifiant", "polymeris", "comportement", "calcul"]),
        ("Matières plastiques", ["poly", "pvc", "epoxy", "matieres", "thermoplasti", "thermodurciss", "monographie", "elastomere",
            "caoutchouc", "silicone", "fluor", "resine", "semi produit", "plastique", "abs!", "pmma", "pet!"]),
    ]),
    "PROC": ("Génie des procédés, chimie & environnement", [
        ("Environnement, risques & déchets", ["depollution", "dechet", "effluent", "eaux", "boue", "pollution", "cov",
            "environnement", "ecoconception", "eco conception", "ecologique", "iso 14001", "hcl", "rejet", "traitement des gaz",
            "atmospher", "odeur", "recyclage", "risque", "explosion", "securit"]),
        ("Analyse & spectrométrie", ["spectro", "spectrom", "analyse", "chromatograph", "plans d experiences", "absorption",
            "fluorescence", "masse", "microscop"]),
        ("Bases : modélisation, transferts, formulation", ["modelis", "transfert", "formulation", "generalite", "thermodynam",
            "cinetique", "reacteur", "catalys"]),
        ("Agroalimentaire", ["agroalimentaire", "alimentaire", "aliment"]),
        ("Opérations unitaires", ["separation", "filtration", "broyage", "criblage", "flottation", "agitation", "melange",
            "evaporation", "sechage", "distillation", "membrane", "cristallis", "tri!", "solide", "classification", "decantation",
            "centrifug", "extraction", "absorption", "adsorption", "granul", "fragmentation", "dimension"]),
    ]),
    "CIVIL": ("Génie civil & construction", [
        ("Ports, littoral & ouvrages", ["port!", "ports!", "littoral", "maritime", "ouvrage", "pont", "route", "barrage", "digue", "quai"]),
        ("Chantier, matériel & marchés", ["chantier", "echafaud", "marche", "contrat", "assurance", "controle technique", "materiel",
            "organisation", "electricite de chantier", "engin", "grue", "coffrage", "outillage", "modelisation"]),
        ("Matériaux de construction", ["beton", "ciment", "bois", "colle", "adhesif", "ceramique", "terre cuite", "materiau", "verre",
            "platre", "pierre", "granulat", "mortier", "brique", "acier"]),
        ("Bâtiment & données techniques", ["batiment", "donnees", "parasism", "eurocode", "thermique", "acoustique", "structure",
            "construction", "toiture", "facade"]),
    ]),
    "ENT": ("Entreprise industrielle : gestion, qualité, maintenance, logistique", [
        ("Maintenance & sûreté de fonctionnement", ["maintenance", "amdec", "tpm", "fiabilit", "surete de fonctionnement",
            "disponibilit", "defaillance", "diagnostic", "dunud"]),
        ("Sécurité & prévention des risques", ["securit", "risque", "prevention", "hygiene", "accident", "ergonom"]),
        ("Manutention & emballage", ["manutention", "levage", "chariot", "convoy", "palett", "emballage", "embalage", "conditionnement",
            "grue", "pont roulant", "transstock", "stockeur", "etiquet"]),
        ("Logistique, stocks & transport", ["logisti", "stock", "approvisionnement", "entrepot", "magasin", "flux", "transport",
            "supply", "distribution", "achat"]),
        ("Qualité & normes", ["qualite", "iso", "norme", "certification", "amelioration continue", "5s", "six sigma", "msp", "maitrise statistique",
            "plans d experiences", "audit", "excellence"]),
        ("Conception & innovation produit", ["conception", "analyse de la valeur", "analyse fonctionnelle", "design", "cahier des charges",
            "produit", "innovation", "veille", "brevet", "propriete industrielle", "creativite", "marketing", "marche"]),
        ("Management & gestion de projet", ["management", "managerment", "projet", "strateg", "entreprise", "organisation",
            "decision", "ressources humaines", "financ", "cout", "comptab", "agile", "culture", "competence", "formation"]),
        ("Production & méthodes", ["production", "ordonnanc", "mrp", "industrialisation", "methode", "gestion industrielle",
            "juste a temps", "kanban", "lean", "performance", "systemes complexes", "atelier", "pilotage", "planification",
            "outils", "productivite", "temps", "simulation", "gestion"]),
    ]),
    "SCI": ("Sciences fondamentales, physique & optique", [
        ("Optique & lasers", ["optique", "laser", "lumiere", "photon", "holograph", "interfer", "diffraction", "polarisation"]),
        ("Mathématiques & calcul numérique", ["mathemat", "statisti", "probabil", "analyse", "matlab", "maple", "equation",
            "calcul", "transformation", "algebre", "integra", "series", "fonction", "courbes", "geometr", "tensor", "tenseur", "matric",
            "optimisation", "graphe", "topolog", "harmonique", "polynom", "racine", "quaternion", "nombre", "fraction",
            "methode numerique", "elements finis", "differentiel", "derivees partielles", "logique floue", "modele", "modelisation",
            "stochasti", "automatique"]),
        ("Mécanique & acoustique fondamentales", ["mecanique", "acousti", "vibration", "gyroscop", "relativ", "aeroacoust",
            "elasticit", "ecoulement", "cinemati", "dynamique"]),
        ("Physique & thermodynamique", ["physique", "thermodynam", "quantique", "matiere", "etat", "structure", "transport",
            "interface", "electromagnet", "atome", "nucle", "solide", "cristal", "cristaux", "surface", "plasma", "rayonnement",
            "unite", "polyelectroni", "molecule"]),
    ]),
    "DIVERS": ("Divers", [
        ("CV & lettre de motivation", ["cv!", "lettre", "entretien", "embauche"]),
        ("Plans & dessins techniques", ["headrest", "asm", "l0152235"]),
    ]),
}

SOURCE_TI, SOURCE_BOOKS, SOURCE_MISC = "Techniques de l'Ingénieur", "Livres", "Divers"


def norm(text: str) -> str:
    """lowercase, no accents (also the broken 'é' of some folder names), only letters/digits/spaces."""
    text = unicodedata.normalize("NFKD", text.replace("‚", "e")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def _pattern(keyword: str) -> str:
    """'asservi' matches the start of a word ('asservissement'); 'cao!' only the whole word (not 'caoutchouc')."""
    if keyword.endswith("!"):
        return r"\b" + re.escape(keyword[:-1]) + r"\b"
    return r"\b" + re.escape(keyword)


def _has(text: str, keywords: list[str]) -> bool:
    return any(re.search(_pattern(k), text) for k in keywords)


def code_category(code: str | None) -> str | None:
    """TI reference code -> category. Letters = TI collection; for old codes the number range matters."""
    m = re.fullmatch(r"([A-Z]+)(\d+)", code or "")
    if not m:
        return None
    p, n = m.group(1), m.group(2)
    d, size = n[0], len(n)
    if p == "AF": return "SCI"
    if p == "D": return "ELEC"
    if p in ("E", "TE"): return "ELN"
    if p == "H": return "INFO"
    if p == "S": return "AUTO"
    if p == "R": return "AUTO" if size == 4 and d in "78" else "MES"
    if p == "M":
        if size == 4 and n[:2] in ("14", "15", "16"): return "METAL"   # traitements de surface
        if (size == 4 and d == "3") or (size == 3 and d in "678"): return "FAB"   # fonderie, mise en forme
        return "METAL"
    if p == "AM": return "PLAST"
    if p in ("AG", "T"): return "ENT"
    if p in ("J", "F", "G", "GR", "P", "PE"): return "PROC"
    if p == "C": return "CIVIL"
    if p == "BE": return "ENER"
    if p in ("B", "BM"):
        if size == 4 and n[:3] == "601": return "ENER"                      # fluides hydrauliques
        if size == 4 and d in "24": return "ENER"
        if size == 4 and d == "7": return "FAB"
        if size == 4 and d == "3": return "ENT"
        if size == 3 and d == "2": return "ENER"
        return "MECA"
    if p == "A":   # old codes: the number range gives the subject (checked on the titles, 2026-10-14)
        num = int(n)
        if size == 4:
            if 1000 <= num < 1080: return "ENT"                              # A10xx emballage (A1080+ = optique)
            if d == "5": return "ENT"           # conception, créativité... except séparation/broyage: see title_category
            return {"1": "SCI", "2": "PLAST", "3": "PLAST", "4": "ENT", "7": "PLAST", "8": "ENT", "9": "ENT"}.get(d)
        if size == 3:
            if d == "7": return "MECA" if num >= 750 else "ENER"            # tuyauteries / écoulements
            return {"1": "SCI", "2": "SCI", "3": "MECA", "4": "MECA", "5": "SCI", "6": "SCI", "8": "MECA"}.get(d)
        return "SCI"
    return None  # standards (ISO, EN, CEI...) and unknown letters



# old A5xxx codes mix company topics and process engineering (centrifugation, fragmentation...)
A5_PROCESS_KEYWORDS = ["centrifug", "fragmentation", "classification", "concentration", "separation", "broyage", "criblage",
                       "flottation", "tri!", "filtration", "decantation"]


def title_category(cat: str | None, title: str, code: str = "") -> str | None:
    text = norm(title)
    if re.fullmatch(r"A5\d{3}", code or "") and _has(text, A5_PROCESS_KEYWORDS):
        return "PROC"
    return cat


# Folders whose documents all belong to one subcategory (checked before the keywords)
FOLDER_SUBCATEGORY = {"giude de conception": "Réseaux & installations électriques"}


def folder_subcategory(folder_parts: list[str]) -> str | None:
    for part in map(norm, folder_parts):
        for key, sub in FOLDER_SUBCATEGORY.items():
            if key in part:
                return sub
    return None


# Folder (or title) words -> category, for documents without a usable TI code. Checked from the deepest
# folder up, so "...\mesures et controles\debits" is found as MES by "debits" before anything else.
FOLDER_RULES = [
    ("cv lettre", "DIVERS"), ("headrest", "DIVERS"),
    ("informatique industrielle", "AUTO"), ("automat", "AUTO"), ("robot", "AUTO"), ("temps reel", "AUTO"), ("asservi", "AUTO"),
    ("regulation", "AUTO"),
    ("mesure", "MES"), ("metrologie", "MES"), ("controle non destructif", "MES"), ("accousti", "MES"), ("debits", "MES"),
    ("thermometrie", "MES"),
    ("genie electrique", "ELEC"), ("machines electriques", "ELEC"), ("convertisseurs", "ELEC"), ("electrotechni", "ELEC"),
    ("installation electrique", "ELEC"), ("giude de conception", "ELEC"), ("plasma", "ELEC"), ("electronique de puissance", "ELEC"),
    ("accumulateurs", "ELEC"), ("electricite", "ELEC"),
    ("electroni", "ELN"), ("eletroni", "ELN"), ("electromagnetisme", "ELN"), ("telecom", "ELN"), ("radiocommunication", "ELN"),
    ("audiovisuel", "ELN"), ("traitement du signal", "ELN"), ("traitement de l image", "ELN"),
    ("informatique", "INFO"), ("logiciel", "INFO"), ("reseaux", "INFO"), ("programmation", "INFO"), ("documents numeriques", "INFO"),
    ("spectrometrie", "PROC"),
    ("optique", "SCI"), ("laser", "SCI"),
    ("plasti", "PLAST"), ("platiques", "PLAST"), ("composites", "PLAST"), ("plasturgie", "PLAST"), ("plastochimie", "PLAST"),
    ("traitements de surface", "METAL"), ("peinture", "METAL"), ("traitements thermiques", "METAL"), ("metaux", "METAL"),
    ("traitements des materiaux", "METAL"), ("generalites materiaux", "METAL"),
    ("fonderie", "FAB"), ("mise en forme", "FAB"), ("usinage", "FAB"), ("soudage", "FAB"), ("soudees", "FAB"), ("assemblage", "FAB"),
    ("fabrication", "FAB"), ("travail de metaux", "FAB"), ("extrusion", "FAB"),
    ("genie civil", "CIVIL"), ("construction", "CIVIL"), ("batiment", "CIVIL"),
    ("hydro", "ENER"), ("moteurs", "ENER"), ("energ", "ENER"), ("thermique de l habitat", "ENER"), ("froid", "ENER"),
    ("hydraulique", "ENER"), ("technique du vide", "ENER"), ("pollution atmospherique", "ENER"), ("meca flotte", "ENER"),
    ("machines", "ENER"),
    ("genie des procedes", "PROC"), ("agroalimentaire", "PROC"), ("traitement hcl", "PROC"), ("dechets", "PROC"),
    ("entreprise", "ENT"), ("management", "ENT"), ("managerment", "ENT"), ("qualite", "ENT"), ("maintenance", "ENT"),
    ("logistique", "ENT"), ("manutention", "ENT"), ("gestion", "ENT"), ("conception", "ENT"), ("securit", "ENT"),
    ("tpm", "ENT"), ("outils de performances", "ENT"), ("transport", "ENT"), ("emballage", "ENT"), ("methode", "ENT"),
    ("selection b4", "ENT"),
    ("science", "SCI"), ("physique", "SCI"), ("matlab", "SCI"), ("mathemat", "SCI"), ("nombre", "SCI"), ("fraction", "SCI"),
    ("polynom", "SCI"),
    ("materiaux", "METAL"),
    ("piece", "MECA"), ("mecanique", "MECA"), ("rdm", "MECA"), ("formulaire", "MECA"), ("be!", "MECA"),
]


def folder_category(folder_parts: list[str]) -> str | None:
    for part in reversed([norm(p) for p in folder_parts]):
        for keyword, cat in FOLDER_RULES:
            if re.search(_pattern(keyword), part):
                return cat
    return None


# Cross-domain THEMES (user, 2026-10-14): a document keeps its category and can also have 0..n themes,
# so the app can search e.g. everything about welding, whatever the category (Fabrication, Plastiques,
# Génie civil...). A document gets a theme if its title has one of the keywords, or if its subcategory
# is listed for that theme.
THEMES = {
    "Soudage & assemblage": (
        ["soud", "brasage", "collage", "colle!", "colles!", "adhesif", "assemblage", "rivet", "sertissage"],
        ["Soudage & assemblage", "Soudage & assemblage des plastiques"]),
    "Optique & lasers": (
        ["optique", "laser", "photon", "opto", "optron", "holograph", "interferom", "photometr", "lumiere", "infrarouge",
         "ultraviolet", "lidar"],
        ["Optique & rayonnements", "Optoélectronique & optronique", "Optique & lasers"]),
    "Capteurs": (
        ["capteur", "detecteur", "jauge", "transducteur", "thermocouple", "sonde!", "sondes!"], []),
    "Maintenance & fiabilité": (
        ["maintenance", "maintenabilit", "fiabilit", "surete de fonctionnement", "amdec", "tpm!", "defaillance", "diagnostic",
         "surveillance vibratoire", "maintenance predictive"],
        ["Maintenance & sûreté de fonctionnement"]),
    "Sécurité & risques": (
        ["securit", "risque", "explosion", "explosib", "incendie", "feu!", "hygiene", "prevention", "accident"],
        ["Sécurité & prévention des risques"]),
    "Normes & réglementation": (
        ["norme", "normes!", "normalis", "reglementation", "certification", "conformite", "iso!", "eurocode"],
        ["Normes, CEM & sécurité électrique", "Qualité & normes"]),
    "Vibrations & acoustique": (
        ["vibrat", "acoust", "accoust", "bruit", "sonoris", "ultrason"],
        ["Acoustique & vibrations", "Mécanique générale & vibrations"]),
    "Électronique de puissance": (
        ["convertiss", "onduleur", "hacheur", "redresseur", "electronique de puissance", "electonique de puissance",
         "alimentation a decoupage", "alimentations a decoupage", "thyristor", "igbt", "gradateur", "semi conducteurs de puissance",
         "variateur"],
        ["Électronique de puissance & convertisseurs", "Électronique de puissance & énergie embarquée"]),
    "Traitement du signal & image": (
        ["signal", "signaux", "filtrage", "filtre numerique", "filtres numeriques", "image", "compression", "analyse spectrale",
         "fourier"], []),
    "CAO & simulation": (
        ["cao!", "cfao", "dao!", "conception assistee", "prototypage rapide", "cotation fonctionnelle", "courbes et surfaces",
         "simulation", "modelisation geometrique", "modelisation numerique", "elements finis", "maquette numerique"],
        ["Conception & CAO"]),
    "Essais & contrôle non destructif": (
        ["essai", "non destructif", "cnd!", "ultrason", "radiograph", "ressuage", "magnetoscop", "courants de foucault"],
        ["Contrôle non destructif", "Essais & caractérisation"]),
}


def themes(title: str, sub: str) -> list[str]:
    text = norm(title)
    return [t for t, (keywords, subs) in THEMES.items() if sub in subs or _has(text, keywords)]


def theme_key(theme: str) -> str:
    """Name of the yes/no field of a theme in the database: 'Capteurs' -> 'theme_capteurs'."""
    return "theme_" + norm(theme).replace(" ", "_")


def subcategory(cat: str, text: str) -> str:
    """text = normalised title + folder + file name."""
    text = text.replace("aide memoire", "")   # a book type, not the "mémoire" (memory chip) topic
    for sub, keywords in CATEGORIES[cat][1]:
        if _has(text, keywords):
            return sub
    return GENERAL

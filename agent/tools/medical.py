"""Medical and Medicine Information Search Tool.

Provides accurate, clinical, and structured information regarding medications,
including generic names, brand names, therapeutic uses, dosage guidelines,
side effects, drug precautions, and key interactions.
Integrates curated clinical knowledge, OpenFDA official drug labels,
and real-time medical web search.
"""

import json
import logging
import re
import urllib.parse
import urllib.request
from typing import Any, Dict, Optional

logger = logging.getLogger("ai_assistant.medical")

# Standard medical safety disclaimer for responsible clinical communication
MEDICAL_DISCLAIMER = (
    "Disclaimer: This information is for educational purposes only. Always consult a qualified "
    "doctor, physician, or pharmacist before taking, changing, or stopping any medication."
)

# Curated high-confidence clinical database for common medications & popular brands
CURATED_MEDICINE_DB: Dict[str, Dict[str, Any]] = {
    "paracetamol": {
        "generic_name": "Paracetamol (Acetaminophen)",
        "drug_class": "Analgesic and Antipyretic",
        "brand_names": ["Dolo 650", "Crocin", "Calpol", "Tylenol", "Panadol", "Pacimol"],
        "uses": "Relief of mild to moderate pain (headaches, body aches, toothaches, joint pain) and reduction of high fever.",
        "dosage_guidelines": "Standard adult dose is 500 mg to 650 mg every 4 to 6 hours as needed. Do not exceed 4,000 mg (4 grams) in 24 hours to prevent severe liver damage.",
        "side_effects": "Generally well-tolerated. Rare side effects include skin rash, nausea, and liver toxicity if taken in overdose.",
        "precautions": "Avoid heavy alcohol consumption while taking paracetamol. Consult a doctor if you have pre-existing liver or kidney conditions.",
        "interactions": "Be cautious when combining with warfarin (blood thinners) or other medications that contain acetaminophen to avoid accidental overdose.",
    },
    "dolo 650": {
        "generic_name": "Paracetamol 650 mg",
        "drug_class": "Analgesic and Antipyretic",
        "brand_names": ["Dolo 650", "Crocin 650", "Calpol 650"],
        "uses": "Commonly prescribed for fever reduction, viral infections, body ache, fever with chills, and moderate pain relief.",
        "dosage_guidelines": "1 tablet (650 mg) orally after meals every 6 to 8 hours as needed. Maintain at least a 4-hour gap between doses. Do not exceed 4 tablets in 24 hours.",
        "side_effects": "Mild nausea, sweating. High doses over prolonged periods can cause acute liver injury.",
        "precautions": "Take after meals with water. Do not combine with other fever medications that already contain paracetamol.",
        "interactions": "Avoid alcohol. Check with a doctor if taking anti-epileptic drugs or blood thinners.",
    },
    "ibuprofen": {
        "generic_name": "Ibuprofen",
        "drug_class": "Non-Steroidal Anti-Inflammatory Drug (NSAID)",
        "brand_names": ["Brufen", "Advil", "Motrin", "Combiflam (with Paracetamol)", "Ibugesic"],
        "uses": "Relief of inflammatory pain, arthritis, dental pain, muscle aches, back pain, menstrual cramps, and swelling.",
        "dosage_guidelines": "Typical adult dose is 200 mg to 400 mg every 4 to 6 hours with food. Maximum OTC dose is 1,200 mg per day unless directed by a physician.",
        "side_effects": "Stomach upset, heartburn, nausea, dizziness. Long-term use may cause gastric ulcers or increase cardiovascular risk.",
        "precautions": "Always take with food or milk to protect stomach lining. Avoid if you have active stomach ulcers, severe kidney disease, or asthma.",
        "interactions": "Do not take concurrently with aspirin, other NSAIDs, or oral anticoagulants without medical supervision.",
    },
    "aspirin": {
        "generic_name": "Acetylsalicylic Acid (Aspirin)",
        "drug_class": "Antiplatelet, NSAID, and Analgesic",
        "brand_names": ["Disprin", "Ecosprin", "Bayer Aspirin", "Loprin"],
        "uses": "Low dose (75 mg - 150 mg) is used to prevent heart attacks and strokes. Higher doses relieve pain, inflammation, and fever.",
        "dosage_guidelines": "For cardiovascular protection: 75 mg to 100 mg once daily. For acute pain: 300 mg to 600 mg every 4 to 6 hours with food.",
        "side_effects": "Gastric irritation, increased bleeding tendency, indigestion.",
        "precautions": "Never give aspirin to children or teenagers recovering from viral infections due to the risk of Reye's syndrome. Contraindicated in bleeding disorders.",
        "interactions": "Interacts with blood thinners like heparin and warfarin, as well as NSAIDs like ibuprofen.",
    },
    "amoxicillin": {
        "generic_name": "Amoxicillin",
        "drug_class": "Penicillin-class Broad-Spectrum Antibiotic",
        "brand_names": ["Augmentin (with Clavulanate)", "Amoxil", "Mox", "Novamox"],
        "uses": "Treatment of bacterial infections including respiratory tract infections, ear infections, strep throat, skin infections, and urinary tract infections.",
        "dosage_guidelines": "Adult dose ranges from 250 mg to 500 mg every 8 hours, or 500 mg to 875 mg every 12 hours, typically for 5 to 10 days as prescribed.",
        "side_effects": "Diarrhea, mild stomach upset, nausea, skin rash.",
        "precautions": "Contraindicated in individuals with severe penicillin allergy. Always complete the entire prescribed course even if symptoms improve.",
        "interactions": "Can interact with methotrexate and reduce the efficacy of certain oral contraceptives.",
    },
    "azithromycin": {
        "generic_name": "Azithromycin",
        "drug_class": "Macrolide Antibiotic",
        "brand_names": ["Azee", "Azithral", "Zithromax", "Z-Pack"],
        "uses": "Bacterial respiratory infections, bronchitis, pneumonia, sinusitis, tonsillitis, and certain skin infections.",
        "dosage_guidelines": "Commonly 500 mg once daily for 3 days, or 500 mg on day 1 followed by 250 mg daily on days 2 to 5. Taken 1 hour before or 2 hours after meals.",
        "side_effects": "Nausea, vomiting, diarrhea, abdominal cramps, transient altered taste.",
        "precautions": "Use caution in patients with cardiac rhythm disorders (QT prolongation) or liver impairment. Not effective against viral colds or flu.",
        "interactions": "Antacids containing aluminum or magnesium may reduce absorption. Take at separate times.",
    },
    "metformin": {
        "generic_name": "Metformin Hydrochloride",
        "drug_class": "Biguanide Antidiabetic Agent",
        "brand_names": ["Glucophage", "Glycomet", "Fortamet", "Obimet"],
        "uses": "First-line oral medication for controlling blood glucose levels in Type 2 Diabetes Mellitus and managing polycystic ovary syndrome (PCOS).",
        "dosage_guidelines": "Initial adult dose is usually 500 mg once or twice daily with meals, gradually titrated up to 1,500 mg - 2,000 mg per day as prescribed by an endocrinologist.",
        "side_effects": "Gastrointestinal disturbances (diarrhea, bloating, nausea, metallic taste). These usually subside within a few weeks.",
        "precautions": "Take with meals to minimize stomach upset. Contraindicated in severe renal failure. Monitor kidney function and vitamin B12 levels regularly.",
        "interactions": "Avoid excessive alcohol due to heightened risk of lactic acidosis. Temporarily withhold before contrast dye imaging procedures.",
    },
    "omeprazole": {
        "generic_name": "Omeprazole",
        "drug_class": "Proton Pump Inhibitor (PPI)",
        "brand_names": ["Prilosec", "Omez", "Omecip", "Losec"],
        "uses": "Treatment of gastroesophageal reflux disease (GERD), acid peptic disease, heartburn, and stomach ulcers.",
        "dosage_guidelines": "Typically 20 mg once daily taken 30 to 60 minutes before breakfast with a glass of water.",
        "side_effects": "Headache, abdominal pain, diarrhea, constipation, flatulence.",
        "precautions": "Best taken on an empty stomach in the morning. Prolonged use over years should be monitored for bone density and magnesium levels.",
        "interactions": "May reduce absorption of medications dependent on gastric acidity (like iron supplements and ketoconazole).",
    },
    "pantoprazole": {
        "generic_name": "Pantoprazole",
        "drug_class": "Proton Pump Inhibitor (PPI)",
        "brand_names": ["Pan 40", "Pantocid", "Protonix", "Pan-D (with Domperidone)"],
        "uses": "Heartburn, acid reflux, erosive esophagitis, and gastritis. Often combined with domperidone to treat nausea with acidity.",
        "dosage_guidelines": "40 mg once daily orally in the morning, 30 minutes before breakfast.",
        "side_effects": "Dizziness, joint pain, diarrhea, nausea, headache.",
        "precautions": "Swallow whole; do not crush or chew delayed-release tablets. Inform doctor if symptoms persist past 2 weeks.",
        "interactions": "May lower efficacy of clopidogrel and protease inhibitors.",
    },
    "cetirizine": {
        "generic_name": "Cetirizine Hydrochloride",
        "drug_class": "Second-Generation Antihistamine",
        "brand_names": ["Zyrtec", "Cetzine", "Alerid", "Okacet"],
        "uses": "Relief of allergic rhinitis, hay fever, sneezing, runny nose, itchy watery eyes, hives, and allergic skin conditions.",
        "dosage_guidelines": "Adult dose is 10 mg once daily, preferably in the evening before bed.",
        "side_effects": "Mild drowsiness, dry mouth, tiredness, headache.",
        "precautions": "Although less sedating than first-generation antihistamines, it may cause drowsiness. Avoid driving or operating machinery until you know how it affects you.",
        "interactions": "Avoid consuming alcohol or other CNS depressants at the same time.",
    },
    "atorvastatin": {
        "generic_name": "Atorvastatin Calcium",
        "drug_class": "HMG-CoA Reductase Inhibitor (Statin)",
        "brand_names": ["Lipitor", "Atorva", "Storvas", "Atocor"],
        "uses": "Lowering low-density lipoprotein (LDL bad cholesterol) and triglycerides, and reducing the risk of stroke and cardiovascular disease.",
        "dosage_guidelines": "Starting dose is usually 10 mg to 20 mg once daily at bedtime, adjusted up to 40 mg - 80 mg under physician monitoring.",
        "side_effects": "Muscle ache (myalgia), mild digestive symptoms, joint pain.",
        "precautions": "Notify your doctor immediately if you experience unexplained muscle tenderness, weakness, or dark urine. Regular liver function monitoring recommended.",
        "interactions": "Avoid large quantities of grapefruit juice. Interactions with certain antibiotics (clarithromycin) and antifungals.",
    },
    "losartan": {
        "generic_name": "Losartan Potassium",
        "drug_class": "Angiotensin II Receptor Blocker (ARB)",
        "brand_names": ["Cozaar", "Losar", "Repace", "Covance"],
        "uses": "Management of high blood pressure (hypertension) and kidney protection in diabetic patients.",
        "dosage_guidelines": "Standard adult starting dose is 50 mg once daily, taken with or without food.",
        "side_effects": "Dizziness upon standing, lightheadedness, nasal congestion, hyperkalemia (high blood potassium).",
        "precautions": "Contraindicated during pregnancy. Monitor blood pressure and renal function regularly. Avoid potassium supplements unless prescribed.",
        "interactions": "Interacts with potassium-sparing diuretics, lithium, and NSAIDs.",
    },
    "montelukast": {
        "generic_name": "Montelukast Sodium",
        "drug_class": "Leukotriene Receptor Antagonist",
        "brand_names": ["Singulair", "Montair", "Montek-LC (with Levocetirizine)"],
        "uses": "Prevention and chronic treatment of asthma, and relief of allergic rhinitis symptoms.",
        "dosage_guidelines": "10 mg once daily in the evening for adults, taken with or without food.",
        "side_effects": "Upper respiratory infection, fever, headache, abdominal pain.",
        "precautions": "Not intended for the relief of acute asthma attacks (a rescue inhaler is required). Monitor for mood or behavior changes.",
        "interactions": "Phenobarbital and rifampin may reduce blood concentrations of montelukast.",
    },
}


def _query_openfda(medicine_name: str) -> Optional[Dict[str, Any]]:
    """Query the OpenFDA drug database for official label information."""
    clean_q = re.sub(r"[^\w\s-]", "", medicine_name).strip()
    if not clean_q:
        return None

    terms = clean_q.split()
    candidates = [clean_q]
    if len(terms) > 1:
        candidates.append(terms[0])

    for search_term in candidates:
        fda_url = (
            f"https://api.fda.gov/drug/label.json?search="
            f'(openfda.brand_name:"{urllib.parse.quote(search_term)}"+'
            f'openfda.generic_name:"{urllib.parse.quote(search_term)}")&limit=1'
        )

        try:
            req = urllib.request.Request(
                fda_url,
                headers={"User-Agent": "AIAssistant/1.0 (MedicalSearch)"},
            )
            with urllib.request.urlopen(req, timeout=3.5) as response:
                if response.status == 200:
                    data = json.loads(response.read().decode("utf-8"))
                    results = data.get("results", [])
                    if results:
                        rec = results[0]
                        openfda = rec.get("openfda", {})
                        generic = (openfda.get("generic_name") or [""])[0].title()
                        brand = (openfda.get("brand_name") or [""])[0].title()

                        purpose = " ".join(rec.get("purpose", []))[:250].strip()
                        indications = " ".join(rec.get("indications_and_usage", []))[:350].strip()
                        warnings = " ".join(rec.get("warnings", []))[:350].strip()
                        dosage = " ".join(rec.get("dosage_and_administration", []))[:300].strip()

                        clean_text = lambda s: re.sub(r"\s+", " ", re.sub(r"^[A-Z\s]+:", "", s)).strip()

                        return {
                            "generic_name": generic or medicine_name.title(),
                            "brand_names": [brand] if brand else [],
                            "uses": clean_text(indications or purpose) or "Used as directed by a healthcare professional.",
                            "dosage_guidelines": clean_text(dosage) or "Take as indicated on the prescription label.",
                            "side_effects": clean_text(rec.get("adverse_reactions", ["Consult package insert for side effects."])[0])[:250],
                            "precautions": clean_text(warnings) or "Read all warnings before use.",
                        }
        except Exception as e:
            logger.debug(f"OpenFDA lookup error for '{search_term}': {e}")

    return None


def _query_medical_web(medicine_name: str) -> Optional[Dict[str, Any]]:
    """Query verified medical search for medicines not in local database or FDA."""
    try:
        from agent.tools.search import web_search

        search_query = f"{medicine_name} medicine uses dosage side effects precautions"
        res = web_search(query=search_query)
        if res.get("success") and res.get("results"):
            snippets = [
                r.get("snippet", "") for r in res.get("results", [])
                if r.get("snippet") and not any(k in r.get("snippet", "").lower() for k in ["no live search results", "no results found", "could not find"])
            ]
            combined = " ".join(snippets[:4]).strip()
            if combined and medicine_name.lower() in combined.lower():
                return {
                    "generic_name": medicine_name.title(),
                    "brand_names": [medicine_name.title()],
                    "uses": combined[:300] + "...",
                    "dosage_guidelines": "Consult physician or product packaging for precise dosage instructions.",
                    "side_effects": "May cause common digestive or allergic reactions. Consult a doctor if adverse symptoms occur.",
                    "precautions": "Do not exceed recommended dose. Consult a healthcare provider if pregnant or taking other medications.",
                }
    except Exception as e:
        logger.debug(f"Medical web search fallback error: {e}")
    return None


def medical_search(medicine_name: str, topic: str = "all", user_query: Optional[str] = None) -> Dict[str, Any]:
    """Retrieve verified medical and pharmacological information about a medicine or drug.

    Args:
        medicine_name: Name of the medicine, drug, salt, or brand (e.g., 'Paracetamol',
                       'Dolo 650', 'Metformin', 'Ibuprofen', 'Azithromycin', 'Omeprazole').
        topic: Specific area of inquiry: 'uses', 'dosage', 'side_effects', 'precautions',
               'interactions', or 'all'. Defaults to 'all'.
        user_query: Optional full user prompt for contextual safety (e.g. pediatric checks).

    Returns:
        Structured dictionary with generic name, brand names, indications, dosage,
        side effects, precautions, interactions, spoken summary, and medical disclaimer.
    """
    if not medicine_name or not medicine_name.strip():
        return {
            "success": False,
            "error": "Please provide a valid medicine or drug name.",
            "spoken": "Please specify which medicine you would like to know about.",
            "disclaimer": MEDICAL_DISCLAIMER,
        }

    raw_query = medicine_name.strip()
    norm_q = raw_query.lower()

    # Step 1: Check curated high-confidence clinical database with exact/word-boundary priority
    matched_key = None
    if norm_q in CURATED_MEDICINE_DB:
        matched_key = norm_q
    else:
        # 1a. Exact brand match (e.g. "Pan 40", "Dolo 650")
        for key, entry in CURATED_MEDICINE_DB.items():
            brands_lower = [b.lower() for b in entry.get("brand_names", [])]
            if any(norm_q == re.sub(r"\s*\(.*?\)", "", b).strip() for b in brands_lower):
                matched_key = key
                break

        # 1b. Whole-word / boundary match across keys and brands (longest match wins)
        if not matched_key:
            q_pat = re.compile(rf"\b{re.escape(norm_q)}\b")
            candidates: List[tuple[int, str]] = []
            for key, entry in CURATED_MEDICINE_DB.items():
                if q_pat.search(key) or re.search(rf"\b{re.escape(key)}\b", norm_q):
                    candidates.append((len(key) + 100, key))
                    continue
                for b in entry.get("brand_names", []):
                    b_clean = re.sub(r"\s*\(.*?\)", "", b).strip().lower()
                    if q_pat.search(b_clean) or (len(b_clean) >= 3 and re.search(rf"\b{re.escape(b_clean)}\b", norm_q)):
                        candidates.append((len(b_clean), key))
                        break
            if candidates:
                candidates.sort(reverse=True)
                matched_key = candidates[0][1]

        # 1c. Conservative substring fallback only for queries >= 4 chars
        if not matched_key and len(norm_q) >= 4:
            for key, entry in CURATED_MEDICINE_DB.items():
                if norm_q in key or key in norm_q:
                    matched_key = key
                    break
                brands_lower = [b.lower() for b in entry.get("brand_names", [])]
                if any(norm_q in b or b in norm_q for b in brands_lower):
                    matched_key = key
                    break

    record: Optional[Dict[str, Any]] = None
    if matched_key:
        record = CURATED_MEDICINE_DB[matched_key].copy()
    else:
        # Step 2: Query OpenFDA official drug labels
        record = _query_openfda(raw_query)

        # Step 3: Query medical web search fallback
        if not record:
            record = _query_medical_web(raw_query)

    if not record:
        return {
            "success": False,
            "medicine": raw_query,
            "error": f"No clinical information found for '{raw_query}'.",
            "spoken": f"I could not find verified medical information for {raw_query}. Please consult a doctor or pharmacist.",
            "disclaimer": MEDICAL_DISCLAIMER,
        }

    generic_name = record.get("generic_name", raw_query.title())
    drug_class = record.get("drug_class", "Therapeutic Medication")
    brands = record.get("brand_names", [])
    brand_str = f" Commonly known as {', '.join(brands[:3])}." if brands else ""
    uses = record.get("uses", "Used under medical supervision.")
    dosage = record.get("dosage_guidelines", "Follow doctor's prescription.")
    side_effects = record.get("side_effects", "Consult your physician for adverse effect details.")
    precautions = record.get("precautions", "Consult a doctor prior to administration.")
    interactions = record.get("interactions", "Check with your doctor if taking other medications.")

    # Check for pediatric / child dosage inquiries to avoid recommending adult doses
    combined_context = f"{norm_q} {topic or ''} {user_query or ''}".lower()
    is_pediatric = any(k in combined_context for k in ["child", "pediatric", "infant", "baby", "toddler", "year old", "years old"])
    if is_pediatric:
        dosage = "For infants and children, pediatric dosing is strictly based on the child's exact weight. Never use adult tablets or guess doses. Always consult a pediatrician, doctor, or pharmacist, and read the product package label."

    # Compose natural spoken response based on requested topic
    topic_clean = (topic or "all").lower().strip()
    if is_pediatric:
        spoken_text = (
            f"For young children and toddlers, pediatric dosing of {generic_name} is strictly determined by weight. "
            "Never give adult formulations. Always consult a pediatrician, doctor, or pharmacist, and follow the exact product package label."
        )
    elif topic_clean in ["use", "uses", "indication", "indications", "what is it for"]:
        spoken_text = (
            f"{generic_name} is a {drug_class}.{brand_str} "
            f"It is primarily used for {uses} "
            "Always consult a licensed doctor or physician for personalized medical advice."
        )
    elif topic_clean in ["dosage", "dose", "how to take", "how much"]:
        spoken_text = (
            f"Regarding dosage for {generic_name}: {dosage} "
            "Always follow the exact prescription given by your doctor."
        )
    elif topic_clean in ["side_effect", "side_effects", "adverse", "reactions"]:
        spoken_text = (
            f"Potential side effects of {generic_name} include: {side_effects} "
            "Consult a doctor, or seek immediate medical attention if severe symptoms occur."
        )
    elif topic_clean in ["precaution", "precautions", "warnings", "warning"]:
        spoken_text = (
            f"Key precautions for {generic_name}: {precautions} "
            "Always inform your doctor of any pre-existing health conditions."
        )
    elif topic_clean in ["interaction", "interactions"]:
        spoken_text = (
            f"Regarding drug interactions for {generic_name}: {interactions} "
            "Consult your doctor or pharmacist before combining medications."
        )
    else:
        # Comprehensive overview for general inquiries
        spoken_text = (
            f"{generic_name} is a {drug_class}.{brand_str} "
            f"It is primarily used for {uses} "
            f"General dosage guidelines are {dosage} "
            f"Common precautions include: {precautions} "
            "Always consult your doctor or pharmacist before taking this medication."
        )

    # Clean spoken text of any leftover markdown
    spoken_text = re.sub(r"[\*\_#`]", "", spoken_text)
    spoken_text = re.sub(r"\s+", " ", spoken_text).strip()

    return {
        "success": True,
        "medicine": raw_query,
        "generic_name": generic_name,
        "drug_class": drug_class,
        "brand_names": brands,
        "uses": uses,
        "dosage_guidelines": dosage,
        "side_effects": side_effects,
        "precautions": precautions,
        "interactions": interactions,
        "spoken": spoken_text,
        "disclaimer": MEDICAL_DISCLAIMER,
    }

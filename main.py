import os
import feedparser
import requests
import json
import re
import io
import time
from datetime import datetime
from google import genai
from google.genai import types

# =============================================================
# CONFIGURATION — variables d'environnement (GitHub Secrets)
# =============================================================

GEMINI_API_KEY     = os.environ["GEMINI_API_KEY"]
RESEND_API_KEY     = os.environ["RESEND_API_KEY"]
EMAIL_DESTINATAIRE = os.environ["EMAIL_DESTINATAIRE"]

client = genai.Client(api_key=GEMINI_API_KEY)

# =============================================================
# SOURCES
# =============================================================

SOURCES = [
    {
        "media": "France Inter",
        "emission": "L'invité de 8h20 — Le grand entretien",
        "journaliste": "Nicolas Demorand et Benjamin Duhamel",
        "heure": "8h20",
        "type": "rss",
        "rss": "https://radiofrance-podcast.net/podcast09/rss_10239.xml"
    },
    {
        "media": "France Info",
        "emission": "8h30 franceinfo",
        "journaliste": "Agathe Lambret et Paul Larrouturou",
        "heure": "8h30",
        "type": "rss",
        "rss": "https://radiofrance-podcast.net/podcast09/rss_16370.xml"
    },
    {
        "media": "RTL",
        "emission": "L'invité RTL de 7h40",
        "journaliste": "Thomas Sotto",
        "heure": "7h40",
        "type": "rss",
        "rss": "https://feeds.audiomeans.fr/feed/bc8743c2-c669-4743-b58e-f689951a261b.xml"
    },
    {
        "media": "Europe 1",
        "emission": "La Grande interview Europe 1 - CNews",
        "journaliste": "Sonia Mabrouk",
        "heure": "8h10",
        "type": "rss",
        "rss": "https://feeds.audiomeans.fr/feed/7dd2a532-d19a-46bb-9ac7-a5eefff10b62.xml"
    },
    {
        "media": "RMC",
        "emission": "Face à Face",
        "journaliste": "Apolline de Malherbe",
        "heure": "8h30",
        "type": "rss",
        "rss": "https://feeds.simplecast.com/0H53ly_3"
    },
    {
        "media": "Sud Radio",
        "emission": "L'invité politique",
        "journaliste": "Jean-François Achilli",
        "heure": "8h15",
        "type": "scrape",
        "page": "https://www.sudradio.fr/programme/le-petit-dejeuner-politique-sudradio",
        "audio_pattern": r"https://podcasts\.sudradio\.fr/podcast/download/\d+\.mp3"
    },
]

# =============================================================
# PROMPT
# =============================================================

PROMPT_TEMPLATE = """
Tu es un analyste senior en affaires publiques. Tu écoutes un enregistrement audio d'une interview politique matinale française. Ton livrable s'adresse à un professionnel qui doit, en 30 secondes de lecture, comprendre ce qui s'est dit de stratégiquement utile.

Source analysée :
- Média : {media}
- Émission : {emission}
- Journaliste : {journaliste}
- Heure de diffusion : {heure}
- Date : {date}

Règles strictes :

Sur l'invité : Identifie l'invité en début d'interview. Si tu n'es pas certain de son nom ou de sa fonction exacte, indique "a_verifier" dans le champ certitude. Ne devine jamais une fonction politique.

Sur les propositions et annonces : Identifie les éléments actionnables exprimés par l'invité : engagements, annonces, votes annoncés, soutiens ou oppositions explicites à un texte ou une décision, initiatives en cours. Maximum 4 éléments, formulés comme des faits bruts à la troisième personne.

Exemples de ce qu'on cherche :
- "X annonce qu'il votera contre le projet de loi Y"
- "X se déclare candidat à Z sans attendre une primaire"
- "X réclame une saisine de l'Arcom sur le dossier Y"
- "X s'engage à déposer une proposition de loi sur Z"

Exemples de ce qu'on ne veut pas :
- "X défend une vision de la France unie" → position idéologique, pas actionnable
- "X critique la gestion de l'immigration" → critique générale, pas actionnable
- "X appelle à plus de justice sociale" → déclaration de principe, pas actionnable

Si l'interview ne contient aucun élément actionnable, renvoie la chaîne "aucune annonce".

Sur l'actualité visée : Identifie le ou les textes, annonces ou arbitrages concrets évoqués : projet de loi, décret, rapport, négociation en cours, échéance parlementaire, nomination. Sois précis quand l'invité l'est. Si l'interview est généraliste sans actualité précise, renvoie la chaîne "aucune".

Sur les signaux faibles : Un signal faible est une esquive sur une question précise, une formulation nouvelle qui rompt avec la ligne habituelle de l'invité, un changement de ton, une concession ou un aveu implicite, une attaque personnelle ou un nom cité de façon inhabituelle. Chaque signal faible doit être ancré dans un moment précis de l'interview avec un timecode. Si tu ne peux pas associer le signal à un échange spécifique, ne le retiens pas. Maximum 3 signaux faibles. Si tu ne détectes rien de significatif, renvoie un tableau vide. Ne pas inventer pour remplir.

Sur le verbatim notable : Un seul verbatim notable maximum. Citation textuelle uniquement, pas une reformulation. Timecode au format MM:SS. Maximum 25 mots. Si tu hésites sur l'exactitude des mots, renvoie citation: "aucun", timecode: "", contexte: "".

Format de sortie : Renvoie un objet JSON. Aucun texte hors JSON.
"""

# =============================================================
# PIPELINE — analyse d'une source
# =============================================================

def analyser_source(source, date_cible=None):
    if date_cible is None:
        date_cible = datetime.now().strftime("%Y-%m-%d")

    print(f"\n{'='*50}")
    print(f"▶ {source['media']}")

    # 1. Récupérer l'URL audio
    if source.get("type") == "scrape":
        try:
            headers = {"User-Agent": "Mozilla/5.0"}
            page = requests.get(source["page"], headers=headers, timeout=30)
            urls = re.findall(source["audio_pattern"], page.text)
            if not urls:
                return {"erreur": "aucun lien audio trouvé", "_meta": {"media": source["media"]}}
            audio_url = urls[0]
            episode_title = "Sud Radio — épisode du jour"
            print(f"  Épisode : {audio_url}")
        except Exception as e:
            return {"erreur": f"scraping échoué : {str(e)}", "_meta": {"media": source["media"]}}
    else:
        try:
            feed = feedparser.parse(source["rss"])
            if not feed.entries:
                return {"erreur": "flux RSS vide", "_meta": {"media": source["media"]}}
        except Exception as e:
            return {"erreur": f"RSS inaccessible : {str(e)}", "_meta": {"media": source["media"]}}

        episode = feed.entries[0]
        episode_title = episode.title
        print(f"  Épisode : {episode_title[:70]}")
        print(f"  Publié  : {episode.get('published', '?')}")

        enclosures = episode.get("enclosures", [])
        if not enclosures:
            return {"erreur": "pas d'enclosure audio", "_meta": {"media": source["media"]}}
        audio_url = enclosures[0].get("href", "")
        if not audio_url:
            return {"erreur": "URL audio manquante", "_meta": {"media": source["media"]}}

    print(f"  Audio   : {audio_url[:70]}...")

    # 2. Télécharger l'audio
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(audio_url, headers=headers, timeout=120)
        audio_bytes = response.content
        taille_mo = len(audio_bytes) / (1024 * 1024)
        print(f"  Taille  : {taille_mo:.1f} Mo")
    except Exception as e:
        return {"erreur": f"téléchargement échoué : {str(e)}", "_meta": {"media": source["media"]}}

    # 3. Upload vers Gemini Files API + attente état ACTIVE
    try:
        mime_type = "audio/mpeg"
        if audio_url.endswith(".m4a"):
            mime_type = "audio/mp4"
        elif audio_url.endswith(".aac"):
            mime_type = "audio/aac"

        audio_file = client.files.upload(
            file=io.BytesIO(audio_bytes),
            config={"mime_type": mime_type}
        )

        max_wait = 30
        waited = 0
        while waited < max_wait:
            file_info = client.files.get(name=audio_file.name)
            if file_info.state.name == "ACTIVE":
                print(f"  Upload  : ✅ (prêt en {waited}s)")
                break
            time.sleep(2)
            waited += 2
        else:
            return {"erreur": "fichier Gemini non prêt après 30s", "_meta": {"media": source["media"]}}

    except Exception as e:
        return {"erreur": f"upload Gemini échoué : {str(e)}", "_meta": {"media": source["media"]}}

    # 4. Construire le prompt
    prompt = PROMPT_TEMPLATE.format(
        media=source["media"],
        emission=source["emission"],
        journaliste=source["journaliste"],
        heure=source["heure"],
        date=date_cible
    )

    # 5. Appel Gemini
    try:
        t0 = time.time()
        gemini_response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[audio_file, prompt],
            config=types.GenerateContentConfig(
                temperature=0.1,
                response_mime_type="application/json"
            )
        )
        duree = round(time.time() - t0, 1)
        tokens_in  = gemini_response.usage_metadata.prompt_token_count
        tokens_out = gemini_response.usage_metadata.candidates_token_count
        print(f"  Gemini  : ✅ ({duree}s — {tokens_in} tokens in / {tokens_out} out)")
    except Exception as e:
        return {"erreur": f"appel Gemini échoué : {str(e)}", "_meta": {"media": source["media"]}}

    # 6. Parser le JSON
    try:
        resultat = json.loads(gemini_response.text)
        resultat["_meta"] = {
            "media": source["media"],
            "episode": episode_title,
            "audio_url": audio_url,
            "duree_analyse_s": duree,
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "date": date_cible
        }
        return resultat
    except Exception as e:
        return {
            "erreur": f"JSON invalide : {str(e)}",
            "raw": gemini_response.text[:300],
            "_meta": {"media": source["media"]}
        }
    finally:
        try:
            client.files.delete(audio_file.name)
        except:
            pass

# =============================================================
# FIL DU JOUR
# =============================================================

def generer_fil_du_jour(resultats):
    blocs = []
    for r in resultats:
        if "erreur" in r:
            continue
        media = r.get("_meta", {}).get("media", "?")
        invite_raw = r.get("invité") or r.get("invite") or {}
        nom = invite_raw.get("nom", "?") if isinstance(invite_raw, dict) else "?"
        annonces = (
            r.get("propositions_et_annonces") or
            r.get("annonces_propositions") or
            r.get("annonces") or []
        )
        if isinstance(annonces, str):
            annonces = [annonces]
        actualite = (
            r.get("actualité_visée") or
            r.get("actualite_visee") or "aucune"
        )
        if isinstance(actualite, list):
            actualite = " · ".join(actualite)
        blocs.append(f"""
{media} — {nom}
Annonces : {chr(10).join(f'- {a}' for a in annonces) if annonces else 'aucune'}
Actualité visée : {actualite}
""")

    prompt_fil = f"""Voici les analyses de plusieurs matinales politiques françaises diffusées ce matin. Identifie en 3 phrases maximum les sujets transversaux : quels thèmes reviennent sur plusieurs antennes, quelles actualités législatives ou politiques sont au cœur du cycle de la journée.

Règles :
- Ton factuel-neutre. Constater, pas commenter.
- Pas de verbes d'opinion (domine, marque, cale).
- Pas de superlatifs.
- Ne pas lister les médias dans la synthèse.
- Pas de phrase d'introduction type "Ce matin, on observe...".
- Commencer directement par le constat.

Si rien de transversal ne se dégage, écrire uniquement :
"Pas de thème dominant ce matin — sujets dispersés."

Analyses du jour :
{"---".join(blocs)}"""

    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[prompt_fil],
            config=types.GenerateContentConfig(temperature=0.1)
        )
        return response.text.strip()
    except Exception as e:
        print(f"Erreur fil du jour : {e}")
        return "Synthèse transversale indisponible ce matin."

# =============================================================
# RENDU EMAIL
# =============================================================

def generer_email(resultats, fil_du_jour, date_str=None):
    if date_str is None:
        date_str = datetime.now().strftime("%A %d %B %Y").capitalize()

    sources_ok = [r for r in resultats if "erreur" not in r]
    sources_ko = [r for r in resultats if "erreur" in r]

    total_tokens = sum(r.get("_meta", {}).get("tokens_in", 0) for r in sources_ok)
    total_duree  = sum(r.get("_meta", {}).get("duree_analyse_s", 0) for r in sources_ok)
    cout         = (total_tokens / 1_000_000) * 0.30

    ORDRE = ["France Inter", "France Info", "RTL", "Europe 1", "RMC", "Sud Radio"]

    def get_resultat(media):
        for r in resultats:
            if r.get("_meta", {}).get("media") == media:
                return r
        return None

    def normaliser_string(valeur, defaut="aucune"):
        if valeur is None:
            return defaut
        if isinstance(valeur, list):
            return " · ".join(str(x) for x in valeur if x)
        return str(valeur).strip() or defaut

    blocs_sources = ""
    for media in ORDRE:
        r = get_resultat(media)
        if r is None or "erreur" in r:
            continue

        invite_raw = r.get("invité") or r.get("invite") or {}
        if isinstance(invite_raw, dict):
            nom       = invite_raw.get("nom", "?")
            fonction  = invite_raw.get("fonction", "")
            certitude = invite_raw.get("certitude", "confirmee")
        else:
            nom, fonction, certitude = str(invite_raw), "", "confirmee"
        flag_invite = " ⚠️" if certitude not in ("confirmee", "certain", "certaine") else ""

        annonces = (
            r.get("propositions_et_annonces") or
            r.get("annonces_propositions") or
            r.get("annonces") or []
        )
        if isinstance(annonces, str):
            annonces = [annonces]

        actualite = normaliser_string(
            r.get("actualité_visée") or
            r.get("actualite_visee") or None
        )

        signaux = []
        for s in r.get("signaux_faibles", []):
            if isinstance(s, dict):
                tc   = s.get("timecode", "")
                desc = s.get("description") or s.get("observation") or s.get("signal") or ""
                signaux.append(f"[{tc}] {desc}" if tc else desc)
            elif isinstance(s, str):
                signaux.append(s)

        verbatim_raw = r.get("verbatim_notable") or r.get("verbatim") or {}
        if isinstance(verbatim_raw, dict):
            citation = normaliser_string(verbatim_raw.get("citation"), "aucun")
            timecode = normaliser_string(verbatim_raw.get("timecode"), "")
            contexte = normaliser_string(verbatim_raw.get("contexte"), "")
        else:
            citation = normaliser_string(verbatim_raw, "aucun")
            timecode, contexte = "", ""

        if annonces:
            items = "".join(f"<li>{a}</li>" for a in annonces)
            annonces_html = f"""
            <div class="section-label">Propositions &amp; annonces</div>
            <ul class="annonces">{items}</ul>"""
        else:
            annonces_html = """
            <div class="section-label">Propositions &amp; annonces</div>
            <p class="empty">Aucune annonce actionnable</p>"""

        if actualite and actualite.lower() not in ("aucune", "aucun", "none", ""):
            actualite_html = f"""
            <div class="section-label">Actualité visée</div>
            <p class="actualite">{actualite}</p>"""
        else:
            actualite_html = ""

        if signaux:
            items = "".join(f"<li>{s}</li>" for s in signaux)
            signaux_html = f"""
            <div class="section-label">Signaux faibles</div>
            <ul class="signaux">{items}</ul>"""
        else:
            signaux_html = ""

        if citation and citation.lower() not in ("aucun", "aucune", "none", ""):
            tc_str  = f" <span class='timecode'>[{timecode}]</span>" if timecode else ""
            ctx_str = f"<div class='verbatim-contexte'>{contexte}</div>" if contexte else ""
            verbatim_html = f"""
            <div class="section-label">Verbatim notable</div>
            <blockquote>«&nbsp;{citation}&nbsp;»{tc_str}</blockquote>
            {ctx_str}"""
        else:
            verbatim_html = ""

        meta    = r.get("_meta", {})
        duree_s = meta.get("duree_analyse_s", 0)
        episode = meta.get("episode", "")[:60]

        blocs_sources += f"""
        <div class="source-bloc">
            <div class="source-header">
                <span class="source-name">▸ {media}</span>
                <span class="source-meta">{episode}...</span>
            </div>
            <div class="invite">
                <strong>{nom}{flag_invite}</strong>
                {f'<span class="fonction"> — {fonction}</span>' if fonction else ''}
            </div>
            {annonces_html}
            {actualite_html}
            {signaux_html}
            {verbatim_html}
            <div class="source-footer">Analysé en {duree_s}s</div>
        </div>"""

    indispo_html = ""
    if sources_ko:
        items = "".join(
            f"<li>{r.get('_meta', {}).get('media', '?')} — {r.get('erreur', '?')}</li>"
            for r in sources_ko
        )
        indispo_html = f"""
        <div class="indispo-bloc">
            <strong>⚠️ Indisponibles à 9h45</strong>
            <ul>{items}</ul>
        </div>"""

    html = f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<style>
  body {{
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    font-size: 14px;
    line-height: 1.6;
    color: #1a1a1a;
    max-width: 680px;
    margin: 0 auto;
    padding: 24px 16px;
    background: #f9f9f7;
  }}
  .header {{
    border-bottom: 2px solid #1a1a1a;
    padding-bottom: 12px;
    margin-bottom: 20px;
  }}
  .header h1 {{
    font-size: 18px;
    font-weight: 700;
    margin: 0 0 4px 0;
    letter-spacing: 0.05em;
    text-transform: uppercase;
  }}
  .header .meta {{ font-size: 12px; color: #666; }}
  .fil-du-jour {{
    background: #1a1a1a;
    color: #f9f9f7;
    padding: 14px 16px;
    margin-bottom: 24px;
    border-radius: 2px;
  }}
  .fil-du-jour .label {{
    font-size: 10px;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    opacity: 0.6;
    margin-bottom: 6px;
  }}
  .fil-du-jour p {{ margin: 0; font-size: 13px; line-height: 1.7; }}
  .source-bloc {{
    background: #fff;
    border: 1px solid #e5e5e5;
    padding: 16px;
    margin-bottom: 12px;
    border-radius: 2px;
  }}
  .source-header {{ margin-bottom: 10px; }}
  .source-name {{
    font-weight: 700;
    font-size: 13px;
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }}
  .source-meta {{
    display: block;
    font-size: 11px;
    color: #888;
    margin-top: 2px;
  }}
  .invite {{
    font-size: 14px;
    margin-bottom: 12px;
    padding-bottom: 10px;
    border-bottom: 1px solid #f0f0f0;
  }}
  .fonction {{ color: #555; font-weight: 400; }}
  .section-label {{
    font-size: 10px;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: #888;
    margin: 12px 0 4px 0;
  }}
  ul.annonces, ul.signaux {{ margin: 0; padding-left: 18px; }}
  ul.annonces li, ul.signaux li {{ font-size: 13px; margin-bottom: 4px; }}
  ul.annonces li {{ color: #1a1a1a; }}
  ul.signaux li {{ color: #444; font-style: italic; }}
  .actualite {{ font-size: 13px; color: #333; margin: 0; }}
  blockquote {{
    border-left: 3px solid #1a1a1a;
    margin: 6px 0;
    padding: 6px 12px;
    font-size: 13px;
    font-style: italic;
    color: #222;
  }}
  .timecode {{ font-style: normal; font-size: 11px; color: #888; }}
  .verbatim-contexte {{ font-size: 11px; color: #888; margin-top: 4px; }}
  .empty {{ color: #aaa; font-size: 12px; margin: 0; }}
  .source-footer {{
    font-size: 10px;
    color: #ccc;
    margin-top: 12px;
    text-align: right;
  }}
  .indispo-bloc {{
    background: #fff8f0;
    border: 1px solid #f0c070;
    padding: 12px 16px;
    margin-bottom: 12px;
    font-size: 12px;
  }}
  .indispo-bloc ul {{ margin: 6px 0 0 0; padding-left: 16px; }}
  .run-bloc {{
    border-top: 1px solid #e5e5e5;
    margin-top: 24px;
    padding-top: 12px;
    font-size: 11px;
    color: #aaa;
  }}
  .run-bloc strong {{ color: #888; }}
  .disclaimer {{
    font-size: 10px;
    color: #bbb;
    margin-top: 16px;
    padding-top: 12px;
    border-top: 1px solid #f0f0f0;
  }}
</style>
</head>
<body>

<div class="header">
  <h1>Matinales — {date_str}</h1>
  <div class="meta">
    {len(sources_ok)} sources analysées
    {f'· {len(sources_ko)} indisponible(s)' if sources_ko else ''}
  </div>
</div>

<div class="fil-du-jour">
  <div class="label">📍 Fil du jour</div>
  <p>{fil_du_jour}</p>
</div>

{blocs_sources}
{indispo_html}

<div class="run-bloc">
  <strong>Run du jour</strong> ·
  Durée : {round(total_duree)}s ·
  Tokens : {total_tokens:,} ·
  Coût estimé : {cout*30:.3f} € ·
  Modèle : gemini-2.5-flash
</div>

<div class="disclaimer">
  Transcriptions et timecodes générés par IA · À vérifier avant toute citation publique
</div>

</body>
</html>"""

    return html

# =============================================================
# ENVOI EMAIL
# =============================================================

def envoyer_email(html, date_str):
    response = requests.post(
        "https://api.resend.com/emails",
        headers={
            "Authorization": f"Bearer {RESEND_API_KEY}",
            "Content-Type": "application/json"
        },
        json={
            "from": "Matinales <onboarding@resend.dev>",
            "to": [EMAIL_DESTINATAIRE],
            "subject": f"Matinales — {date_str}",
            "html": html
        }
    )
    if response.status_code == 200:
        print(f"✅ Email envoyé à {EMAIL_DESTINATAIRE}")
    else:
        print(f"❌ Erreur envoi : {response.status_code} — {response.text}")

# =============================================================
# MAIN
# =============================================================

if __name__ == "__main__":
    date_cible   = datetime.now().strftime("%Y-%m-%d")
    date_lisible = datetime.now().strftime("%A %d %B %Y").capitalize()

    print(f"=== HUMEUR MATINALE — {date_lisible} ===\n")

    # 1. Analyser les 6 sources
    resultats = []
    for source in SOURCES:
        r = analyser_source(source, date_cible=date_cible)
        resultats.append(r)
        time.sleep(3)

    # 2. Fil du jour
    print("\n--- Génération du fil du jour ---")
    fil = generer_fil_du_jour(resultats)
    print(fil)

    # 3. Email HTML
    print("\n--- Génération de l'email ---")
    html = generer_email(resultats, fil, date_str=date_lisible)

    # 4. Envoi
    print("\n--- Envoi ---")
    envoyer_email(html, date_str=date_lisible)

    # 5. Bilan
    sources_ok = [r for r in resultats if "erreur" not in r]
    sources_ko = [r for r in resultats if "erreur" in r]
    print(f"\n=== BILAN : {len(sources_ok)}/6 sources OK ===")
    for r in sources_ko:
        print(f"  ❌ {r.get('_meta', {}).get('media', '?')} : {r.get('erreur', '?')}")

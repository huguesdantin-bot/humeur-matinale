# Humeur Matinale 🎙️

Agent IA de surveillance et d'analyse des interviews politiques matinales françaises.

## Ce que ça fait

Chaque matin en semaine à 9h30, cet agent :

1. **Surveille** 6 flux RSS / sources audio de matinales politiques françaises
2. **Analyse** chaque interview via Gemini 2.5 Flash (multimodal audio → texte)
3. **Extrait** les annonces actionnables, l'actualité visée, les signaux faibles et un verbatim notable
4. **Synthétise** les thèmes transversaux de la matinée en 3 phrases
5. **Livre** un email HTML structuré avant 10h00

## Sources surveillées

| Média | Émission | Journaliste |
|---|---|---|
| France Inter | L'invité de 8h20 | Nicolas Demorand / Benjamin Duhamel |
| France Info | 8h30 franceinfo | Agathe Lambret / Paul Larrouturou |
| RTL | L'invité RTL de 7h40 | Thomas Sotto |
| Europe 1 | La Grande interview | Sonia Mabrouk |
| RMC | Face à Face | Apolline de Malherbe |
| Sud Radio | L'invité politique | Jean-François Achilli |

## Structure du livrable

Chaque interview est analysée selon 4 dimensions :

- **Propositions & annonces** — éléments actionnables (votes, engagements, initiatives)
- **Actualité visée** — textes, décrets, échéances parlementaires évoqués
- **Signaux faibles** — esquives, ruptures de ton, formulations nouvelles (avec timecode)
- **Verbatim notable** — citation textuelle courte (avec timecode, à vérifier avant usage)

Un **Fil du jour** en ouverture synthétise les thèmes transversaux détectés sur l'ensemble des sources.

## Architecture technique

```
humeur-matinale/
├── main.py              # Pipeline complet (RSS → audio → Gemini → email)
├── requirements.txt     # Dépendances Python
└── .github/
    └── workflows/
        └── matinales.yml   # Déclencheur GitHub Actions (cron 9h30 lun-ven)
```

**Stack :**
- **Langage** : Python 3.11
- **Déclencheur** : GitHub Actions (cron, zéro infra à maintenir)
- **Modèle** : Gemini 2.5 Flash via API (analyse audio multimodale)
- **Envoi email** : Resend API
- **Coût estimé** : ~2 € / mois (22 jours ouvrés × ~0,09 €/run)

## Comment ça marche (pour le workshop)

Le pipeline se décompose en 6 étapes observables dans les logs GitHub Actions :

```
1. Parsing RSS          → récupération de l'URL audio du dernier épisode
2. Téléchargement       → récupération du fichier audio (~20-30 Mo)
3. Upload Gemini        → envoi à l'API Files de Gemini, attente état ACTIVE
4. Analyse multimodale  → un seul appel API, audio + prompt → JSON structuré
5. Synthèse transverse  → second appel Gemini texte → Fil du jour
6. Rendu & envoi        → génération HTML + envoi via Resend
```

Le prompt d'analyse est versionné dans `main.py` (section `PROMPT_TEMPLATE`). Chaque modification est tracée dans l'historique Git — ce qui permet de mesurer l'impact d'un changement de prompt sur la qualité des analyses.

## Installation et déploiement

### Prérequis
- Compte GitHub (gratuit)
- Clé API Gemini — [aistudio.google.com](https://aistudio.google.com)
- Compte Resend — [resend.com](https://resend.com) (3000 emails/mois gratuits)

### Configuration

1. Forke ce repo
2. Dans **Settings → Secrets and variables → Actions**, ajoute 3 secrets :

| Secret | Valeur |
|---|---|
| `GEMINI_API_KEY` | Ta clé API Gemini (`AIza...`) |
| `RESEND_API_KEY` | Ta clé API Resend (`re_...`) |
| `EMAIL_DESTINATAIRE` | Ton adresse email |

3. Dans **Actions → Humeur Matinale → Run workflow** pour un premier test manuel

Le pipeline se déclenche ensuite automatiquement chaque matin en semaine.

## Limites et précautions

- **Verbatims** : générés par IA, à vérifier à l'écoute avant toute citation publique
- **Timecodes** : peuvent être approximatifs sur les fichiers audio longs
- **Disponibilité** : certaines sources peuvent ne pas avoir publié leur podcast avant 9h30 — elles apparaissent dans la section "Indisponibles" de l'email
- **Filtres Gemini** : sur certains sujets sensibles (affaires judiciaires, contenus violents), Gemini peut refuser l'analyse — la source est alors marquée indisponible

## Contexte

Développé dans le cadre du workshop **"In the Loop"** (module 3 — Ouvrir le capot), ce projet illustre comment un professionnel des affaires publiques peut construire un agent IA opérationnel sans infrastructure complexe, en combinant des outils no-code/low-code accessibles.

---

*Transcriptions et timecodes générés par IA · À vérifier avant toute citation publique*


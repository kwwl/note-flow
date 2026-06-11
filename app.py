import base64
import io
import os
import unicodedata
from datetime import datetime
from pathlib import Path
from html import escape
from fastapi import FastAPI, File, UploadFile, HTTPException, Request, Form, Depends, Query
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from backend import ExpenseAgent, GoogleSheetsClient, SupabaseStorage

BASE_DIR = Path(__file__).parent
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 Mo
ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp"}

app = FastAPI(title="NoteFlow — Gestion des notes de frais")
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")

agent = ExpenseAgent()
sheets = GoogleSheetsClient()
supabase = SupabaseStorage()

security = HTTPBearer()

CONFIDENCE_CLASS = {
    "haute": "confidence-high",
    "moyen": "confidence-medium",
    "basse": "confidence-low",
}

MOIS_FR = {
    1: "Janvier", 2: "Février", 3: "Mars", 4: "Avril",
    5: "Mai", 6: "Juin", 7: "Juillet", 8: "Août",
    9: "Septembre", 10: "Octobre", 11: "Novembre", 12: "Décembre",
}


# ── Auth ───────────────────────────────────────────────────────────────────────

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    try:
        user = supabase.verify_jwt(credentials.credentials)
        profile = supabase.get_profile(str(user.id))
        return {
            "id": str(user.id),
            "nom": profile.get("nom", ""),
            "prenom": profile.get("prenom", ""),
        }
    except Exception:
        raise HTTPException(401, detail="Session expirée. Veuillez vous reconnecter.")


# ── Fragments HTML ─────────────────────────────────────────────────────────────

def build_form_fragment(data: dict, image_b64: str, media_type: str) -> str:
    def v(field):
        val = data.get(field)
        return escape(str(val)) if val is not None else ""

    confidence_raw = str(data.get("confiance", "")).lower()
    confidence_class = CONFIDENCE_CLASS.get(confidence_raw, "confidence-medium")

    type_options = ""
    for opt in ["restaurant", "transport", "hôtel", "autre"]:
        selected = "selected" if data.get("type_document") == opt else ""
        type_options += f'<option value="{opt}" {selected}>{opt.capitalize()}</option>'

    confiance_options = ""
    for opt in ["haute", "moyen", "basse"]:
        selected = "selected" if confidence_raw == opt else ""
        confiance_options += f'<option value="{opt}" {selected}>{opt.capitalize()}</option>'

    return f"""
<form
  hx-post="/api/submit"
  hx-target="#result"
  hx-swap="innerHTML"
  hx-encoding="multipart/form-data"
  class="expense-form"
>
  <div class="form-group">
    <label>Type de document</label>
    <select name="type_document">{type_options}</select>
  </div>
  <div class="form-group">
    <label>Fournisseur</label>
    <input type="text" name="fournisseur" value="{v('fournisseur')}" />
  </div>
  <div class="form-group">
    <label>Date (JJ/MM/AAAA)</label>
    <input type="text" name="date" value="{v('date')}" placeholder="ex : 08/06/2026" />
  </div>
  <div class="form-row">
    <div class="form-group">
      <label>Montant TTC (€)</label>
      <input type="number" step="0.01" name="montant_ttc" value="{v('montant_ttc')}" />
    </div>
    <div class="form-group">
      <label>TVA (€)</label>
      <input type="number" step="0.01" name="tva" value="{v('tva')}" />
    </div>
    <div class="form-group">
      <label>Devise</label>
      <input type="text" name="devise" value="{v('devise') or 'EUR'}" maxlength="5" />
    </div>
  </div>
  <div class="form-group">
    <label>Description</label>
    <input type="text" name="description" value="{v('description')}" />
  </div>
  <div class="form-group">
    <label>Confiance</label>
    <select name="confiance">{confiance_options}</select>
    <span class="confidence-badge {confidence_class}">{escape(str(data.get("confiance", "—")))}</span>
  </div>
  <input type="hidden" name="image_data" value="{image_b64}" />
  <input type="hidden" name="media_type" value="{media_type}" />
  <button type="submit" class="btn-submit">Envoyer vers Google Sheets</button>
</form>
"""


def build_success_fragment(image_url: str = None) -> str:
    img_tag = (
        f'<img src="{escape(image_url)}" alt="Justificatif archivé" class="archived-img" />'
        if image_url else ""
    )
    return f"""
<div class="result-success">
  <p class="success-message">✅ Note de frais enregistrée avec succès dans Google Sheets.</p>
  {img_tag}
</div>
"""


def build_history_fragment(expenses: list) -> str:
    if not expenses:
        return '<p class="text-muted">Aucune note de frais pour le moment.</p>'

    rows = ""
    for e in expenses:
        montant = f"{e.get('montant_ttc') or '—'} {e.get('devise') or 'EUR'}"
        image_link = f'<a href="{escape(e["image_url"])}" target="_blank">🖼</a>' if e.get("image_url") else "—"
        rows += f"""
        <tr>
          <td>{escape(str(e.get("date") or "—"))}</td>
          <td>{escape(str(e.get("type_document") or "—"))}</td>
          <td>{escape(str(e.get("fournisseur") or "—"))}</td>
          <td>{escape(str(montant))}</td>
          <td>{image_link}</td>
        </tr>"""

    return f"""
<div class="history-card">
  <h3 class="history-title">Mes 5 dernières notes de frais</h3>
  <table class="history-table">
    <thead>
      <tr>
        <th>Date</th><th>Type</th><th>Fournisseur</th><th>Montant</th><th>Ticket</th>
      </tr>
    </thead>
    <tbody>{rows}</tbody>
  </table>
</div>
"""


# ── Génération PDF ─────────────────────────────────────────────────────────────

def generate_pdf(expenses: list, profile: dict, year: int, month: int) -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4,
                            leftMargin=2*cm, rightMargin=2*cm,
                            topMargin=2*cm, bottomMargin=2*cm)
    styles = getSampleStyleSheet()
    story = []

    # Titre
    title_style = ParagraphStyle("title", parent=styles["Title"],
                                  fontSize=18, spaceAfter=6)
    story.append(Paragraph("NoteFlow — Récapitulatif des notes de frais", title_style))

    sub_style = ParagraphStyle("sub", parent=styles["Normal"],
                                fontSize=11, textColor=colors.grey, spaceAfter=4)
    nom_complet = f"{profile.get('prenom', '')} {profile.get('nom', '')}".strip()
    story.append(Paragraph(f"{nom_complet} — {MOIS_FR[month]} {year}", sub_style))
    story.append(Spacer(1, 0.5*cm))

    if not expenses:
        story.append(Paragraph("Aucune note de frais pour ce mois.", styles["Normal"]))
    else:
        # En-têtes
        headers = ["Date", "Type", "Fournisseur", "Description", "Montant TTC", "TVA", "Devise"]
        table_data = [headers]
        total = 0.0

        for e in expenses:
            montant = e.get("montant_ttc") or 0
            total += montant
            table_data.append([
                e.get("date") or "—",
                e.get("type_document") or "—",
                e.get("fournisseur") or "—",
                e.get("description") or "—",
                f"{montant:.2f} €",
                f"{e.get('tva') or '—'}",
                e.get("devise") or "EUR",
            ])

        # Ligne total
        table_data.append(["", "", "", "TOTAL", f"{total:.2f} €", "", ""])

        col_widths = [2.5*cm, 2.5*cm, 3.5*cm, 5*cm, 2.5*cm, 2*cm, 1.5*cm]
        t = Table(table_data, colWidths=col_widths, repeatRows=1)
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#5b6ef5")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, 0), 9),
            ("FONTSIZE", (0, 1), (-1, -1), 8),
            ("ROWBACKGROUNDS", (0, 1), (-1, -2), [colors.white, colors.HexColor("#f5f6ff")]),
            ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#eef0ff")),
            ("FONTNAME", (3, -1), (4, -1), "Helvetica-Bold"),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cccccc")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("PADDING", (0, 0), (-1, -1), 5),
        ]))
        story.append(t)

    doc.build(story)
    return buffer.getvalue()


# ── Gestionnaire d'erreurs ─────────────────────────────────────────────────────

@app.exception_handler(HTTPException)
async def htmx_exception_handler(request: Request, exc: HTTPException):
    return HTMLResponse(
        content=f'<p class="result-error">Erreur {exc.status_code} : {escape(str(exc.detail))}</p>',
        status_code=exc.status_code,
    )


# ── Routes ─────────────────────────────────────────────────────────────────────

@app.get("/api/config")
async def get_config():
    return JSONResponse({
        "supabase_url": os.environ["SUPABASE_URL"],
        "supabase_anon_key": os.environ["SUPABASE_ANON_KEY"],
    })


@app.get("/", response_class=FileResponse)
async def serve_frontend():
    return FileResponse(BASE_DIR / "static" / "index.html")


@app.get("/dashboard", response_class=FileResponse)
async def serve_dashboard():
    return FileResponse(BASE_DIR / "static" / "dashboard.html")


@app.post("/api/analyze", response_class=HTMLResponse)
async def analyze_image(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
):
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(415, detail="Type de fichier non supporté.")
    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(415, detail=f"Format non supporté : {file.content_type}.")

    image_bytes = await file.read()
    if len(image_bytes) > MAX_FILE_SIZE:
        raise HTTPException(413, detail="Image trop volumineuse (maximum 10 Mo).")

    try:
        data = agent.extract_from_bytes(image_bytes, media_type=file.content_type)
    except Exception as e:
        raise HTTPException(500, detail=f"Erreur du modèle : {str(e)}")

    image_b64 = base64.b64encode(image_bytes).decode("utf-8")
    return HTMLResponse(content=build_form_fragment(data, image_b64, file.content_type))


@app.post("/api/submit", response_class=HTMLResponse)
async def submit_expense(
    type_document: str = Form(...),
    fournisseur: str = Form(""),
    date: str = Form(""),
    montant_ttc: str = Form(""),
    tva: str = Form(""),
    devise: str = Form("EUR"),
    description: str = Form(""),
    confiance: str = Form(""),
    image_data: str = Form(""),
    media_type: str = Form("image/jpeg"),
    current_user: dict = Depends(get_current_user),
):
    data = {
        "type_document": type_document,
        "fournisseur": fournisseur or None,
        "date": date or None,
        "montant_ttc": float(montant_ttc) if montant_ttc else None,
        "tva": float(tva) if tva else None,
        "devise": devise or "EUR",
        "description": description or None,
        "confiance": confiance or None,
    }

    image_url = None
    if image_data:
        try:
            image_bytes = base64.b64decode(image_data)

            def slugify(s):
                s = unicodedata.normalize("NFD", s)
                s = "".join(c for c in s if unicodedata.category(c) != "Mn")
                return s.lower().replace(" ", "_")

            nom = slugify(current_user.get("nom", "inconnu"))
            prenom = slugify(current_user.get("prenom", "inconnu"))
            user_id = current_user.get("id", "")[:8]
            date_clean = (date or "sans-date").replace("/", "-")
            ext = "jpg" if "jpeg" in media_type else media_type.split("/")[-1]
            filename = f"{user_id}_{nom}_{prenom}_{date_clean}.{ext}"
            image_url = supabase.upload_image(image_bytes, filename=filename, media_type=media_type)
        except Exception as e:
            raise HTTPException(500, detail=f"Erreur upload image : {str(e)}")

    try:
        sheets.append_expense(data=data, user=current_user, image_url=image_url)
    except Exception as e:
        raise HTTPException(500, detail=f"Erreur Google Sheets : {str(e)}")

    try:
        supabase.save_expense(user_id=current_user["id"], data=data, image_url=image_url)
    except Exception as e:
        raise HTTPException(500, detail=f"Erreur sauvegarde Supabase : {str(e)}")

    return HTMLResponse(content=build_success_fragment(image_url))


@app.get("/api/history", response_class=HTMLResponse)
async def get_history(current_user: dict = Depends(get_current_user)):
    try:
        expenses = supabase.get_history(current_user["id"])
    except Exception as e:
        raise HTTPException(500, detail=f"Erreur historique : {str(e)}")
    return HTMLResponse(content=build_history_fragment(expenses))


@app.get("/api/export-pdf")
async def export_pdf(
    month: str = Query(..., description="Format YYYY-MM"),
    current_user: dict = Depends(get_current_user),
):
    try:
        year, m = map(int, month.split("-"))
    except ValueError:
        raise HTTPException(400, detail="Format de mois invalide. Utilisez YYYY-MM.")

    try:
        expenses = supabase.get_monthly_expenses(current_user["id"], year, m)
        profile = supabase.get_profile(current_user["id"])
        pdf_bytes = generate_pdf(expenses, profile, year, m)
    except Exception as e:
        raise HTTPException(500, detail=f"Erreur génération PDF : {str(e)}")

    nom = profile.get("nom", "employe").lower().replace(" ", "_")
    filename = f"notes-frais-{nom}-{month}.pdf"
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@app.get("/api/dashboard/stats")
async def dashboard_stats(current_user: dict = Depends(get_current_user)):
    try:
        stats = supabase.get_dashboard_stats(current_user["id"])
    except Exception as e:
        raise HTTPException(500, detail=f"Erreur stats : {str(e)}")
    return JSONResponse(stats)

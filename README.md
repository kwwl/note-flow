# NoteFlow — Application Agentique de Gestion des Notes de Frais

> Du ticket de caisse au Google Sheet en quelques secondes.

NoteFlow est une application web agentique permettant aux employés de photographier leurs justificatifs de dépenses, d'en extraire automatiquement les informations clés grâce à l'IA, de les valider et de les synchroniser dans un Google Sheet partagé avec la comptabilité.

---

## Démo

🔗 **Application** : [note-flow-production-ee36.up.railway.app](https://note-flow-production-ee36.up.railway.app)

📊 **Google Sheet** : [Voir les notes de frais](https://docs.google.com/spreadsheets/d/1IBGiEqLxHfUscHcdouJSZZVsuZR4OlhaDjkpnQMk-v8/edit?usp=sharing)

---

## Fonctionnalités

- **Extraction automatique** — photo d'un ticket → extraction des champs via Llama 4 Scout (Groq)
- **Formulaire éditable** — correction manuelle avant envoi
- **Authentification** — inscription / connexion via Supabase Auth
- **Stockage images** — upload automatique sur Supabase Storage
- **Google Sheets** — synchronisation en temps réel avec lien cliquable vers le justificatif
- **Historique** — affichage des 5 dernières notes de frais dans l'interface
- **Dashboard** — graphiques mensuels, répartition par catégorie, KPIs
- **Export PDF** — récapitulatif mensuel téléchargeable par employé

---

## Stack technique

| Composant | Technologie |
|---|---|
| Modèle IA | `meta-llama/llama-4-scout-17b-16e-instruct` via Groq SDK |
| Backend | Python · FastAPI |
| Frontend | HTML · HTMX · CSS · JS Vanilla |
| Auth & DB | Supabase (Auth + PostgreSQL + Storage) |
| Intégration | Google Sheets API via `gspread` |
| PDF | ReportLab |
| Déploiement | Railway |

---

## Architecture

```
note-flow/
├── app.py              # Serveur FastAPI — routes et fragments HTML
├── backend.py          # ExpenseAgent (Groq), SupabaseStorage, GoogleSheetsClient
├── context.txt         # Prompt système du modèle vision
├── prompt.txt          # Prompt utilisateur du modèle vision
├── requirements.txt
├── static/
│   ├── index.html      # Interface principale (upload, formulaire, historique)
│   ├── dashboard.html  # Dashboard analytique
│   └── app.js          # Logique JS (auth Supabase, HTMX, prévisualisation)
└── .env                # Variables d'environnement (non versionné)
```

---

## Installation locale

### Prérequis

- Python 3.11+
- Un compte [Groq](https://console.groq.com)
- Un compte [Supabase](https://supabase.com)
- Un compte Google avec accès à l'API Sheets

### 1. Cloner le projet

```bash
git clone https://github.com/kwwl/note-flow.git
cd note-flow
```

### 2. Environnement virtuel

```bash
python3 -m venv env
source env/bin/activate
pip install -r requirements.txt
```

### 3. Variables d'environnement

Créer un fichier `.env` à la racine :

```dotenv
GROQ_API_KEY=""
GOOGLE_SHEET_ID=""
GOOGLE_SERVICE_ACCOUNT_JSON="/chemin/vers/credentials.json"
SUPABASE_URL=""
SUPABASE_ANON_KEY=""
SUPABASE_SERVICE_KEY=""
SUPABASE_BUCKET="tickets"
```

### 4. Supabase — Configuration

Exécuter dans le SQL Editor de Supabase :

```sql
-- Table profils utilisateurs
create table profiles (
  id uuid references auth.users on delete cascade primary key,
  nom text, prenom text, email text
);
alter table profiles enable row level security;
create policy "select own" on profiles for select using (auth.uid() = id);
create policy "insert own" on profiles for insert with check (auth.uid() = id);

-- Trigger création automatique du profil
create or replace function public.handle_new_user()
returns trigger as $$
begin
  insert into public.profiles (id, nom, prenom, email)
  values (new.id, new.raw_user_meta_data->>'nom', new.raw_user_meta_data->>'prenom', new.email);
  return new;
end;
$$ language plpgsql security definer;

create trigger on_auth_user_created
  after insert on auth.users
  for each row execute procedure public.handle_new_user();

-- Table notes de frais
create table expenses (
  id uuid default gen_random_uuid() primary key,
  user_id uuid references auth.users on delete cascade,
  type_document text, fournisseur text, date text,
  montant_ttc numeric, tva numeric, devise text,
  description text, confiance text, image_url text,
  created_at timestamptz default now()
);
alter table expenses enable row level security;
create policy "select own" on expenses for select using (auth.uid() = user_id);
create policy "insert own" on expenses for insert with check (auth.uid() = user_id);
```

Créer un bucket Storage nommé **`tickets`** en mode public.

### 5. Google Sheet

Le sheet doit avoir un onglet **"Notes de frais"** avec les colonnes dans cet ordre :

| ID Employé | Nom | Prénom | Horodatage | Type | Fournisseur | Date | Montant TTC (€) | TVA (€) | Devise | Description | Confiance | Image | Lien du ticket |

### 6. Lancer l'application

```bash
uvicorn app:app --reload
```

Ouvrir [http://localhost:8000](http://localhost:8000)

---

## Déploiement Railway

1. Connecter le repo GitHub dans Railway
2. Ajouter toutes les variables d'environnement dans Railway → Variables
3. Pour `GOOGLE_SERVICE_ACCOUNT_JSON`, coller le contenu JSON brut du fichier credentials
4. Start command : `uvicorn app:app --host 0.0.0.0 --port $PORT`
5. Générer un domaine public dans Settings → Networking

---

## Branches Git

| Branche | Contenu |
|---|---|
| `feature/extraction-backend` | `ExpenseAgent` — extraction via Groq |
| `feature/google-sheets` | `GoogleSheetsClient` — synchronisation Sheets |
| `feature/frontend-vibe` | Interface HTML/HTMX/CSS |
| `feature/edition-manuelle` | Formulaire éditable + route `/api/submit` |
| `feature/upload-image-sheet` | Auth Supabase + upload Storage + dashboard + historique + PDF |
| `dev` | Branche d'intégration |
| `main` | Production |

---

## Auteur

**Kémil Lamouri** — Data IA HETIC 2026

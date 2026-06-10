from groq import Groq
import base64
from dotenv import load_dotenv
import os
import json
import gspread
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
from supabase import create_client
import io

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

EXPECTED_FIELDS = [
    "type_document",
    "fournisseur",
    "date",
    "montant_ttc",
    "tva",
    "devise",
    "description",
    "confiance",
]


class ExpenseAgent:
    def __init__(self):
        load_dotenv()
        self.client = Groq(api_key=os.environ["GROQ_API_KEY"])

    @staticmethod
    def read_file(file_path):
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()

    def extract_from_bytes(
        self, image_bytes: bytes, media_type: str = "image/jpeg"
    ) -> dict:
        base64_image = base64.b64encode(image_bytes).decode("utf-8")
        base_dir = os.path.dirname(os.path.abspath(__file__))

        chat_completion = self.client.chat.completions.create(
            messages=[
                {
                    "role": "system",
                    "content": ExpenseAgent.read_file(
                        os.path.join(base_dir, "context.txt")
                    ),
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": ExpenseAgent.read_file(
                                os.path.join(base_dir, "prompt.txt")
                            ),
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{media_type};base64,{base64_image}",
                            },
                        },
                    ],
                },
            ],
            response_format={"type": "json_object"},
            model="meta-llama/llama-4-scout-17b-16e-instruct",
        )

        raw = json.loads(chat_completion.choices[0].message.content)
        result = {field: raw.get(field, None) for field in EXPECTED_FIELDS}
        return result


class SupabaseStorage:
    def __init__(self):
        load_dotenv()
        self.client = create_client(
            os.environ["SUPABASE_URL"],
            os.environ["SUPABASE_SERVICE_KEY"],
        )
        self.bucket = os.environ.get("SUPABASE_BUCKET", "tickets")

    def verify_jwt(self, token: str):
        """Vérifie le JWT Supabase et retourne l'objet user."""
        response = self.client.auth.get_user(token)
        return response.user

    def get_profile(self, user_id: str) -> dict:
        """Récupère nom et prénom depuis la table profiles."""
        response = (
            self.client.table("profiles")
            .select("nom, prenom")
            .eq("id", user_id)
            .single()
            .execute()
        )
        return response.data or {}

    def upload_image(
        self, image_bytes: bytes, filename: str, media_type: str = "image/jpeg"
    ) -> str:
        """Upload l'image dans le bucket Supabase Storage et retourne l'URL publique."""
        self.client.storage.from_(self.bucket).upload(
            path=filename,
            file=image_bytes,
            file_options={"content-type": media_type, "upsert": "true"},
        )
        return self.client.storage.from_(self.bucket).get_public_url(filename)


class GoogleSheetsClient:
    def __init__(self):
        load_dotenv()
        service_account_info = json.loads(os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"])
        creds = Credentials.from_service_account_info(
            service_account_info,
            scopes=SCOPES,
        )
        self.gc = gspread.authorize(creds)
        self.sheet = self.gc.open_by_key(os.environ["GOOGLE_SHEET_ID"]).worksheet(
            "Notes de frais"
        )
        self.drive = build("drive", "v3", credentials=creds)

    def append_expense(
        self, data: dict, user: dict = None, image_url: str = None
    ) -> None:
        from datetime import datetime
        from zoneinfo import ZoneInfo

        image_formula = f'=IMAGE("{image_url}")' if image_url else ""
        hyperlink_formula = f'=HYPERLINK("{image_url}", "Voir le ticket")' if image_url else ""
        horodatage = datetime.now(ZoneInfo("Europe/Paris")).strftime("%d/%m/%Y %H:%M:%S")

        row = [
            user.get("id", "") if user else "",
            user.get("nom", "") if user else "",
            user.get("prenom", "") if user else "",
            horodatage,
            data.get("type_document", ""),
            data.get("fournisseur", ""),
            data.get("date", ""),
            data.get("montant_ttc", ""),
            data.get("tva", ""),
            data.get("devise", "EUR"),
            data.get("description", ""),
            data.get("confiance", ""),
            image_formula,
            hyperlink_formula,
        ]

        self.sheet.append_row(row, value_input_option="USER_ENTERED")


if __name__ == "__main__":
    import sys

    agent = ExpenseAgent()

    image_path = sys.argv[1] if len(sys.argv) > 1 else "ticket.jpg"

    with open(image_path, "rb") as f:
        image_bytes = f.read()

    ext = image_path.rsplit(".", 1)[-1].lower()
    media_type = {
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "png": "image/png",
        "webp": "image/webp",
    }.get(ext, "image/jpeg")

    result = agent.extract_from_bytes(image_bytes=image_bytes, media_type=media_type)

    print(json.dumps(result, ensure_ascii=False, indent=2))

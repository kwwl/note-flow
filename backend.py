from groq import Groq
import base64
from dotenv import load_dotenv
import os
import json
import gspread
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
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


class GoogleSheetsClient:
    def __init__(self):
        load_dotenv()
        creds = Credentials.from_service_account_file(
            os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"],
            scopes=SCOPES,
        )
        self.gc = gspread.authorize(creds)
        self.sheet = self.gc.open_by_key(os.environ["GOOGLE_SHEET_ID"]).worksheet(
            "Notes de frais"
        )
        self.drive = build("drive", "v3", credentials=creds)

    def upload_image_to_drive(
        self, image_bytes: bytes, filename: str, media_type: str = "image/jpeg"
    ) -> str:
        folder_id = os.environ.get("GOOGLE_DRIVE_FOLDER_ID")
        file_metadata = (
            {"name": filename, "parents": [folder_id]}
            if folder_id
            else {"name": filename}
        )
        media = MediaIoBaseUpload(io.BytesIO(image_bytes), mimetype=media_type)

        uploaded = (
            self.drive.files()
            .create(
                body=file_metadata,
                media_body=media,
                fields="id",
            )
            .execute()
        )

        file_id = uploaded.get("id")

        # Rendre le fichier public en lecture
        self.drive.permissions().create(
            fileId=file_id,
            body={"type": "anyone", "role": "reader"},
        ).execute()

        return f"https://drive.google.com/uc?id={file_id}"

    def append_expense(self, data: dict, image_url: str = None) -> None:
        from datetime import datetime

        image_formula = f'=IMAGE("{image_url}")' if image_url else ""
        horodatage = datetime.now().strftime("%d/%m/%Y %H:%M:%S")

        row = [
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

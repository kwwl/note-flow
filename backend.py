from groq import Groq
import base64
from dotenv import load_dotenv
import os
import json

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

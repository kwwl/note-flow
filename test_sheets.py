from backend import GoogleSheetsClient

client = GoogleSheetsClient()

fake_data = {
    "type_document": "restaurant",
    "fournisseur": "Bistrot Test",
    "date": "08/06/2026",
    "montant_ttc": 24.50,
    "tva": 4.08,
    "devise": "EUR",
    "description": "Déjeuner de test",
    "confiance": "haute",
}

client.append_expense(data=fake_data, image_url=None)
print("Ligne ajoutée avec succès dans le Sheet")

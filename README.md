# Invoice Upload AI

A web application that uses AI to extract data from invoices and automatically populate Google Sheets.

## Features

- Simple drag-and-drop interface for invoice uploads
- Supports PDF, PNG, and JPEG formats
- AI-powered invoice data extraction
- Automatic Google Sheets integration
- Modern, responsive UI

## Setup Instructions

1. Install Python 3.7 or higher if you haven't already.

2. Install the required dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Set up Google Cloud Vision API:
   - Go to the [Google Cloud Console](https://console.cloud.google.com)
   - Create a new project or select an existing one
   - Enable the Cloud Vision API
   - Create service account credentials and download the JSON file
   - Rename the downloaded file to `credentials.json` and place it in the project root

4. Set up Google Sheets API:
   - In the same Google Cloud Console project, enable the Google Sheets API
   - Create a new Google Sheet and copy its ID from the URL
   - Update the `SAMPLE_SPREADSHEET_ID` in `app.py` with your sheet's ID
   - Share the sheet with the email address from your service account

5. Run the application:
   ```bash
   python app.py
   ```

6. Open your browser and navigate to `http://localhost:5000`

## Usage

1. Open the web application in your browser
2. Drag and drop an invoice file or click to select one
3. Click the "Upload Invoice" button
4. Wait for the AI to process the invoice
5. Check your Google Sheet for the extracted data

## Columns in Google Sheet

- Invoice Date
- Invoice Number
- Expense Description
- Expense Quantity
- Expense Amount
- Total Expense Cost
- Date Accessed

## Support

For any issues or questions, please open an issue on GitHub. 